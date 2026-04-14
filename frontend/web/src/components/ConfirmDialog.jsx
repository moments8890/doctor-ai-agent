import { Box, Dialog, Typography } from "@mui/material";
import { TYPE, COLOR, RADIUS } from "../theme";
import AppButton from "./AppButton";

export default function ConfirmDialog({
  open,
  title,
  message,
  children,
  confirmLabel = "确认",
  cancelLabel = "取消",
  onConfirm,
  onCancel,
  onClose,
  confirmTone = "primary",
  confirmDisabled = false,
  confirmLoading = false,
  confirmLoadingLabel,
  cancelDisabled = false,
  showCancel = true,
  maxWidth = 360,
}) {
  const cancelHandler = onCancel || onClose;
  const closeHandler = onClose || onCancel;
  const danger = confirmTone === "danger";

  const cancelButton = showCancel ? (
    <AppButton
      variant="secondary"
      size="md"
      fullWidth
      disabled={cancelDisabled}
      onClick={cancelHandler}
    >
      {cancelLabel}
    </AppButton>
  ) : null;

  const confirmButton = (
    <AppButton
      variant={danger ? "danger" : "primary"}
      size="md"
      fullWidth
      disabled={confirmDisabled}
      loading={confirmLoading}
      loadingLabel={confirmLoadingLabel}
      onClick={onConfirm}
    >
      {confirmLabel}
    </AppButton>
  );

  const orderedButtons = [cancelButton, confirmButton].filter(Boolean);

  return (
    <Dialog
      open={open}
      onClose={closeHandler}
      maxWidth="xs"
      fullWidth
      PaperProps={{ sx: { borderRadius: RADIUS.lg, m: 1, width: "calc(100% - 16px)", maxWidth } }}
    >
      <Box sx={{ p: 2.5, textAlign: "center" }}>
        {title && (
          <Typography sx={{ fontSize: TYPE.title.fontSize, fontWeight: 600, color: COLOR.text1, mb: 0.5 }}>
            {title}
          </Typography>
        )}
        {message && (
          <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text4, lineHeight: 1.6, whiteSpace: "pre-wrap", mb: children ? 1.5 : 2.5 }}>
            {message}
          </Typography>
        )}
        {children ? <Box sx={{ mb: 2 }}>{children}</Box> : null}
        <Box sx={{ display: "grid", gap: 0.5, gridTemplateColumns: orderedButtons.length > 1 ? "repeat(2, minmax(0, 1fr))" : "1fr" }}>
          {orderedButtons.map((button, index) => (
            <Box key={index}>{button}</Box>
          ))}
        </Box>
      </Box>
    </Dialog>
  );
}
