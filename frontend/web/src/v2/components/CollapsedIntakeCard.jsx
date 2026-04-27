/**
 * CollapsedIntakeCard — single-row summary that stands in for a confirmed
 * intake transcript inside the patient ChatTab. Tap to expand the full
 * transcript inline (component-local state, no navigation).
 *
 * Default state: ✓ 已提交问诊 · {N}轮 · {chief_complaint} + 查看 ›
 * Expanded:      same row + the original messages rendered above it via
 *                the renderMessage callback the parent already uses.
 *
 * Styling follows the v2 card pattern from CLAUDE.md (white card on gray
 * bg, RADIUS.lg, no hard border, FONT/ICON tokens only).
 */

import { useState } from "react";
import CheckCircleOutlinedIcon from "@mui/icons-material/CheckCircleOutlined";
import CancelOutlinedIcon from "@mui/icons-material/CancelOutlined";
import HistoryOutlinedIcon from "@mui/icons-material/HistoryOutlined";
import AccessTimeOutlinedIcon from "@mui/icons-material/AccessTimeOutlined";
import ExpandMoreOutlinedIcon from "@mui/icons-material/ExpandMoreOutlined";
import ExpandLessOutlinedIcon from "@mui/icons-material/ExpandLessOutlined";
import { APP, FONT, ICON, RADIUS } from "../theme";

const STATUS_PRESET = {
  confirmed: { Icon: CheckCircleOutlinedIcon, color: "primary", label: "已提交问诊" },
  abandoned: { Icon: CancelOutlinedIcon, color: "text4", label: "已取消问诊" },
  expired:   { Icon: AccessTimeOutlinedIcon, color: "text4", label: "问诊已过期" },
  reviewing: { Icon: CheckCircleOutlinedIcon, color: "primary", label: "已提交问诊" },
};
const FALLBACK_PRESET = { Icon: HistoryOutlinedIcon, color: "text4", label: "历史问诊" };

function deriveSummary(messages) {
  // Turn count = number of patient (user) messages in this run. Each user
  // message is a "round" from the patient's perspective.
  const turnCount = (messages || []).filter((m) => {
    const src = m.source || (m.role === "user" ? "patient" : "ai");
    return src === "patient";
  }).length;

  // Chief complaint hint: first patient message, truncated. Cheaper than
  // joining intake_sessions.collected, and good enough for a one-line
  // summary. If no patient message (shouldn't happen, but defensive),
  // fall back to the first AI prompt.
  const firstPatient = (messages || []).find((m) => {
    const src = m.source || (m.role === "user" ? "patient" : "ai");
    return src === "patient";
  });
  const fallback = (messages || [])[0];
  const raw = (firstPatient || fallback || {}).content || "";
  const trimmed = String(raw).trim();
  const summary = trimmed.length > 24 ? trimmed.slice(0, 24) + "…" : trimmed;

  return { turnCount, summary };
}

export default function CollapsedIntakeCard({ messages, renderMessage, status }) {
  const [expanded, setExpanded] = useState(false);
  const { turnCount, summary } = deriveSummary(messages);
  const preset = STATUS_PRESET[status] || FALLBACK_PRESET;
  const { Icon, label } = preset;
  const iconColor = preset.color === "primary" ? APP.primary : APP.text4;

  return (
    <div style={styles.wrap}>
      {expanded && (
        <div style={styles.transcript}>
          {messages.map((m, i) => renderMessage(m, i))}
        </div>
      )}
      <div
        role="button"
        tabIndex={0}
        aria-label={expanded ? "收起问诊记录" : "展开问诊记录"}
        onClick={() => setExpanded((e) => !e)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            setExpanded((v) => !v);
          }
        }}
        style={styles.card}
      >
        <Icon
          sx={{ fontSize: ICON.sm, color: iconColor, flexShrink: 0 }}
        />
        <span style={styles.text}>
          {label}
          {turnCount > 0 ? ` · ${turnCount}轮` : ""}
          {summary ? ` · ${summary}` : ""}
        </span>
        <span style={styles.action}>
          {expanded ? "收起" : "查看"}
          {expanded ? (
            <ExpandLessOutlinedIcon
              sx={{ fontSize: ICON.xs, marginLeft: "2px" }}
            />
          ) : (
            <ExpandMoreOutlinedIcon
              sx={{ fontSize: ICON.xs, marginLeft: "2px" }}
            />
          )}
        </span>
      </div>
    </div>
  );
}

const styles = {
  wrap: {
    margin: "8px 12px",
  },
  transcript: {
    background: APP.surface,
    borderRadius: RADIUS.lg,
    padding: "10px 0",
    marginBottom: 6,
  },
  card: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    background: APP.surface,
    borderRadius: RADIUS.lg,
    padding: "12px 14px",
    minHeight: 44,
    cursor: "pointer",
    userSelect: "none",
  },
  text: {
    flex: 1,
    minWidth: 0,
    fontSize: FONT.sm,
    color: APP.text2,
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
  },
  action: {
    display: "inline-flex",
    alignItems: "center",
    fontSize: FONT.sm,
    color: APP.primary,
    flexShrink: 0,
  },
};
