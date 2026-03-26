/**
 * DiagnosisCard — collapsible review card for a single AI diagnosis suggestion.
 *
 * Five visual states driven by `suggestion.decision`:
 *  1. null (unreviewed)  — gray left border, chevron icon
 *  2. "confirmed"        — green left border, "✓ 确认" label
 *  3. "rejected"         — gray left border, dimmed + strike-through, "✗ 排除"
 *  4. "edited"           — amber left border, "已改" badge
 *  5. "custom"           — dashed green border, "补充" badge
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
import { TYPE, COLOR } from "../../theme";

/* ── State-derived style maps ──────────────────────────────────────────────── */

const BORDER_BY_DECISION = {
  confirmed: `3px solid ${COLOR.primary}`,
  rejected:  `3px solid ${COLOR.border}`,
  edited:    `3px solid ${COLOR.warning}`,
  custom:    `3px dashed ${COLOR.primary}`,
};
const BORDER_DEFAULT = `3px solid ${COLOR.border}`;

const STATUS_LABEL = {
  confirmed: { text: "✓ 确认", color: COLOR.primary },
  rejected:  { text: "✗ 排除", color: COLOR.text4 },
  edited:    { text: "已改",   color: COLOR.warning },
  custom:    { text: "补充",   color: COLOR.primary },
};

/* ── Badge pill color logic ────────────────────────────────────────────────── */

function badgeColor(value) {
  if (value === "急诊") return COLOR.danger;
  if (value === "紧急") return COLOR.warning;
  return COLOR.text4;
}

/* ── Sub-components ────────────────────────────────────────────────────────── */

/** Outlined badge pill for confidence / urgency / intervention. */
function BadgePill({ value }) {
  if (!value) return null;
  const c = badgeColor(value);
  return (
    <Box
      component="span"
      sx={{
        fontSize: 10,
        fontWeight: 500,
        color: c,
        border: `0.5px solid ${c}`,
        px: "5px",
        py: 0,
        borderRadius: "3px",
        lineHeight: 1.6,
        whiteSpace: "nowrap",
        ml: 0.8,
        flexShrink: 0,
      }}
    >
      {value}
    </Box>
  );
}

/** Status label / chevron shown on the right side of the collapsed row. */
function RightIndicator({ decision, expanded }) {
  const status = STATUS_LABEL[decision];
  if (status) {
    return (
      <Typography
        component="span"
        sx={{
          fontSize: TYPE.micro.fontSize,
          fontWeight: 500,
          color: status.color,
          flexShrink: 0,
          ml: 1,
        }}
      >
        {status.text}
      </Typography>
    );
  }
  // Unreviewed — show chevron
  return (
    <Typography
      component="span"
      sx={{
        fontSize: TYPE.secondary.fontSize,
        color: COLOR.text4,
        flexShrink: 0,
        ml: 1,
        lineHeight: 1,
      }}
    >
      {expanded ? "▴" : "▾"}
    </Typography>
  );
}

/** Three-button action row: 排除 (left) | 修改 (middle) | 确认 (right) */
function ActionRow({ onConfirm, onReject, onEdit }) {
  const btnSx = {
    flex: 1,
    textAlign: "center",
    py: 1,
    fontSize: TYPE.secondary.fontSize,
    fontWeight: 500,
    cursor: "pointer",
    "&:active": { opacity: 0.6 },
  };
  return (
    <Box sx={{ display: "flex", borderTop: `0.5px solid ${COLOR.borderLight}` }}>
      <Box onClick={onReject} sx={{ ...btnSx, color: COLOR.text4 }}>
        ✗ 排除
      </Box>
      <Box sx={{ width: "0.5px", bgcolor: COLOR.borderLight }} />
      <Box onClick={onEdit} sx={{ ...btnSx, color: COLOR.accent }}>
        ✎ 修改
      </Box>
      <Box sx={{ width: "0.5px", bgcolor: COLOR.borderLight }} />
      <Box onClick={onConfirm} sx={{ ...btnSx, color: COLOR.primary }}>
        ✓ 确认
      </Box>
    </Box>
  );
}

