/**
 * DiagnosisCard — collapsible review card for a single AI diagnosis suggestion.
 *
 * Five visual states driven by `suggestion.decision`:
 *  1. null (unreviewed)  — gray left border, "待处理"
 *  2. "confirmed"        — green left border, "已确认"
 *  3. "rejected"         — gray left border, dimmed + strike-through, "已排除"
 *  4. "edited"           — amber left border, "已修改"
 *  5. "custom"           — green left border, "已补充"
 *
 * Props:
 *  - suggestion: { id, section, content, detail, confidence, urgency,
 *      intervention, decision, edited_text, reason, is_custom }
 *  - onDecide(suggestionId, decision, opts): callback for confirm/reject/edit
 *  - expanded: boolean — controlled expand state
 *  - onToggle(): toggle expand/collapse
 */
import { useState } from "react";
import { Box, Typography, TextField } from "@mui/material";
import { TYPE, BUTTON, COLOR } from "../../theme";
import InlineEditor from "../InlineEditor";

/* ── State-derived style maps ──────────────────────────────────────────────── */

const BORDER_BY_DECISION = {
  confirmed: `3px solid ${COLOR.primary}`,
  rejected:  `3px solid ${COLOR.border}`,
  edited:    `3px solid ${COLOR.warning}`,
  custom:    `3px solid ${COLOR.primary}`,
};

// Color-code by confidence/urgency so doctor can visually scan priority
const BORDER_BY_PRIORITY = {
  "高":   `3px solid #E8533F`,
  "紧急": `3px solid #E8533F`,
  "中":   `3px solid #e8833a`,
  "常规": `3px solid #e8833a`,
  "低":   `3px solid #ccc`,
  "观察": `3px solid #ccc`,
  "药物": `3px solid ${COLOR.primary}`,
};
const BORDER_DEFAULT = `3px solid ${COLOR.borderLight}`;

const STATUS_LABEL = {
  confirmed: { text: "已确认", color: COLOR.primary },
  rejected:  { text: "已排除", color: COLOR.text4 },
  edited:    { text: "已修改", color: COLOR.warning },
  custom:    { text: "已补充", color: COLOR.primary },
};

/* ── Badge pill color logic ────────────────────────────────────────────────── */

function badgeColor(value) {
  if (value === "急诊" || value === "紧急" || value === "高") return "#E8533F";
  if (value === "中" || value === "常规") return "#e8833a";
  if (value === "低" || value === "观察") return "#999";
  if (value === "药物") return COLOR.primary;
  return COLOR.text4;
}

/* ── Sub-components ────────────────────────────────────────────────────────── */

function MetaBadge({ value }) {
  if (!value) return null;
  const c = badgeColor(value);
  const bgMap = { "#E8533F": "#FFF1F0", "#e8833a": "#FFF7E6", "#999": "#f5f5f5" };
  const bg = bgMap[c] || "#f0faf4";
  return (
    <Box
      component="span"
      sx={{
        fontSize: 10,
        fontWeight: 500,
        color: c,
        bgcolor: bg,
        px: 0.8,
        py: 0.15,
        borderRadius: "3px",
        whiteSpace: "nowrap",
        flexShrink: 0,
        lineHeight: 1.4,
      }}
    >
      {value}
    </Box>
  );
}

/** Status label / chevron shown on the right side of the collapsed row. */
function RightIndicator({ decision, expanded }) {
  const status = STATUS_LABEL[decision];
  return (
    <Typography
      component="span"
      sx={{
        fontSize: TYPE.caption.fontSize,
        fontWeight: 400,
        color: expanded ? COLOR.text4 : (status?.color || COLOR.text4),
        flexShrink: 0,
        lineHeight: 1.4,
        whiteSpace: "nowrap",
      }}
    >
      {expanded ? "收起 ▴" : (status?.text || "待处理")}
    </Typography>
  );
}

function TextAction({ icon, label, color, onClick }) {
  return (
    <Box
      onClick={(e) => { e.stopPropagation(); onClick?.(); }}
      sx={{
        display: "inline-flex",
        alignItems: "center",
        gap: 0.45,
        minHeight: BUTTON.compactHeight,
        fontSize: BUTTON.compactFontSize,
        lineHeight: BUTTON.compactLineHeight,
        color,
        cursor: "pointer",
        whiteSpace: "nowrap",
        "&:active": { opacity: 0.55 },
      }}
    >
      <Box component="span" sx={{ fontSize: TYPE.caption.fontSize, lineHeight: 1 }}>
        {icon}
      </Box>
      {label}
    </Box>
  );
}

/** Three-button action row: 排除 (left) | 修改 (middle) | 确认 (right) */
function ActionRow({ onConfirm, onReject, onEdit }) {
  return (
    <Box sx={{ px: 2, pb: 1, display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 2.5 }}>
      <Typography component="span" onClick={(e) => { e.stopPropagation(); onEdit?.(); }}
        sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4, cursor: "pointer", "&:active": { opacity: 0.5 } }}>
        修改
      </Typography>
      <Typography component="span" onClick={(e) => { e.stopPropagation(); onReject?.(); }}
        sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4, cursor: "pointer", "&:active": { opacity: 0.5 } }}>
        排除
      </Typography>
      <Typography component="span" onClick={(e) => { e.stopPropagation(); onConfirm?.(); }}
        sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.primary, cursor: "pointer", fontWeight: 500, "&:active": { opacity: 0.5 } }}>
        确认
      </Typography>
    </Box>
  );
}

