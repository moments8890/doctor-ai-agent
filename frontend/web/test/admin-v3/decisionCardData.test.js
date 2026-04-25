// TDD test for the decision-card data transform used by the admin v3 AI 与知识 tab.
// Spec: docs/plans/2026-04-24-admin-modern-port.md — Task 2.5 step 1.
//
// `toDecisionCards(items)` is a pure transform. It maps the raw rows returned
// by GET /api/admin/doctors/{id}/related (`suggestions.items[]`) into the
// 4-block decision-card shape consumed by <DecisionCard>:
//   { id, patient, kind, sectionTag, time, observation,
//     evidence: [{ num, title, quote }],
//     risks:    [{ label, level }],
//     outcome:  { badge, who, when, prose, triptych? } }
//
// `kind` derivation:
//   - section in {"workup","differential"} OR explicit `danger_signal` flag → "danger_signal"
//   - section === "treatment" OR has `doctor_reply` → "reply_suggestion"
//
// `outcome.badge` mapping from `decision`:
//   confirmed → accept · edited → edit · rejected → reject · generated → pending

import { describe, it, expect } from "vitest";
import { toDecisionCards } from "../../src/pages/admin/v3/doctorDetail/decisionCardData";

const REPLY_ROW = {
  id: 1,
  patient_id: 7,
  patient_name: "陈玉琴",
  section: "treatment",
  content: "建议氨氯地平 5→10mg；两周后复测。",
  decision: "edited",
  cited_knowledge_ids: [12],
  cited_knowledge: [
    { id: 12, title: "高血压调药梯度", quote: "先加量再加药" },
  ],
  doctor_reply:
    "陈阿姨好，您先把氨氯地平加到 10mg/日，两周后我们再测一次。",
  edit_reason: "删除了 ACEI 提示（过早），加入了起立性低血压提醒。",
  risk_tags: [
    { label: "用药变更 · 需医生确认", level: "med" },
    { label: "符合医生既有规则", level: "low" },
  ],
  created_at: "2026-04-24T14:42:00Z",
};

const DANGER_ROW = {
  id: 2,
  patient_id: 9,
  patient_name: "林文华",
  section: "workup",
  content:
    "过去 5 天体重连续上升（+1.8 kg），夜间静息心率 78→102 bpm，疑似心衰失代偿前兆。",
  decision: "confirmed",
  cited_knowledge: [
    { id: 8,  title: "心衰失代偿早期识别", quote: "体重 7 天内增加 ≥1.5 kg + 心率持续 ↑ + 端坐呼吸 = 高度怀疑" },
    { id: 15, title: "2023 中国心衰指南",   quote: "体重监测是门诊随访早期识别失代偿的最敏感指标。" },
  ],
  risk_tags: [
    { label: "高风险", level: "high" },
    { label: "建议 24h 内联系", level: "med" },
  ],
  created_at: "2026-04-23T17:14:00Z",
};

describe("toDecisionCards", () => {
  it("kind=reply_suggestion when section=treatment and doctor_reply present", () => {
    const cards = toDecisionCards([REPLY_ROW]);
    expect(cards).toHaveLength(1);
    expect(cards[0].kind).toBe("reply_suggestion");
  });

  it("kind=danger_signal when section=workup (or explicit danger flag)", () => {
    const cards = toDecisionCards([DANGER_ROW]);
    expect(cards[0].kind).toBe("danger_signal");

    const explicit = toDecisionCards([
      { ...REPLY_ROW, id: 99, section: "general", danger_signal: true, doctor_reply: null },
    ]);
    expect(explicit[0].kind).toBe("danger_signal");
  });

  it("preserves citations as evidence array of {num, title, quote}", () => {
    const cards = toDecisionCards([REPLY_ROW]);
    expect(cards[0].evidence).toEqual([
      { num: 12, title: "高血压调药梯度", quote: "先加量再加药" },
    ]);

    const dangerCards = toDecisionCards([DANGER_ROW]);
    expect(dangerCards[0].evidence).toEqual([
      { num: 8,  title: "心衰失代偿早期识别", quote: "体重 7 天内增加 ≥1.5 kg + 心率持续 ↑ + 端坐呼吸 = 高度怀疑" },
      { num: 15, title: "2023 中国心衰指南",   quote: "体重监测是门诊随访早期识别失代偿的最敏感指标。" },
    ]);
  });

  it("falls back to knowledge.items when only cited_knowledge_ids is present", () => {
    const knowledgeIndex = {
      knowledge: {
        items: [
          { id: 12, title: "高血压调药梯度", content: "先加量再加药" },
        ],
      },
    };
    const cards = toDecisionCards(
      [{ ...REPLY_ROW, cited_knowledge: undefined }],
      knowledgeIndex,
    );
    expect(cards[0].evidence).toEqual([
      { num: 12, title: "高血压调药梯度", quote: "先加量再加药" },
    ]);
  });

  it("maps decision field to outcome.badge", () => {
    expect(toDecisionCards([{ ...REPLY_ROW, decision: "confirmed" }])[0].outcome.badge).toBe("accept");
    expect(toDecisionCards([{ ...REPLY_ROW, decision: "edited"    }])[0].outcome.badge).toBe("edit");
    expect(toDecisionCards([{ ...REPLY_ROW, decision: "rejected"  }])[0].outcome.badge).toBe("reject");
    expect(toDecisionCards([{ ...REPLY_ROW, decision: "generated" }])[0].outcome.badge).toBe("pending");
  });

  it("populates outcome.triptych for reply_suggestion with both AI draft + doctor_reply", () => {
    const cards = toDecisionCards([REPLY_ROW]);
    expect(cards[0].outcome.triptych).toEqual({
      aiDraft: REPLY_ROW.content,
      sentVersion: REPLY_ROW.doctor_reply,
      reason: REPLY_ROW.edit_reason,
    });
  });

  it("danger_signal cards have no triptych", () => {
    const cards = toDecisionCards([DANGER_ROW]);
    expect(cards[0].outcome.triptych).toBeUndefined();
  });

  it("returns empty array for null/undefined input", () => {
    expect(toDecisionCards(undefined)).toEqual([]);
    expect(toDecisionCards(null)).toEqual([]);
    expect(toDecisionCards([])).toEqual([]);
  });
});
