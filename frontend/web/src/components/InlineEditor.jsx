/**
 * InlineEditor — shared inline textarea with auto-resize and action buttons.
 *
 * Used by DiagnosisCard (edit suggestion) and KnowledgeSubpage (edit item).
 * Shows a textarea with optional delete on the left, cancel + save on the right.
 * Includes a mic button for voice input when the browser supports it.
 */
import { useState, useRef, useEffect } from "react";
import { Box, Typography } from "@mui/material";
import { TYPE, COLOR, RADIUS } from "../theme";

export default function InlineEditor({ value, onSave, onCancel, onDelete }) {
  const [text, setText] = useState(value);
  const ref = useRef(null);

  useEffect(() => {
    if (ref.current) {
      ref.current.focus();
      ref.current.style.height = "auto";
      ref.current.style.height = ref.current.scrollHeight + "px";
    }
  }, []);

  function handleChange(e) {
    setText(e.target.value);
    e.target.style.height = "auto";
    e.target.style.height = e.target.scrollHeight + "px";
  }

  const isDirty = text.trim() !== value;

  return (
    <Box>
      <Box sx={{ display: "flex", gap: 0.5, alignItems: "flex-start" }}>
        <Box component="textarea" ref={ref} value={text} onChange={handleChange}
          sx={{
            flex: 1, boxSizing: "border-box", fontFamily: "inherit",
            fontSize: TYPE.body.fontSize, color: COLOR.text2, lineHeight: 1.55,
            p: 1, border: `1px solid ${COLOR.primary}`, borderRadius: RADIUS.sm,
            bgcolor: COLOR.surfaceAlt, resize: "none", overflow: "hidden", outline: "none",
          }}
          rows={1}
        />
      </Box>
      <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", mt: 1 }}>
        {onDelete ? (
          <Typography onClick={onDelete}
            sx={{ fontSize: TYPE.body.fontSize, color: COLOR.danger, cursor: "pointer", "&:active": { opacity: 0.5 } }}>
            删除
          </Typography>
        ) : (
          <Box />
        )}
        <Typography onClick={onCancel}
          sx={{ fontSize: TYPE.body.fontSize, color: COLOR.text3, cursor: "pointer", "&:active": { opacity: 0.5 } }}>
          取消
        </Typography>
        <Typography onClick={isDirty ? () => onSave(text.trim()) : undefined}
          sx={{
            fontSize: TYPE.body.fontSize, fontWeight: isDirty ? 500 : 400,
            color: isDirty ? COLOR.primary : COLOR.text4,
            cursor: isDirty ? "pointer" : "default",
            "&:active": isDirty ? { opacity: 0.5 } : {},
          }}>
          保存
        </Typography>
      </Box>
    </Box>
  );
}
