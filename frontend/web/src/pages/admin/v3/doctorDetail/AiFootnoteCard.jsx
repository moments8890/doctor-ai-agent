// AiFootnoteCard — the high-stakes component of the 沟通 tab.
//
// Renders the "AI 解析 · 不发送" / "AI 起草 · 待医生处理" footnote that hangs off
// a real chat bubble. The visual contract is rigorous on purpose — this card
// must NEVER be confused for a real outbound message at scroll speed.
//
// Mockup reference: docs/specs/2026-04-24-admin-modern-mockup-v3.html
//   `.ai-anchor`, `.ai-bracket`, `.ai-card`, `.ai-card.expanded`
//
// Critical invariants (codex v3 review):
//   1. The card keeps `infoTint` background AND dashed border in BOTH
//      collapsed and expanded states. Do NOT switch to white/solid when
//      expanded — that's what makes it look like an outbound bubble.
//   2. Drafts (`kind="draft"`) default to expanded. Analysis defaults to
//      collapsed.
//   3. Click anywhere on the card toggles expansion.
//   4. Smaller font than message bubbles: 11px header label, 11.5px summary,
//      12.5px body — adds another not-a-bubble cue.
//
// Props:
//   kind:    "analysis" | "draft"
//   summary: string  — single-line teaser shown in both states
//   body:    string  — full text revealed on expand
//   sources: Array<{ id, label }>  — source chips, e.g. KB-12 / 内部规则
//
// The bracket connector visually anchors the card to the message above it.
// Implemented as an absolutely-spec'd flex sibling to keep the card-only
// click target intact.

import { useState } from "react";
import { COLOR, FONT_STACK } from "../tokens";

const LABEL = {
  analysis: "AI 解析 · 不发送",
  draft:    "AI 起草 · 待医生处理",
};

function Bracket() {
  // Mirrors `.ai-bracket` — 14px-wide L-shape on the card's left edge,
  // anchoring it visually under the bubble above.
  return (
    <div
      aria-hidden
      style={{
        width: 14,
        borderLeft: `2px solid ${COLOR.info}`,
        borderTop: `2px solid ${COLOR.info}`,
        borderBottom: `2px solid ${COLOR.info}`,
        borderRadius: "0 0 0 6px",
        marginRight: 6,
        flexShrink: 0,
        opacity: 0.5,
      }}
    />
  );
}

function HeaderLine({ kind, expanded }) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 6,
        fontSize: 11,
        fontWeight: 600,
        color: COLOR.info,
        letterSpacing: "0.08em",
        textTransform: "uppercase",
      }}
    >
      <span className="material-symbols-outlined" style={{ fontSize: 13 }}>
        network_intelligence
      </span>
      {LABEL[kind] || LABEL.analysis}
      <span style={{ flex: 1 }} />
      <span
        style={{
          fontSize: 10.5,
          color: COLOR.text2,
          fontWeight: 500,
          letterSpacing: 0,
          textTransform: "none",
          display: "inline-flex",
          alignItems: "center",
          gap: 2,
        }}
      >
        {expanded ? "收起" : "展开"}
        <span className="material-symbols-outlined" style={{ fontSize: 14 }}>
          {expanded ? "expand_less" : "expand_more"}
        </span>
      </span>
    </div>
  );
}

function SourceChips({ sources }) {
  if (!Array.isArray(sources) || sources.length === 0) return null;
  return (
    <div
      style={{
        marginTop: 8,
        display: "flex",
        flexWrap: "wrap",
        gap: 4,
      }}
    >
      {sources.map((s, idx) => (
        <span
          key={s?.id ?? idx}
          style={{
            fontSize: 10.5,
            padding: "1px 7px",
            border: `1px solid ${COLOR.borderDefault}`,
            borderRadius: 999,
            background: COLOR.bgCard,
            color: COLOR.text2,
            fontFamily: s?.label?.startsWith?.("[KB-") ? FONT_STACK.mono : undefined,
          }}
        >
          {s?.label ?? s?.id ?? ""}
        </span>
      ))}
    </div>
  );
}

export default function AiFootnoteCard({ kind = "analysis", summary, body, sources }) {
  const [expanded, setExpanded] = useState(kind === "draft");

  return (
    <div
      style={{
        alignSelf: "flex-end",
        display: "flex",
        alignItems: "stretch",
        maxWidth: 360,
        marginTop: -2,
      }}
    >
      <Bracket />
      <div
        onClick={() => setExpanded((v) => !v)}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            setExpanded((v) => !v);
          }
        }}
        style={{
          flex: 1,
          // CRITICAL: infoTint + dashed must persist in expanded state.
          background: COLOR.infoTint,
          border: `1px dashed ${COLOR.info}`,
          borderRadius: 6,
          padding: "7px 10px",
          fontSize: 12,
          color: COLOR.text2,
          cursor: "pointer",
          minWidth: 0,
        }}
      >
        <HeaderLine kind={kind} expanded={expanded} />

        {summary && (
          <div
            style={{
              fontSize: 11.5,
              color: expanded ? COLOR.text1 : COLOR.text2,
              marginTop: 3,
              // Collapsed: single-line clamp. Expanded: wraps so callers can
              // put a richer "建议:" line in summary when kind="draft".
              overflow: expanded ? "visible" : "hidden",
              textOverflow: expanded ? "clip" : "ellipsis",
              whiteSpace: expanded ? "normal" : "nowrap",
            }}
          >
            {summary}
          </div>
        )}

        {expanded && body && (
          <div
            style={{
              marginTop: 8,
              paddingTop: 8,
              borderTop: `1px dashed ${COLOR.borderSubtle}`,
              fontSize: 12.5,
              lineHeight: 1.55,
              color: COLOR.text1,
            }}
          >
            {body}
          </div>
        )}

        {expanded && <SourceChips sources={sources} />}
      </div>
    </div>
  );
}
