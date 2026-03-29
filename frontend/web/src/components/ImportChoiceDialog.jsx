import { Box, Typography } from "@mui/material";
import { TYPE, COLOR, RADIUS } from "../theme";
import AppButton from "./AppButton";
import SheetDialog from "./SheetDialog";

export default function ImportChoiceDialog({ open, text, onImport, onChat, onClose }) {
  if (!text) return null;
  const preview = text.length > 200 ? text.slice(0, 200) + "..." : text;
  return (
    <SheetDialog
      open={open}
      onClose={onClose}
      title="已提取文字内容"
      subtitle={`共提取 ${text.length} 字`}
      desktopMaxWidth={460}
      footer={
        <Box sx={{ display: "grid", gap: 0.5, gridTemplateColumns: "repeat(2, minmax(0, 1fr))" }}>
          <AppButton variant="secondary" size="md" fullWidth onClick={onClose}>
            取消
          </AppButton>
          {onChat ? (
            <AppButton variant="secondary" size="md" fullWidth onClick={() => onChat(text)}>
              发送到聊天
            </AppButton>
          ) : (
            <AppButton variant="primary" size="md" fullWidth onClick={() => onImport(text)}>
              导入病历
            </AppButton>
          )}
          {onChat ? (
            <Box sx={{ gridColumn: "1 / -1" }}>
              <AppButton variant="primary" size="md" fullWidth onClick={() => onImport(text)}>
                导入病历
              </AppButton>
            </Box>
          ) : null}
        </Box>
      }
    >
        <Box sx={{ p: 1.5, borderRadius: RADIUS.sm, bgcolor: COLOR.borderLight, mb: 1 }}>
          <Typography variant="body2" sx={{ whiteSpace: "pre-wrap", fontSize: TYPE.secondary.fontSize, color: COLOR.text3, lineHeight: 1.8 }}>
            {preview}
          </Typography>
        </Box>
    </SheetDialog>
  );
}
