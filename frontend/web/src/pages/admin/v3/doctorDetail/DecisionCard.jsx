// DecisionCard — the core surface of the AI 与知识 tab.
// Mirrors `<div class="dc danger|info">` in
// docs/specs/2026-04-24-admin-modern-mockup-v3.html (lines ~919-1042 +
// the two example cards at lines ~1851-1981).
//
// Stable 4-block anatomy across BOTH variants (codex v3 critique:
// clinicians need a predictable card; only the *content* of the
// 医生处理 block changes by kind):
//   1. AI 观察    (visibility icon)
//   2. 依据       (menu_book icon)        → <KbCitation> rows
//   3. 触发规则   (priority_high icon)    → <RiskTagRow>
//   4. 医生处理   (stethoscope icon)      → prose | <Triptych>
//
// Variant rail (2px positioned bar on left edge):
//   kind="danger_signal" → COLOR.danger
//   kind="reply_suggestion" → COLOR.info
//
// Footer:
//   left:  outcome badge + who/when (st-* tinted pill)
//   right: secondary CTA "查看完整决策链 →" (danger) / "对比历史决策 →" (reply)
//
// Props:
//   card — output of toDecisionCards()[0]. See decisionCardData.js.

import { COLOR, FONT, FONT_STACK, RADIUS, SHADOW } from "../tokens";
import KbCitation from "./KbCitation";
import RiskTagRow from "./RiskTagRow";
import Triptych from "./Triptych";

const RAIL_BY_KIND = {
  danger_signal: COLOR.danger,
  reply_suggestion: COLOR.info,
};

const PAT_AV_BY_KIND = {
  danger_signal: { background: COLOR.dangerTint, color: COLOR.danger },
  reply_suggestion: { background: COLOR.infoTint, color: COLOR.info },
};

// st-* tokens from mockup line ~568 — same colors as timeline status chips.
const BADGE_BY_VARIANT = {
  accept:  { background: COLOR.brandTint,   color: COLOR.brand,   label: "医生确认" },
  edit:    { background: COLOR.infoTint,    color: COLOR.info,    label: "医生修改后采纳" },
  reject:  { background: COLOR.dangerTint,  color: COLOR.danger,  label: "医生拒绝" },
  pending: { background: COLOR.warningTint, color: COLOR.warning, label: "待处理" },
  done:    { background: COLOR.brandTint,   color: COLOR.brand,   label: "已完成" },
};

const blockLabelStyle = {
  fontSize: 10.5,
  letterSpacing: "0.14em",
  textTransform: "uppercase",
  color: COLOR.text3,
  fontWeight: 600,
  marginBottom: 5,
  display: "flex",
  alignItems: "center",
  gap: 6,
};

function BlockLabel({ icon, children }) {
  return (
    <div style={blockLabelStyle}>
      <span
        className="material-symbols-outlined"
        style={{ fontSize: 14, color: COLOR.text3 }}
      >
        {icon}
      </span>
      {children}
    </div>
  );
}

function DcText({ children, smaller }) {
  return (
    <div
      style={{
        fontSize: smaller ? FONT.base : 13.5,
        lineHeight: 1.55,
        color: COLOR.text1,
      }}
    >
      {children}
    </div>
  );
}

function OutcomeBadge({ variant }) {
  const v = BADGE_BY_VARIANT[variant] || BADGE_BY_VARIANT.pending;
  return (
    <span
      style={{
        fontSize: FONT.xs,
        fontWeight: 600,
        padding: "3px 10px",
        borderRadius: 999,
        background: v.background,
        color: v.color,
      }}
    >
      {v.label}
    </span>
  );
}

