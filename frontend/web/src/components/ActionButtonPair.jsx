/**
 * ActionButtonPair — cancel + confirm two-button row for dialogs and actions.
 */
import { Box } from "@mui/material";
import AppButton from "./AppButton";

export default function ActionButtonPair({
  onCancel, onConfirm,
  cancelLabel = "取消", confirmLabel = "保存",
  loading = false, loadingLabel = "保存中…",
  danger = false,
}) {
  return (
    <Box sx={{ display: "flex", gap: 1.5 }}>
      <AppButton variant="secondary" onClick={onCancel} fullWidth>
        {cancelLabel}
      </AppButton>
      <AppButton variant={danger ? "danger" : "primary"} onClick={onConfirm}
        loading={loading} loadingLabel={loadingLabel} fullWidth>
        {confirmLabel}
      </AppButton>
    </Box>
  );
}
