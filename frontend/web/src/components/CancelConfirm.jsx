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
import ConfirmDialog from "./ConfirmDialog";

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
    <ConfirmDialog
      open={open}
      onClose={onCancel}
      onCancel={onCancel}
      onConfirm={onConfirm}
      title={title}
      message={message}
      confirmLabel={confirmLabel}
      cancelLabel={cancelLabel}
      confirmTone="danger"
    />
  );
}