export default function DecisionCard({ card }) {
  if (!card) return null;
  const railColor = RAIL_BY_KIND[card.kind] || COLOR.info;
  const avStyle = PAT_AV_BY_KIND[card.kind] || PAT_AV_BY_KIND.reply_suggestion;
  const ctaLabel =
    card.kind === "reply_suggestion" ? "对比历史决策" : "查看完整决策链";

  return (
    <article
      style={{
        position: "relative",
        background: COLOR.bgCard,
        border: `1px solid ${COLOR.borderSubtle}`,
        borderRadius: RADIUS.lg,
        overflow: "hidden",
        boxShadow: SHADOW.s1,
        display: "flex",
        flexDirection: "column",
      }}
    >
      {/* 2px rail — positioned span (matches Panel.jsx convention) */}
      <span
        aria-hidden
        style={{
          position: "absolute",
          left: 0,
          top: 0,
          bottom: 0,
          width: 2,
          background: railColor,
        }}
      />

      {/* Head */}
      <header
        style={{
          padding: "14px 16px",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          borderBottom: `1px solid ${COLOR.borderSubtle}`,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div
            style={{
              width: 28,
              height: 28,
              borderRadius: "50%",
              display: "grid",
              placeItems: "center",
              fontSize: FONT.sm,
              fontWeight: 600,
              ...avStyle,
            }}
          >
            {card.patient?.initial || "·"}
          </div>
          <div>
            <div style={{ fontWeight: 600, fontSize: FONT.body, color: COLOR.text1 }}>
              {card.patient?.name || "—"}
            </div>
            <div
              style={{
                fontSize: FONT.xs,
                textTransform: "uppercase",
                letterSpacing: "0.12em",
                color: COLOR.text2,
                fontWeight: 600,
              }}
            >
              {card.sectionTag}
            </div>
          </div>
        </div>
        <span
          style={{
            fontFamily: FONT_STACK.mono,
            fontSize: 11.5,
            color: COLOR.text3,
          }}
        >
          {card.time}
        </span>
      </header>

      {/* Body — stable 4 blocks */}
      <div
        style={{
          padding: "14px 16px 16px",
          display: "flex",
          flexDirection: "column",
          gap: 12,
        }}
      >
        {/* 1. AI 观察 */}
        <div>
          <BlockLabel icon="visibility">AI 观察</BlockLabel>
          <DcText>{card.observation || "—"}</DcText>
        </div>

        {/* 2. 依据 */}
        <div>
          <BlockLabel icon="menu_book">依据</BlockLabel>
          {card.evidence && card.evidence.length > 0 ? (
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {card.evidence.map((e, i) => (
                <KbCitation
                  key={`${e.num ?? "kb"}-${i}`}
                  num={e.num}
                  title={e.title}
                  quote={e.quote}
                />
              ))}
            </div>
          ) : (
            <DcText smaller>暂无引用知识</DcText>
          )}
        </div>

        {/* 3. 触发规则 / 风险 */}
        <div>
          <BlockLabel icon="priority_high">触发规则 / 风险</BlockLabel>
          {card.risks && card.risks.length > 0 ? (
            <RiskTagRow risks={card.risks} />
          ) : (
            <DcText smaller>—</DcText>
          )}
        </div>

        {/* 4. 医生处理 — content varies by kind */}
        <div>
          <BlockLabel icon="stethoscope">医生处理</BlockLabel>
          {card.kind === "reply_suggestion" && card.outcome?.triptych ? (
            <Triptych
              aiDraft={card.outcome.triptych.aiDraft}
              sentVersion={card.outcome.triptych.sentVersion}
              reason={card.outcome.triptych.reason}
            />
          ) : (
            <DcText smaller>{card.outcome?.prose || "—"}</DcText>
          )}
        </div>
      </div>

      {/* Foot */}
      <footer
        style={{
          padding: "10px 16px",
          borderTop: `1px solid ${COLOR.borderSubtle}`,
          background: COLOR.bgCardAlt,
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 12.5 }}>
          <OutcomeBadge variant={card.outcome?.badge || "pending"} />
          {(card.outcome?.who || card.outcome?.when) && (
            <span style={{ color: COLOR.text2 }}>
              {card.outcome.who && (
                <b style={{ color: COLOR.text1, fontWeight: 500 }}>
                  {card.outcome.who}
                </b>
              )}
              {card.outcome.who && card.outcome.when && " · "}
              {card.outcome.when}
            </span>
          )}
        </div>
        <a
          style={{
            fontSize: 12.5,
            color: COLOR.info,
            cursor: "pointer",
            display: "inline-flex",
            alignItems: "center",
            gap: 4,
            fontWeight: 500,
          }}
        >
          {ctaLabel}
          <span className="material-symbols-outlined" style={{ fontSize: 14 }}>
            arrow_forward
          </span>
        </a>
      </footer>
    </article>
  );
}