/** Inline edit mode: textarea + save/cancel buttons. */
function EditMode({ initialText, onSave, onCancel }) {
  const [text, setText] = useState(initialText || "");
  return (
    <Box sx={{ px: 1.5, pb: 1.5 }}>
      <TextField
        multiline
        minRows={2}
        maxRows={6}
        fullWidth
        value={text}
        onChange={(e) => setText(e.target.value)}
        sx={{
          "& .MuiInputBase-root": {
            fontSize: TYPE.caption.fontSize,
            lineHeight: 1.5,
            p: 1,
          },
          "& .MuiOutlinedInput-notchedOutline": {
            borderColor: COLOR.border,
          },
        }}
      />
      <Box sx={{ display: "flex", gap: 1, mt: 1, alignItems: "center" }}>
        <Box
          onClick={onCancel}
          sx={{
            fontSize: TYPE.caption.fontSize,
            color: COLOR.text4,
            cursor: "pointer",
            px: 1.5,
            py: 0.5,
            "&:active": { opacity: 0.6 },
          }}
        >
          取消
        </Box>
        <Box sx={{ flex: 1 }} />
        <Box
          onClick={() => onSave(text)}
          sx={{
            fontSize: TYPE.caption.fontSize,
            color: COLOR.white,
            bgcolor: COLOR.accent,
            borderRadius: "4px",
            cursor: "pointer",
            px: 1.5,
            py: 0.5,
            "&:active": { opacity: 0.7 },
          }}
        >
          保存修改
        </Box>
      </Box>
    </Box>
  );
}

/** Inline reject confirmation: optional reason input. */
function RejectMode({ onSubmit, onCancel }) {
  const [reason, setReason] = useState("");
  return (
    <Box sx={{ px: 1.5, pb: 1.5 }}>
      <TextField
        fullWidth
        size="small"
        placeholder="排除理由（可选）"
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        sx={{
          "& .MuiInputBase-root": {
            fontSize: TYPE.caption.fontSize,
          },
          "& .MuiOutlinedInput-notchedOutline": {
            borderColor: COLOR.border,
          },
        }}
      />
      <Box sx={{ display: "flex", gap: 1, mt: 1, alignItems: "center" }}>
        <Box
          onClick={onCancel}
          sx={{
            fontSize: TYPE.caption.fontSize,
            color: COLOR.text4,
            cursor: "pointer",
            px: 1.5,
            py: 0.5,
            "&:active": { opacity: 0.6 },
          }}
        >
          取消
        </Box>
        <Box sx={{ flex: 1 }} />
        <Box
          onClick={() => onSubmit(reason)}
          sx={{
            fontSize: TYPE.caption.fontSize,
            color: COLOR.white,
            bgcolor: COLOR.text4,
            borderRadius: "4px",
            cursor: "pointer",
            px: 1.5,
            py: 0.5,
            "&:active": { opacity: 0.7 },
          }}
        >
          确认排除
        </Box>
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

  function handleConfirm(e) {
    e.stopPropagation();
    setMode(null);
    onDecide?.(id, "confirmed", {});
  }

  function handleRejectTap(e) {
    e.stopPropagation();
    setMode("reject");
  }

  function handleRejectSubmit(reason) {
    setMode(null);
    onDecide?.(id, "rejected", { reason: reason || undefined });
  }

  function handleEditTap(e) {
    e.stopPropagation();
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
      }}
    >
      {/* Collapsed header row — always visible */}
      <Box
        onClick={onToggle}
        sx={{
          display: "flex",
          alignItems: "center",
          minHeight: 44,
          px: 1.5,
          py: 0.8,
          cursor: "pointer",
          "&:active": { bgcolor: COLOR.surface },
          opacity: isRejected ? 0.5 : 1,
          textDecoration: isRejected ? "line-through" : "none",
        }}
      >
        {/* Content text */}
        <Typography
          sx={{
            flex: 1,
            minWidth: 0,
            fontSize: TYPE.secondary.fontSize,
            fontWeight: 500,
            color: COLOR.text2,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {content}
        </Typography>

        {/* Badge pill */}
        <BadgePill value={badgeValue} />

        {/* Right indicator (status label or chevron) */}
        <RightIndicator decision={effectiveDecision} expanded={expanded} />
      </Box>

      {/* Expanded panel */}
      {expanded && (
        <Box>
          {/* Reasoning / detail text */}
          {detail && mode === null && (
            <Box sx={{ px: 1.5, pb: 1 }}>
              <Typography
                sx={{
                  fontSize: TYPE.caption.fontSize,
                  color: COLOR.text3,
                  lineHeight: 1.5,
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
