/**
 * FieldReviewCard — unified component for field-level review and confirmation.
 *
 * Two modes:
 *  1. Carry-forward: confirm or dismiss fields from a prior visit record.
 *  2. Import preview: confirm or inline-edit fields extracted from photo/PDF/voice.
 *
 * Features:
 *  - Collapsible (▾/▴) — collapsed by default
 *  - Per-item: dismiss/edit (left) | confirm (right) — lightweight inline action row
 *  - Footer: dismiss all (left) | confirm all (right)
 *  - Edit mode: cancel (left) | save (right)
 */
import { useState, useRef, useEffect } from "react";
import { Box, Typography } from "@mui/material";
import { TYPE, BUTTON, COLOR, RADIUS } from "../../theme";
import AppButton from "../AppButton";

function InlineActionBar({ actions }) {
  return (
    <Box
      sx={{
        display: "flex",
        alignItems: "center",
        justifyContent: "flex-end",
        gap: 2,
      }}
    >
      {actions.map(({ key, icon, label, color, onClick, disabled }) => (
        <Box
          key={key}
          onClick={!disabled ? onClick : undefined}
          sx={{
            minHeight: BUTTON.compactHeight - 4,
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "flex-end",
            gap: 0.5,
            fontSize: BUTTON.compactFontSize,
            lineHeight: BUTTON.compactLineHeight,
            fontWeight: 500,
            color: disabled ? COLOR.text4 : color,
            cursor: disabled ? "default" : "pointer",
            opacity: disabled ? 0.45 : 1,
            "&:active": !disabled ? { opacity: 0.6 } : {},
          }}
        >
          {icon && (
            <Box
              component="span"
              sx={{ fontSize: TYPE.caption.fontSize, lineHeight: 1, flexShrink: 0 }}
            >
              {icon}
            </Box>
          )}
          {label}
        </Box>
      ))}
    </Box>
  );
}

