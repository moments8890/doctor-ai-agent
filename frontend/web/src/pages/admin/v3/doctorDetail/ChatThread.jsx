// ChatThread — right pane of the 沟通 tab. Renders a header (avatar + name +
// meta + tools), then a scrollable body that interleaves message bubbles, AI
// footnote cards, day tags, and adoption-trace lines.
//
// Mockup reference: docs/specs/2026-04-24-admin-modern-mockup-v3.html
//   `.chat-thread`, `.ct-head`, `.ct-tools`, `.ct-body`, `.day-tag`,
//   `.bubble.b-patient`, `.bubble.b-doctor`, `.bubble .stamp`
//
// TODO: wire AI-suggestion linkage. The /api/admin/doctors/{id}/related
// endpoint exposes `messages` and `suggestions` independently — there is no
// `ai_suggestion_id` field on PatientMessage yet, so the chat-thread cannot
// yet anchor real AI footnotes to specific bubbles. For now we render the
// real patient/doctor messages inline AND interleave a small set of demo
// AI footnote + adoption-trace entries so the visual contract is testable.
// Wire the real linkage once the backend exposes which AI suggestion fed
// which doctor reply (cross-reference via timestamps + same patient_id).

import { useMemo } from "react";
import AiFootnoteCard from "./AiFootnoteCard";
import AdoptionTrace from "./AdoptionTrace";
import { COLOR, FONT, FONT_STACK } from "../tokens";

// ── helpers ────────────────────────────────────────────────────────────────

function parseTs(ts) {
  if (!ts) return null;
  const d = new Date(ts);
  return Number.isNaN(d.getTime()) ? null : d;
}

function formatStamp(d) {
  if (!d) return "";
  return `${String(d.getHours()).padStart(2, "0")}:${String(
    d.getMinutes(),
  ).padStart(2, "0")}`;
}

function formatDayTag(d) {
  if (!d) return "";
  const now = new Date();
  const sameDay = d.toDateString() === now.toDateString();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  const weekdays = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"];
  if (sameDay) return `今天 · ${m} 月 ${dd} 日`;
  return `${m} 月 ${dd} 日 · ${weekdays[d.getDay()]}`;
}

function dayKey(d) {
  if (!d) return "";
  return d.toDateString();
}

// ── header ─────────────────────────────────────────────────────────────────

