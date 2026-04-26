// AdminPatientDetailV3 — patient drill-down inside the V3 admin shell.
// Mirrors AdminDoctorDetailV3's pattern (header + sections), backed by
// /api/admin/patients/{patient_id}/related which already returns records,
// messages, tasks, suggestions, interviews, drafts.
//
// Routing contract: ?v=3&patient=<id>. v3/index.jsx detects `patient` and
// renders this component instead of the doctor or doctor-list view.

import { useEffect, useState } from "react";
import { COLOR, FONT, FONT_STACK, RADIUS, SHADOW } from "../tokens";
import EmptyState from "../components/EmptyState";
import SectionLoading from "../components/SectionLoading";
import SectionError from "../components/SectionError";

const ADMIN_TOKEN_KEY = "adminToken";

async function fetchAdminJson(url) {
  const token =
    localStorage.getItem(ADMIN_TOKEN_KEY) ||
    (import.meta.env.DEV ? "dev" : "");
  const res = await fetch(url, {
    headers: token ? { "X-Admin-Token": token } : {},
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

function fmtRelative(ts) {
  if (!ts) return "—";
  const d = new Date(ts.replace(" ", "T") + "Z");
  if (Number.isNaN(d.getTime())) return String(ts).slice(0, 16);
  const diffMin = Math.floor((Date.now() - d.getTime()) / 60000);
  if (diffMin < 1) return "刚刚";
  if (diffMin < 60) return `${diffMin} 分钟前`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr} 小时前`;
  const diffDay = Math.floor(diffHr / 24);
  if (diffDay < 30) return `${diffDay} 天前`;
  return ts.slice(0, 10);
}

function calcAge(year_of_birth) {
  if (!year_of_birth) return null;
  return new Date().getFullYear() - Number(year_of_birth);
}

// ── Patient header ─────────────────────────────────────────────────────────

function PatientHeader({ profile, doctorId }) {
  const initial = (profile.name || "?").trim().charAt(0);
  const age = calcAge(profile.year_of_birth);
  const meta = [
    profile.gender,
    age != null ? `${age} 岁` : null,
    profile.phone || null,
  ].filter(Boolean).join(" · ");

  function backToDoctor() {
    if (typeof window === "undefined") return;
    const params = new URLSearchParams(window.location.search);
    params.delete("patient");
    if (doctorId) params.set("doctor", doctorId);
    const next = `${window.location.pathname}?${params.toString()}`;
    window.history.pushState(null, "", next);
    window.dispatchEvent(new PopStateEvent("popstate"));
  }

  return (
    <section
      style={{
        background: COLOR.bgCard,
        border: `1px solid ${COLOR.borderSubtle}`,
        borderRadius: RADIUS.lg,
        boxShadow: SHADOW.s1,
        padding: "16px 20px",
        display: "flex",
        alignItems: "center",
        gap: 16,
        marginBottom: 16,
      }}
    >
      <div
        style={{
          width: 48,
          height: 48,
          borderRadius: "50%",
          background: COLOR.brandTint,
          color: COLOR.brand,
          display: "grid",
          placeItems: "center",
          fontSize: 18,
          fontWeight: 600,
          flexShrink: 0,
        }}
      >
        {initial}
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
          <span style={{ fontSize: FONT.lg, fontWeight: 600, color: COLOR.text1 }}>
            {profile.name || "(未命名患者)"}
          </span>
          <span style={{ fontSize: FONT.sm, color: COLOR.text3 }}>
            来自 {profile.doctor_name || "(未命名医生)"}
          </span>
        </div>
        {meta && (
          <div style={{ fontSize: FONT.sm, color: COLOR.text3, marginTop: 4 }}>
            {meta}
          </div>
        )}
        <div
          style={{
            fontSize: FONT.xs,
            color: COLOR.text3,
            fontFamily: FONT_STACK.mono,
            marginTop: 4,
          }}
        >
          patient_id={profile.id} · 注册 {fmtRelative(profile.created_at)}
        </div>
      </div>
      <button
        type="button"
        onClick={backToDoctor}
        style={{
          fontSize: FONT.sm,
          color: COLOR.text2,
          background: "transparent",
          border: `1px solid ${COLOR.borderDefault}`,
          borderRadius: RADIUS.md,
          padding: "6px 12px",
          cursor: "pointer",
        }}
      >
        ← 返回医生
      </button>
    </section>
  );
}

// ── KPI strip ──────────────────────────────────────────────────────────────

function PatientKpiStrip({ data }) {
  const cells = [
    { label: "病历", value: data.records?.count ?? 0 },
    { label: "消息", value: data.messages?.count ?? 0 },
    { label: "任务", value: data.tasks?.count ?? 0 },
    { label: "AI 建议", value: data.suggestions?.count ?? 0 },
  ];
  return (
    <section
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(4, 1fr)",
        gap: 12,
        marginBottom: 16,
      }}
    >
      {cells.map((c) => (
        <div
          key={c.label}
          style={{
            background: COLOR.bgCard,
            border: `1px solid ${COLOR.borderSubtle}`,
            borderRadius: RADIUS.lg,
            padding: "14px 18px",
          }}
        >
          <div style={{ fontSize: FONT.sm, color: COLOR.text3 }}>{c.label}</div>
          <div style={{ fontSize: 24, fontWeight: 600, color: COLOR.text1, marginTop: 4 }}>
            {c.value}
          </div>
        </div>
      ))}
    </section>
  );
}

// ── Generic section card ───────────────────────────────────────────────────

function SectionCard({ title, count, children }) {
  return (
    <section
      style={{
        background: COLOR.bgCard,
        border: `1px solid ${COLOR.borderSubtle}`,
        borderRadius: RADIUS.lg,
        boxShadow: SHADOW.s1,
        marginBottom: 16,
        overflow: "hidden",
      }}
    >
      <header
        style={{
          padding: "12px 16px",
          borderBottom: `1px solid ${COLOR.borderSubtle}`,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
        }}
      >
        <span style={{ fontSize: FONT.md, fontWeight: 600, color: COLOR.text1 }}>{title}</span>
        <span style={{ fontSize: FONT.sm, color: COLOR.text3 }}>{count}</span>
      </header>
      {children}
    </section>
  );
}

function EmptyRow({ label }) {
  return (
    <div style={{ padding: "20px 16px", textAlign: "center", color: COLOR.text3, fontSize: FONT.sm }}>
      {label}
    </div>
  );
}

// Display all populated clinical fields as labeled blocks. Skips fields that
// are null/empty so a thin interview_summary record renders compactly while a
// full visit note shows everything.
function RecordField({ label, value }) {
  if (!value) return null;
  return (
    <div style={{ marginTop: 8 }}>
      <div style={{ fontSize: FONT.xs, color: COLOR.text3, fontWeight: 500, letterSpacing: "0.02em" }}>
        {label}
      </div>
      <div style={{ fontSize: FONT.sm, color: COLOR.text1, whiteSpace: "pre-wrap", marginTop: 2 }}>
        {value}
      </div>
    </div>
  );
}

const RECORD_FIELDS = [
  { key: "chief_complaint",   label: "主诉" },
  { key: "present_illness",   label: "现病史" },
  { key: "past_history",      label: "既往史" },
  { key: "allergy_history",   label: "过敏史" },
  { key: "physical_exam",     label: "体格检查" },
  { key: "specialist_exam",   label: "专科检查" },
  { key: "auxiliary_exam",    label: "辅助检查" },
  { key: "diagnosis",         label: "诊断" },
  { key: "treatment_plan",    label: "治疗方案" },
  { key: "orders_followup",   label: "医嘱与随访" },
];

function RecordsSection({ items }) {
  return (
    <SectionCard title="病历" count={`${items.length} 条`}>
      {items.length === 0 ? (
        <EmptyRow label="暂无病历" />
      ) : (
        items.map((r) => {
          // Header line: type + status + date
          const populatedFields = RECORD_FIELDS.filter((f) => r[f.key]);
          const hasContent = !populatedFields.length && r.content;
          return (
            <div
              key={r.id}
              style={{
                padding: "14px 16px",
                borderTop: `1px solid ${COLOR.borderLight || COLOR.borderSubtle}`,
              }}
            >
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "baseline",
                  flexWrap: "wrap",
                  gap: 6,
                }}
              >
                <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
                  <span style={{ fontSize: FONT.body, fontWeight: 600, color: COLOR.text1 }}>
                    {r.record_type || "病历"}
                  </span>
                  {r.department && (
                    <span style={{ fontSize: FONT.xs, color: COLOR.text3 }}>
                      {r.department}
                    </span>
                  )}
                  {r.status && (
                    <span
                      style={{
                        fontSize: FONT.xs,
                        color: r.status === "completed" ? COLOR.brand : COLOR.text3,
                        background: r.status === "completed" ? COLOR.brandTint : COLOR.bgCardAlt,
                        padding: "2px 8px",
                        borderRadius: RADIUS.pill,
                      }}
                    >
                      {r.status}
                    </span>
                  )}
                </div>
                <span style={{ fontSize: FONT.xs, color: COLOR.text3 }}>
                  {fmtRelative(r.created_at)}
                </span>
              </div>
              {populatedFields.map((f) => (
                <RecordField key={f.key} label={f.label} value={r[f.key]} />
              ))}
              {hasContent && (
                <RecordField label="内容" value={r.content} />
              )}
            </div>
          );
        })
      )}
    </SectionCard>
  );
}

// Chat-bubble layout: patient on the left (gray bubble), doctor/AI on the
// right (brand-tint bubble), label adjacent to bubble, time below. Backend
// returns most recent first, so we reverse for chronological order — that's
// how a real chatlog reads.
function ChatBubble({ msg }) {
  const isInbound = msg.direction === "inbound";
  const senderLabel = isInbound
    ? "患者"
    : msg.source === "ai"
    ? "AI"
    : "医生";
  const senderColor = isInbound
    ? COLOR.info
    : msg.source === "ai"
    ? COLOR.brand
    : COLOR.text1;
  const bubbleBg = isInbound ? COLOR.bgCardAlt : COLOR.brandTint;
  const bubbleColor = COLOR.text1;
  return (
    <div
      style={{
        display: "flex",
        justifyContent: isInbound ? "flex-start" : "flex-end",
        marginBottom: 14,
      }}
    >
      <div style={{ maxWidth: "72%", display: "flex", flexDirection: "column", alignItems: isInbound ? "flex-start" : "flex-end" }}>
        <div
          style={{
            fontSize: FONT.xs,
            color: senderColor,
            fontWeight: 500,
            marginBottom: 4,
          }}
        >
          {senderLabel}
        </div>
        <div
          style={{
            fontSize: FONT.sm,
            color: bubbleColor,
            background: bubbleBg,
            padding: "10px 14px",
            borderRadius: 14,
            borderTopLeftRadius: isInbound ? 4 : 14,
            borderTopRightRadius: isInbound ? 14 : 4,
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
            lineHeight: 1.55,
          }}
        >
          {msg.content}
        </div>
        <div
          style={{
            fontSize: FONT.xs,
            color: COLOR.text3,
            marginTop: 4,
          }}
        >
          {fmtRelative(msg.created_at)}
        </div>
      </div>
    </div>
  );
}

function MessagesSection({ items }) {
  // Backend returns desc; flip so the conversation reads top-to-bottom.
  const ordered = [...items].reverse();
  return (
    <SectionCard title="对话记录" count={`${items.length} 条`}>
      {items.length === 0 ? (
        <EmptyRow label="暂无消息" />
      ) : (
        <div
          style={{
            padding: "16px 16px 6px",
            background: COLOR.bgPage,
          }}
        >
          {ordered.map((m) => (
            <ChatBubble key={m.id} msg={m} />
          ))}
        </div>
      )}
    </SectionCard>
  );
}

function TasksSection({ items }) {
  return (
    <SectionCard title="任务" count={`${items.length} 条`}>
      {items.length === 0 ? (
        <EmptyRow label="暂无任务" />
      ) : (
        items.map((t) => (
          <div
            key={t.id}
            style={{
              padding: "10px 16px",
              borderTop: `1px solid ${COLOR.borderLight || COLOR.borderSubtle}`,
              display: "flex",
              justifyContent: "space-between",
              alignItems: "baseline",
              gap: 12,
            }}
          >
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: FONT.body, color: COLOR.text1 }}>{t.title}</div>
              <div style={{ fontSize: FONT.xs, color: COLOR.text3, marginTop: 2 }}>
                {t.task_type} · {t.status}
                {t.due_at ? ` · 截止 ${fmtRelative(t.due_at)}` : ""}
              </div>
            </div>
          </div>
        ))
      )}
    </SectionCard>
  );
}

const URGENCY_LABEL = { high: "紧急", medium: "中等", low: "常规" };
const URGENCY_COLOR = (lvl) =>
  lvl === "high" ? COLOR.danger : lvl === "medium" ? COLOR.warning : COLOR.text3;
const DECISION_LABEL = {
  confirmed: "已采纳",
  edited: "修改后采纳",
  rejected: "已拒绝",
};
const DECISION_COLOR = (d) =>
  d === "confirmed" ? COLOR.brand
  : d === "edited" ? COLOR.warning
  : d === "rejected" ? COLOR.danger
  : COLOR.text3;

function Tag({ children, color, bg }) {
  return (
    <span
      style={{
        fontSize: FONT.xs,
        color,
        background: bg,
        padding: "2px 8px",
        borderRadius: RADIUS.pill,
        whiteSpace: "nowrap",
      }}
    >
      {children}
    </span>
  );
}

function SuggestionsSection({ items }) {
  return (
    <SectionCard title="AI 建议" count={`${items.length} 条`}>
      {items.length === 0 ? (
        <EmptyRow label="暂无 AI 建议" />
      ) : (
        items.map((s) => {
          const decisionColor = DECISION_COLOR(s.decision);
          const decisionLabel = s.decision
            ? DECISION_LABEL[s.decision] || s.decision
            : "未决定";
          // Confidence may be either a 0-1 float or a Chinese string ("高"/"中"/"低")
          // depending on which extractor produced it. Show whichever shape is real.
          let confidencePct = null;
          if (typeof s.confidence === "number" && !Number.isNaN(s.confidence)) {
            confidencePct = `${Math.round(s.confidence * 100)}%`;
          } else if (typeof s.confidence === "string" && s.confidence.trim()) {
            confidencePct = s.confidence.trim();
          }
          return (
            <div
              key={s.id}
              style={{
                padding: "14px 16px",
                borderTop: `1px solid ${COLOR.borderLight || COLOR.borderSubtle}`,
              }}
            >
              {/* Header: section + tags + decision */}
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "baseline",
                  flexWrap: "wrap",
                  gap: 6,
                }}
              >
                <div style={{ display: "flex", alignItems: "baseline", gap: 8, flexWrap: "wrap" }}>
                  <span style={{ fontSize: FONT.body, fontWeight: 600, color: COLOR.text1 }}>
                    {s.section || "建议"}
                  </span>
                  {s.urgency && (
                    <Tag color={URGENCY_COLOR(s.urgency)} bg={COLOR.bgCardAlt}>
                      {URGENCY_LABEL[s.urgency] || s.urgency}
                    </Tag>
                  )}
                  {s.intervention && (
                    <Tag color={COLOR.info} bg={COLOR.infoTint || COLOR.bgCardAlt}>
                      {s.intervention}
                    </Tag>
                  )}
                  {confidencePct && (
                    <span style={{ fontSize: FONT.xs, color: COLOR.text3, fontFamily: FONT_STACK.mono }}>
                      置信 {confidencePct}
                    </span>
                  )}
                </div>
                <Tag color={decisionColor} bg={COLOR.bgCardAlt}>
                  {decisionLabel}
                  {s.decided_at ? ` · ${fmtRelative(s.decided_at)}` : ""}
                </Tag>
              </div>
              {/* Headline content */}
              {s.content && (
                <div style={{ fontSize: FONT.sm, color: COLOR.text1, marginTop: 8, whiteSpace: "pre-wrap" }}>
                  {s.content}
                </div>
              )}
              {/* Detailed reasoning */}
              {s.detail && s.detail !== s.content && (
                <div
                  style={{
                    fontSize: FONT.sm,
                    color: COLOR.text2,
                    marginTop: 8,
                    paddingLeft: 10,
                    borderLeft: `2px solid ${COLOR.borderSubtle}`,
                    whiteSpace: "pre-wrap",
                  }}
                >
                  {s.detail}
                </div>
              )}
              <div style={{ fontSize: FONT.xs, color: COLOR.text3, marginTop: 8 }}>
                生成于 {fmtRelative(s.created_at)}
              </div>
            </div>
          );
        })
      )}
    </SectionCard>
  );
}

// ── Main component ─────────────────────────────────────────────────────────

export default function AdminPatientDetailV3({ patientId }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!patientId) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchAdminJson(`/api/admin/patients/${encodeURIComponent(patientId)}/related`)
      .then((d) => {
        if (cancelled) return;
        setData(d);
        setLoading(false);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(e.message || String(e));
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [patientId]);

  if (loading) return <SectionLoading />;
  if (error) return <SectionError message={error} />;
  if (!data?.profile) {
    return (
      <EmptyState
        icon="person_off"
        title="未找到该患者"
        desc="该 patient_id 不存在或已被清理"
      />
    );
  }

  return (
    <>
      <PatientHeader profile={data.profile} doctorId={data.profile.doctor_id} />
      <PatientKpiStrip data={data} />
      <RecordsSection items={data.records?.items || []} />
      <MessagesSection items={data.messages?.items || []} />
      <TasksSection items={data.tasks?.items || []} />
      <SuggestionsSection items={data.suggestions?.items || []} />
    </>
  );
}
