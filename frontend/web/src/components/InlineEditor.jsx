/**
 * InlineEditor — shared inline textarea with auto-resize and action buttons.
 *
 * Used by DiagnosisCard (edit suggestion) and KnowledgeSubpage (edit item).
 * Shows a textarea with optional delete on the left, cancel + save on the right.
 * Includes a mic button for voice input when the browser supports it.
 */
import { useState, useRef, useEffect } from "react";
import { Box, Typography } from "@mui/material";
import MicIcon from "@mui/icons-material/Mic";
import VoiceInput, { isVoiceSupported } from "./VoiceInput";
import { TYPE, COLOR } from "../theme";

export default function InlineEditor({ value, onSave, onCancel, onDelete }) {
  const [text, setText] = useState(value);
  const [showVoice, setShowVoice] = useState(false);
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
            p: 1, border: `1px solid ${COLOR.primary}`, borderRadius: "4px",
            bgcolor: COLOR.surfaceAlt, resize: "none", overflow: "hidden", outline: "none",
          }}
          rows={1}
        />
        {isVoiceSupported() && (
          <Box
            onClick={() => setShowVoice(!showVoice)}
            sx={{
              width: 32, height: 32, borderRadius: "50%",
              display: "flex", alignItems: "center", justifyContent: "center",
              cursor: "pointer", flexShrink: 0, mt: 0.5,
              bgcolor: showVoice ? COLOR.primaryLight : COLOR.surface,
              "&:active": { opacity: 0.6 },
            }}
          >
            <MicIcon sx={{ fontSize: 18, color: showVoice ? COLOR.primary : COLOR.text4 }} />
          </Box>
        )}
      </Box>
      {showVoice && (
        <Box sx={{ mt: 0.8 }}>
          <VoiceInput
            onResult={(transcript) => {
              setText((prev) => prev ? prev + transcript : transcript);
              setShowVoice(false);
            }}
            onCancel={() => setShowVoice(false)}
          />
        </Box>
      )}
      <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", mt: 0.75 }}>
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
