/**
 * DialogFooter — standard button layout for SheetDialog and ConfirmDialog footers.
 *
 * Convention (WeChat standard):
 *  - Cancel/secondary always LEFT, primary always RIGHT
 *  - Equal-width grid for 2 horizontal buttons
 *  - Stacked (column) for 3+ buttons or when `stack` is true
 *
 * Usage:
 *   <SheetDialog footer={<DialogFooter onCancel={...} onConfirm={...} confirmLabel="保存" />}>
 */
import { Box } from "@mui/material";
import AppButton from "./AppButton";

export default function DialogFooter({
  onCancel,
  onConfirm,
  cancelLabel = "取消",
  confirmLabel = "确认",
  confirmVariant = "primary",
  cancelVariant = "secondary",
  confirmDisabled = false,
  confirmLoading = false,
  confirmLoadingLabel,
  cancelDisabled = false,
  showCancel = true,
  stack = false,
  children,
}) {
  // If children are provided, render them directly (custom footer content)
  if (children) return <Box sx={{ display: "flex", flexDirection: "column", gap: 1 }}>{children}</Box>;

  const cancelBtn = showCancel ? (
    <AppButton variant={cancelVariant} size="md" fullWidth disabled={cancelDisabled} onClick={onCancel}>
      {cancelLabel}
    </AppButton>
  ) : null;

  const confirmBtn = (
    <AppButton
      variant={confirmVariant}
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

  if (stack || !showCancel) {
    return (
      <Box sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
        {confirmBtn}
        {cancelBtn}
      </Box>
    );
  }

  return (
    <Box sx={{ display: "grid", gap: 1, gridTemplateColumns: "repeat(2, minmax(0, 1fr))" }}>
      {cancelBtn}
      {confirmBtn}
    </Box>
  );
}
