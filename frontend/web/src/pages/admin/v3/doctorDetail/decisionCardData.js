// decisionCardData — pure transform from raw `/related.suggestions.items[]`
// rows into the 4-block decision-card shape consumed by <DecisionCard>.
//
// See docs/plans/2026-04-24-admin-modern-port.md — Task 2.5 step 3, and the
// `.dc.danger` / `.dc.info` example cards in
// docs/specs/2026-04-24-admin-modern-mockup-v3.html (lines ~1849-1981).
//
// Backend schema (admin_overview.py admin_doctor_related, ~line 1373):
//   { id, record_id, section, content, decision, created_at }
// Plus optional richer fields some callers populate:
//   patient_id, patient_name, doctor_reply, edit_reason,
//   cited_knowledge[{id,title,quote}], cited_knowledge_ids[],
//   risk_tags[{label,level} | string], danger_signal (bool)
//
// Missing fields are tolerated — every output field defaults to a safe value.

const DECISION_TO_BADGE = {
  confirmed: "accept",
  edited: "edit",
  rejected: "reject",
  generated: "pending",
};

const DANGER_SECTIONS = new Set(["workup", "differential", "danger_signal"]);
const REPLY_SECTIONS = new Set(["treatment", "reply", "followup"]);

const SECTION_TAG_MAP = {
  treatment: "回复建议 · 用药调整",
  reply: "回复建议",
  followup: "回复建议 · 随访",
  workup: "危险信号",
  differential: "危险信号",
  danger_signal: "危险信号",
};

function nameInitial(name) {
  if (!name || typeof name !== "string") return "·";
  // Take the first grapheme/character (works for CJK names like "陈玉琴" → "陈").
  return Array.from(name)[0] || "·";
}

function pad2(n) {
  return n < 10 ? `0${n}` : `${n}`;
}

function fmtTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return String(iso);
  return `${pad2(d.getMonth() + 1)}·${pad2(d.getDate())} ${pad2(d.getHours())}:${pad2(d.getMinutes())}`;
}

function deriveKind(row) {
  if (row.danger_signal === true) return "danger_signal";
  if (row.kind === "danger_signal" || row.kind === "reply_suggestion") return row.kind;
  const section = String(row.section || "").toLowerCase();
  if (DANGER_SECTIONS.has(section)) return "danger_signal";
  if (REPLY_SECTIONS.has(section)) return "reply_suggestion";
  // Heuristic: if a doctor_reply exists, it's a reply_suggestion. Otherwise default to danger.
  if (row.doctor_reply) return "reply_suggestion";
  return "danger_signal";
}

function deriveSectionTag(row, kind) {
  if (row.section_tag) return row.section_tag;
  const section = String(row.section || "").toLowerCase();
  if (SECTION_TAG_MAP[section]) return SECTION_TAG_MAP[section];
  return kind === "danger_signal" ? "危险信号" : "回复建议";
}

function deriveEvidence(row, knowledge) {
  // Preferred: explicit cited_knowledge with full {id,title,quote}.
  if (Array.isArray(row.cited_knowledge) && row.cited_knowledge.length > 0) {
    return row.cited_knowledge.map((k) => ({
      num: k.id ?? k.num ?? null,
      title: k.title || "",
      quote: k.quote || k.snippet || "",
    }));
  }
  // 2026-04-25 new schema: trigger_rule_ids array (e.g. ["KB-12"]) maps to KB items
  if (Array.isArray(row.trigger_rule_ids) && row.trigger_rule_ids.length > 0) {
    const items = knowledge?.knowledge?.items || knowledge?.items || [];
    const byId = new Map(items.map((k) => [k.id, k]));
    const fromTriggers = row.trigger_rule_ids
      .map((tid) => {
        const m = String(tid).match(/KB-(\d+)/i);
        const id = m ? Number(m[1]) : null;
        const k = id !== null ? byId.get(id) : null;
        if (!k) return null;
        return {
          num: id,
          title: k.title || "",
          quote: k.quote || k.snippet || k.content || "",
        };
      })
      .filter(Boolean);
    if (fromTriggers.length > 0) return fromTriggers;
  }
  // Fallback: cited_knowledge_ids matched against knowledge.items by id.
  if (Array.isArray(row.cited_knowledge_ids) && row.cited_knowledge_ids.length > 0) {
    const items = knowledge?.knowledge?.items || knowledge?.items || [];
    const byId = new Map(items.map((k) => [k.id, k]));
    return row.cited_knowledge_ids
      .map((id) => {
        const k = byId.get(id);
        if (!k) return null;
        return {
          num: id,
          title: k.title || "",
          quote: k.quote || k.snippet || k.content || "",
        };
      })
      .filter(Boolean);
  }
  return [];
}

function normalizeRiskLevel(level) {
  const v = String(level || "").toLowerCase();
  if (v === "high" || v === "med" || v === "low") return v;
  return "low";
}

function deriveRisks(row) {
  // 2026-04-25 new schema: risk_signals array (atomic strings) is the primary source
  if (Array.isArray(row.risk_signals) && row.risk_signals.length > 0) {
    return row.risk_signals
      .filter((s) => s && typeof s === "string")
      .map((s) => ({ label: s, level: "med" }));
  }
  // Legacy: risk_tags array (mixed string/object shape)
  const tags = row.risk_tags;
  if (!Array.isArray(tags)) return [];
  return tags
    .map((t) => {
      if (typeof t === "string") return { label: t, level: "low" };
      if (t && typeof t === "object") {
        return { label: t.label || t.text || "", level: normalizeRiskLevel(t.level) };
      }
      return null;
    })
    .filter((t) => t && t.label);
}

function deriveBadge(decision) {
  return DECISION_TO_BADGE[String(decision || "").toLowerCase()] || "pending";
}

function deriveOutcome(row, kind) {
  const badge = deriveBadge(row.decision);
  const outcome = {
    badge,
    who: row.outcome_who || row.doctor_name || "",
    when: fmtTime(row.outcome_at || row.updated_at || row.created_at),
    prose: row.outcome_prose || row.doctor_note || "",
  };

  // Triptych is reply_suggestion-only and only when both an AI draft (content)
  // AND a doctor_reply exist. The "reason" column may be empty (codex polish).
  if (kind === "reply_suggestion" && row.content && row.doctor_reply) {
    outcome.triptych = {
      aiDraft: row.content,
      sentVersion: row.doctor_reply,
      reason: row.edit_reason || "",
    };
  }

  return outcome;
}

export function toDecisionCards(items, knowledge) {
  if (!Array.isArray(items)) return [];

  return items.map((row) => {
    const kind = deriveKind(row);
    const patientName = row.patient_name || row.name || "";
    return {
      id: row.id,
      patient: {
        id: row.patient_id ?? null,
        name: patientName,
        initial: nameInitial(patientName),
      },
      kind,
      sectionTag: deriveSectionTag(row, kind),
      time: fmtTime(row.created_at),
      // 2026-04-25 new schema: prefer evidence array (atomic facts) for the
      // "AI 观察" block; fall back to legacy observation/content.
      observation: (Array.isArray(row.evidence) && row.evidence.length > 0)
        ? row.evidence.join("，")
        : (row.observation || row.content || ""),
      evidence: deriveEvidence(row, knowledge),
      risks: deriveRisks(row),
      outcome: deriveOutcome(row, kind),
    };
  });
}

export default toDecisionCards;