/** Inline edit mode — uses shared InlineEditor. */

/** Inline reject confirmation: optional reason input. */
function RejectMode({ onSubmit, onCancel }) {
  const [reason, setReason] = useState("");
  return (
    <Box sx={{ px: 2, pb: 1.25 }}>
      <TextField
        fullWidth
        size="small"
        placeholder="排除理由（可选）"
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        sx={{
          "& .MuiInputBase-root": {
            fontSize: TYPE.secondary.fontSize,
            bgcolor: COLOR.surfaceAlt,
          },
          "& .MuiOutlinedInput-notchedOutline": {
            borderColor: COLOR.border,
          },
        }}
      />
      <Box sx={{ mt: 0.75, display: "flex", justifyContent: "flex-end", gap: 2.2 }}>
        <TextAction icon="↩" label="返回" color={COLOR.text4} onClick={onCancel} />
        <TextAction icon="✗" label="确认排除" color={COLOR.danger} onClick={() => onSubmit(reason)} />
      </Box>
    </Box>
  );
}

/* ── Main component ────────────────────────────────────────────────────────── */

export default function DiagnosisCard({ suggestion, onDecide, expanded, onToggle }) {
  const [mode, setMode] = useState(null); // null | "edit" | "reject"

  if (!suggestion) return null;

  const { id, content, detail, confidence, urgency, intervention, decision, is_custom } = suggestion;

  // Resolve effective decision — is_custom without explicit decision shows as "custom"
  const effectiveDecision = decision || (is_custom ? "custom" : null);
  const isRejected = effectiveDecision === "rejected";

  // Determine which badge value to show (only one will be present)
  const badgeValue = confidence || urgency || intervention;

  // Color-code left border: by decision if reviewed, by priority if pending
  const borderLeft = BORDER_BY_DECISION[effectiveDecision]
    || BORDER_BY_PRIORITY[badgeValue]
    || BORDER_DEFAULT;

  /* ── Handlers ──────────────────────────────────────────────────────────── */

  function handleConfirm() {
    setMode(null);
    onDecide?.(id, "confirmed", {});
  }

  function handleRejectTap() {
    setMode("reject");
  }

  function handleRejectSubmit(reason) {
    setMode(null);
    onDecide?.(id, "rejected", { reason: reason || undefined });
  }

  function handleEditTap() {
    setMode("edit");
  }

  function handleEditSave(editedText) {
    setMode(null);
    onDecide?.(id, "edited", { edited_text: editedText });
  }

  function handleCancel() {
    setMode(null);
  }

  /* ── Render ────────────────────────────────────────────────────────────── */

  return (
    <Box
      sx={{
        borderLeft,
        bgcolor: COLOR.white,
        transition: "border-color 0.15s",
        borderTop: `0.5px solid ${COLOR.borderLight}`,
      }}
    >
      {/* Collapsed header row — always visible */}
      <Box
        onClick={onToggle}
        sx={{
          px: 2,
          py: 1.2,
          cursor: "pointer",
          "&:active": { bgcolor: COLOR.surface },
          opacity: isRejected ? 0.5 : 1,
        }}
      >
        <Box sx={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 1.5 }}>
          <Box sx={{ minWidth: 0, flex: 1 }}>
            <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap" }}>
              <Typography
                sx={{
                  fontSize: TYPE.action.fontSize,
                  fontWeight: 500,
                  color: COLOR.text1,
                  whiteSpace: "pre-wrap",
                  overflowWrap: "anywhere",
                  lineHeight: 1.45,
                  textDecoration: isRejected ? "line-through" : "none",
                }}
              >
                {content}
              </Typography>
              <MetaBadge value={badgeValue} />
            </Box>
          </Box>
          <RightIndicator decision={effectiveDecision} expanded={expanded} />
        </Box>
      </Box>

      {/* Expanded panel */}
      {expanded && (
        <Box>
          {/* Reasoning / detail text — tinted card for visual separation */}
          {detail && mode === null && (
            <Box sx={{ mx: 2, mb: 0.5, px: 1.5, py: 1, bgcolor: COLOR.surfaceAlt, borderRadius: "6px" }}>
              <Typography
                sx={{
                  fontSize: TYPE.body.fontSize,
                  color: COLOR.text2,
                  lineHeight: 1.65,
                  whiteSpace: "pre-wrap",
                }}
              >
                {suggestion.edited_text || detail}
              </Typography>
            </Box>
          )}

          {/* Mode: edit */}
          {mode === "edit" && (
            <Box sx={{ px: 2, pb: 1.25 }}>
              <InlineEditor
                value={suggestion.edited_text || detail || content}
                onSave={handleEditSave}
                onCancel={handleCancel}
              />
            </Box>
          )}

          {/* Mode: reject — reason input */}
          {mode === "reject" && (
            <RejectMode onSubmit={handleRejectSubmit} onCancel={handleCancel} />
          )}

          {/* Action buttons — shown only when no sub-mode is active */}
          {mode === null && (
            <ActionRow
              onConfirm={handleConfirm}
              onReject={handleRejectTap}
              onEdit={handleEditTap}
            />
          )}
        </Box>
      )}
    </Box>
  );
}
