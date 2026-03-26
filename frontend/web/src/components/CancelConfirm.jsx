/**
 * CancelConfirm — two-step cancel confirmation popup.
 *
 * Every cancel/back action that would discard user work must go through
 * this component. Prevents accidental loss of unsaved changes.
 *
 * Step 1: User taps cancel/back → this popup appears
 * Step 2: User confirms "确认" to discard, or "返回" to continue working
 *
 * Props:
 *  - open: boolean
 *  - title: string (default: "确认离开？")
 *  - message: string (default: "未保存的内容将会丢失")
 *  - confirmLabel: string (default: "确认")
 *  - cancelLabel: string (default: "返回")
 *  - onConfirm: () => void — executes the cancel/discard
 *  - onCancel: () => void — dismisses popup, user continues working
 */
import { Box, Dialog, Typography } from "@mui/material";
import { TYPE, COLOR } from "../theme";

export default function CancelConfirm({
  open,
  title = "确认离开？",
  message = "未保存的内容将会丢失",
  confirmLabel = "确认",
  cancelLabel = "返回",
  onConfirm,
  onCancel,
}) {
  return (
    <Dialog open={open} onClose={onCancel} maxWidth="xs" fullWidth
      PaperProps={{ sx: { borderRadius: "12px", mx: 3 } }}>
      <Box sx={{ p: 3, textAlign: "center" }}>
        <Typography sx={{ fontSize: TYPE.body.fontSize, fontWeight: 600, mb: 0.5 }}>
          {title}
        </Typography>
        <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text4, mb: 2.5 }}>
          {message}
        </Typography>
        <Box sx={{ display: "flex", gap: 1.5 }}>
          <Box
            onClick={onConfirm}
            sx={{
              flex: 1, py: 1, textAlign: "center", borderRadius: "4px",
              fontSize: TYPE.body.fontSize, color: COLOR.danger,
              border: `0.5px solid ${COLOR.border}`,
              cursor: "pointer", "&:active": { opacity: 0.6 },
            }}
          >
            {confirmLabel}
          </Box>
          <Box
            onClick={onCancel}
            sx={{
              flex: 1, py: 1, textAlign: "center", borderRadius: "4px",
              fontSize: TYPE.body.fontSize, fontWeight: 600, color: "#fff",
              bgcolor: COLOR.primary,
              cursor: "pointer", "&:active": { opacity: 0.7 },
            }}
          >
            {cancelLabel}
          </Box>
        </Box>
      </Box>
    </Dialog>
  );
}
