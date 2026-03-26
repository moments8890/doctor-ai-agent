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

/* ── State-derived style maps ──────────────────────────────────────────────── */

const BORDER_BY_DECISION = {
  confirmed: `2px solid ${COLOR.primary}`,
  rejected:  `2px solid ${COLOR.border}`,
  edited:    `2px solid ${COLOR.warning}`,
  custom:    `2px solid ${COLOR.primary}`,
};
const BORDER_DEFAULT = `2px solid ${COLOR.borderLight}`;

const STATUS_LABEL = {
  confirmed: { text: "已确认", color: COLOR.primary },
  rejected:  { text: "已排除", color: COLOR.text4 },
  edited:    { text: "已修改", color: COLOR.warning },
  custom:    { text: "已补充", color: COLOR.primary },
};

/* ── Badge pill color logic ────────────────────────────────────────────────── */

function badgeColor(value) {
  if (value === "急诊") return COLOR.danger;
  if (value === "紧急") return COLOR.warning;
  if (value === "高") return COLOR.text3;
  if (value === "中") return COLOR.text4;
  if (value === "低") return COLOR.text4;
  return COLOR.text4;
}

/* ── Sub-components ────────────────────────────────────────────────────────── */

function MetaText({ value }) {
  if (!value) return null;
  const c = badgeColor(value);
  return (
    <Typography
      component="span"
      sx={{
        fontSize: TYPE.caption.fontSize,
        color: c,
        whiteSpace: "nowrap",
        flexShrink: 0,
        lineHeight: 1.4,
      }}
    >
      {value}
    </Typography>
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
    <Box sx={{ px: 2, pb: 1.2, display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 2.2 }}>
      <TextAction icon="✎" label="修改" color={COLOR.accent} onClick={onEdit} />
      <TextAction icon="✗" label="排除" color={COLOR.text4} onClick={onReject} />
      <TextAction icon="✓" label="确认" color={COLOR.primary} onClick={onConfirm} />
    </Box>
  );
}

/** Inline edit mode: textarea + save/cancel buttons. */
function EditMode({ initialText, onSave, onCancel }) {
  const [text, setText] = useState(initialText || "");
  return (
    <Box sx={{ px: 2, pb: 1.25 }}>
      <TextField
        multiline
        minRows={2}
        maxRows={6}
        fullWidth
        value={text}
        onChange={(e) => setText(e.target.value)}
        sx={{
          "& .MuiInputBase-root": {
            fontSize: TYPE.secondary.fontSize,
            lineHeight: 1.5,
            p: 1,
            bgcolor: COLOR.surfaceAlt,
          },
          "& .MuiOutlinedInput-notchedOutline": {
            borderColor: COLOR.border,
          },
        }}
      />
      <Box sx={{ mt: 0.75, display: "flex", justifyContent: "flex-end", gap: 2.2 }}>
        <TextAction icon="✗" label="取消" color={COLOR.text4} onClick={onCancel} />
        <TextAction icon="✓" label="保存" color={COLOR.primary} onClick={() => onSave(text)} />
      </Box>
    </Box>
  );
}

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

  const borderLeft = BORDER_BY_DECISION[effectiveDecision] || BORDER_DEFAULT;
  const isRejected = effectiveDecision === "rejected";

  // Determine which badge value to show (only one will be present)
  const badgeValue = confidence || urgency || intervention;

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
              <MetaText value={badgeValue} />
            </Box>
          </Box>
          <RightIndicator decision={effectiveDecision} expanded={expanded} />
        </Box>
      </Box>

      {/* Expanded panel */}
      {expanded && (
        <Box>
          {/* Reasoning / detail text */}
          {detail && mode === null && (
            <Box sx={{ px: 2, pb: 0.9 }}>
              <Typography
                sx={{
                  fontSize: TYPE.body.fontSize,
                  color: COLOR.text3,
                  lineHeight: 1.6,
                  whiteSpace: "pre-wrap",
                }}
              >
                {suggestion.edited_text || detail}
              </Typography>
            </Box>
          )}

          {/* Mode: edit */}
          {mode === "edit" && (
            <EditMode
              initialText={suggestion.edited_text || detail || content}
              onSave={handleEditSave}
              onCancel={handleCancel}
            />
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