export default function FieldReviewCard({
  title,
  subtitle,
  items,
  confirmLabel = "沿用",
  dismissLabel = "忽略",
  confirmAllLabel = "全部沿用",
  dismissAllLabel = "全部忽略",
  onConfirm,
  onDismiss,
  onEdit,
  onConfirmAll,
  onDismissAll,
  disabled = false,
  editable = false,
  defaultCollapsed = true,
}) {
  const [collapsed, setCollapsed] = useState(defaultCollapsed);
  const [editingField, setEditingField] = useState(null);
  const [editValue, setEditValue] = useState("");
  const textareaRef = useRef(null);

  useEffect(() => {
    if (editingField !== null && textareaRef.current) {
      const el = textareaRef.current;
      el.focus();
      el.setSelectionRange(el.value.length, el.value.length);
    }
  }, [editingField]);

  if (!items || items.length === 0) return null;

  const handleStartEdit = (item) => { setEditingField(item.field); setEditValue(item.value || ""); };
  const handleCancelEdit = () => { setEditingField(null); setEditValue(""); };
  const handleSaveEdit = (field) => { if (onEdit) onEdit(field, editValue); setEditingField(null); setEditValue(""); };

  const handleTextareaChange = (e) => {
    setEditValue(e.target.value);
    e.target.style.height = "auto";
    e.target.style.height = e.target.scrollHeight + "px";
  };

  return (
    <Box sx={{
      mt: 1,
      bgcolor: COLOR.white,
      borderTop: `0.5px solid ${COLOR.border}`,
      borderBottom: `0.5px solid ${COLOR.border}`,
      overflow: "hidden",
    }}>
      {/* Header — tappable to toggle */}
      <Box onClick={() => setCollapsed(!collapsed)} sx={{
        display: "flex", alignItems: "flex-start", justifyContent: "space-between",
        px: 2, py: 1, cursor: "pointer",
        "&:active": { bgcolor: COLOR.surface },
      }}>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography sx={{ fontSize: TYPE.action.fontSize, fontWeight: 500, color: COLOR.text1 }}>
            {title}
          </Typography>
          {subtitle && (
            <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4, mt: 0.5 }}>
              {subtitle}
            </Typography>
          )}
        </Box>
        <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4, flexShrink: 0, ml: 1, textAlign: "right", lineHeight: 1.4, pt: 0.15 }}>
          {collapsed ? "展开 ▾" : "收起 ▴"}
        </Typography>
      </Box>

      {/* Collapsible content */}
      {!collapsed && (
        <Box>
          {/* Per-field rows */}
          {items.map((item) => {
            const isEditing = editingField === item.field;

            return (
              <Box key={item.field} sx={{ px: 2, py: 1, borderTop: `0.5px solid ${COLOR.borderLight}` }}>
                {isEditing ? (
                  /* ── Edit mode ── */
                  <Box>
                    <Typography sx={{ fontSize: TYPE.caption.fontSize, fontWeight: 500, color: COLOR.text4, mb: 0.35 }}>
                      {item.label}
                    </Typography>
                    <Box
                      component="textarea"
                      ref={textareaRef}
                      value={editValue}
                      onChange={handleTextareaChange}
                      sx={{
                        width: "100%", boxSizing: "border-box", fontFamily: "inherit",
                        fontSize: TYPE.body.fontSize, color: COLOR.text2, lineHeight: 1.5,
                        p: 1, border: `1px solid ${COLOR.border}`, borderRadius: RADIUS.sm, bgcolor: COLOR.surfaceAlt,
                        resize: "none", overflow: "hidden", outline: "none",
                        "&:focus": { borderColor: COLOR.primary },
                      }}
                      rows={1}
                      onFocus={(e) => { e.target.style.height = "auto"; e.target.style.height = e.target.scrollHeight + "px"; }}
                    />
                    <Box sx={{ mt: 1 }}>
                      <InlineActionBar
                        actions={[
                          { key: "cancel", icon: "✗", label: "取消", color: COLOR.text4, onClick: handleCancelEdit },
                          { key: "save", icon: "✓", label: "保存", color: COLOR.primary, onClick: () => handleSaveEdit(item.field) },
                        ]}
                      />
                    </Box>
                  </Box>
                ) : (
                  /* ── Display mode ── */
                  <Box sx={{ display: "grid", gap: 1 }}>
                    <Box sx={{ minWidth: 0 }}>
                      <Typography sx={{ fontSize: TYPE.caption.fontSize, fontWeight: 500, color: COLOR.text4, mb: 0.2 }}>
                        {item.label}
                      </Typography>
                      <Typography sx={{ fontSize: TYPE.body.fontSize, color: COLOR.text2, whiteSpace: "pre-wrap", overflowWrap: "anywhere", lineHeight: 1.55 }}>
                        {item.value}
                      </Typography>
                    </Box>
                    <Box sx={{ mt: 0.5 }}>
                      <InlineActionBar
                        actions={[
                          {
                            key: "left",
                            icon: editable ? "✎" : "✗",
                            label: editable ? "编辑" : dismissLabel,
                            color: editable ? COLOR.accent : COLOR.text4,
                            disabled,
                            onClick: () => editable ? handleStartEdit(item) : onDismiss?.(item.field),
                          },
                          {
                            key: "confirm",
                            icon: "✓",
                            label: confirmLabel,
                            color: COLOR.primary,
                            disabled,
                            onClick: () => onConfirm?.(item.field),
                          },
                        ]}
                      />
                    </Box>
                  </Box>
                )}
              </Box>
            );
          })}

          {/* Footer: dismiss all (left) | confirm all (right) */}
          {items.length > 1 && (
            <Box sx={{ px: 2, pt: 1, pb: 1.5, borderTop: `0.5px solid ${COLOR.borderLight}`, display: "grid", gap: 0.5, gridTemplateColumns: "repeat(2, minmax(0, 1fr))" }}>
              <AppButton variant="secondary" size="sm" fullWidth disabled={disabled} onClick={onDismissAll}>
                {dismissAllLabel}
              </AppButton>
              <AppButton variant="primary" size="sm" fullWidth disabled={disabled} onClick={onConfirmAll}>
                {confirmAllLabel}
              </AppButton>
            </Box>
          )}
        </Box>
      )}
    </Box>
  );
}