function ThreadHeader({ patient }) {
  const initial = (patient?.name || "?").trim().charAt(0) || "?";
  const sub = [
    patient?.gender,
    patient?.age != null ? `${patient.age} 岁` : null,
  ]
    .filter(Boolean)
    .join(" · ");
  const meta = [
    patient?.diagnosis,
    patient?.message_count != null ? `${patient.message_count} 条消息` : null,
    patient?.last_visit ? `上次回访 ${patient.last_visit}` : null,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <div
      style={{
        height: 56,
        padding: "0 18px",
        borderBottom: `1px solid ${COLOR.borderSubtle}`,
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        flexShrink: 0,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <div
          style={{
            width: 30,
            height: 30,
            borderRadius: "50%",
            background: COLOR.brand,
            color: "#fff",
            display: "grid",
            placeItems: "center",
            fontSize: 12,
            fontWeight: 600,
          }}
        >
          {initial}
        </div>
        <div>
          <div style={{ fontSize: 15, fontWeight: 600, color: COLOR.text1 }}>
            {patient?.name || "未命名患者"}
            {sub && (
              <span
                style={{
                  fontSize: 13,
                  color: COLOR.text2,
                  fontWeight: 400,
                  marginLeft: 6,
                }}
              >
                · {sub}
              </span>
            )}
          </div>
          {meta && (
            <div style={{ fontSize: 12, color: COLOR.text2, marginTop: 1 }}>
              {meta}
            </div>
          )}
        </div>
      </div>
      {/* Right-side icon buttons (search / more_horiz) removed — they had
          no onClick handlers and no destinations behind them. Restore once
          message search and per-thread actions actually ship. */}
    </div>
  );
}

// ── bubbles ────────────────────────────────────────────────────────────────

function Bubble({ role, text, stamp }) {
  const isDoctor = role === "doctor";
  return (
    <div
      style={{
        alignSelf: isDoctor ? "flex-end" : "flex-start",
        maxWidth: "64%",
        padding: "10px 14px",
        fontSize: 14,
        lineHeight: 1.55,
        position: "relative",
        display: "flex",
        flexDirection: "column",
        gap: 4,
        background: isDoctor ? COLOR.brand : COLOR.bgCard,
        color: isDoctor ? "#fff" : COLOR.text1,
        border: isDoctor ? "none" : `1px solid ${COLOR.borderSubtle}`,
        borderRadius: isDoctor ? "12px 12px 4px 12px" : "12px 12px 12px 4px",
      }}
    >
      <div style={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}>{text}</div>
      {stamp && (
        <span
          style={{
            fontFamily: FONT_STACK.mono,
            fontSize: 10.5,
            color: isDoctor ? "rgba(255,255,255,0.75)" : COLOR.text3,
            alignSelf: "flex-end",
          }}
        >
          {stamp}
        </span>
      )}
    </div>
  );
}

function DayTag({ label }) {
  return (
    <span
      style={{
        alignSelf: "center",
        fontSize: 11,
        letterSpacing: "0.12em",
        textTransform: "uppercase",
        color: COLOR.text3,
        background: COLOR.bgCard,
        padding: "3px 12px",
        borderRadius: 999,
        border: `1px solid ${COLOR.borderSubtle}`,
        fontWeight: 600,
      }}
    >
      {label}
    </span>
  );
}

// ── thread builder ─────────────────────────────────────────────────────────

function buildThreadItems(realMessages) {
  // Convert raw messages → ordered ascending list of bubble entries with
  // synthetic day-tag boundaries between consecutive different-day items.
  const bubbles = (realMessages || [])
    .filter((m) => m && (m.direction === "inbound" || m.direction === "outbound"))
    .map((m) => ({
      kind: "bubble",
      role: m.direction === "outbound" ? "doctor" : "patient",
      text: m.content || "",
      ts: parseTs(m.created_at),
      _id: m.id,
    }))
    .sort((a, b) => {
      if (!a.ts) return -1;
      if (!b.ts) return 1;
      return a.ts.getTime() - b.ts.getTime();
    });

  const items = [];
  let lastDay = null;
  for (const b of bubbles) {
    const k = dayKey(b.ts);
    if (k !== lastDay) {
      items.push({ kind: "day", label: formatDayTag(b.ts), _key: `day-${k}` });
      lastDay = k;
    }
    items.push({ ...b, stamp: formatStamp(b.ts) });
  }
  return items;
}

// ── demo seam ──────────────────────────────────────────────────────────────
// While AI-suggestion linkage is unwired, append a small didactic block at
// the end of the thread that exercises the AI footnote + adoption trace
// visual contract. This is the part of the screen that needs human review.
// Remove when wiring completes.
function DemoAiFootnoteShowcase() {
  return (
    <>
      <DayTag label="示例 · AI 脚注样式" />
      <Bubble
        role="patient"
        text="医生，最近血压一直在 145/95 左右，早起还会头晕，需要调药吗？我现在吃的是氨氯地平 5mg。"
        stamp="14:38"
      />
      <AiFootnoteCard
        kind="draft"
        summary={
          <>
            <b>建议：</b>氨氯地平 5→10 mg/日；2 周后复测；监测起立性低血压。
          </>
        }
        body="陈阿姨您好。根据近 7 日 145/95 平均血压（未达标）+ 上次尿微量白蛋白 28 mg/L 的化验结果，建议先把氨氯地平加到 10 mg。两周后复测，如仍不达标，再考虑加用 ACEI。早起头晕注意起床动作放慢，监测站立时血压偏低。"
        sources={[
          { id: "kb-12", label: "[KB-12] 高血压调药梯度" },
          { id: "kb-23", label: "[KB-23] 老年起立性低血压" },
          { id: "rule-1", label: "王医生 · 内部规则" },
        ]}
      />
      <Bubble
        role="doctor"
        text="陈阿姨好，您先把氨氯地平加到 10mg/日，两周后我们再测一次。早上起床动作放慢一些，监测有没有站起来头晕的情况。两周后如果还不达标，我们再加一个药。"
        stamp="14:46"
      />
      <AdoptionTrace
        mode="edit"
        summary="采纳 ≈ 70% · 加入了起立性低血压的具体描述"
      />
      <AiFootnoteCard
        kind="analysis"
        summary="尿微量白蛋白 28 mg/L 轻度升高 · 7d 血压均值 145/93 未达标 · 建议调药。"
      />
    </>
  );
}

// ── main ───────────────────────────────────────────────────────────────────

export default function ChatThread({ patient, messages }) {
  const items = useMemo(() => buildThreadItems(messages), [messages]);

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        background: COLOR.bgCard,
        minWidth: 0,
        minHeight: 0,
      }}
    >
      <ThreadHeader patient={patient} />
      <div
        style={{
          flex: 1,
          overflowY: "auto",
          padding: "18px 22px",
          display: "flex",
          flexDirection: "column",
          gap: 12,
          background: COLOR.bgCardAlt,
        }}
      >
        {items.length === 0 && (
          <div
            style={{
              alignSelf: "center",
              fontSize: FONT.sm,
              color: COLOR.text3,
              padding: "24px 0",
            }}
          >
            暂无消息
          </div>
        )}
        {items.map((it, idx) => {
          if (it.kind === "day") return <DayTag key={it._key || idx} label={it.label} />;
          return (
            <Bubble
              key={it._id ?? idx}
              role={it.role}
              text={it.text}
              stamp={it.stamp}
            />
          );
        })}
        {/* Demo footnote/trace block (see TODO above) */}
        <DemoAiFootnoteShowcase />
      </div>
    </div>
  );
}
