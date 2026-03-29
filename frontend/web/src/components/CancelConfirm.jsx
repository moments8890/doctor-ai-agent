/**
 * CancelConfirm — two-step cancel confirmation popup.
 *
 * Every cancel/back action that would discard user work must go through
 * this component. Prevents accidental loss of unsaved changes.
 *
 * Layout (WeChat convention — primary action always RIGHT):
 *  LEFT:  "取消" (gray)  — stay and continue working
 *  RIGHT: "离开" (red)   — discard and leave
 *
 * Props:
 *  - open: boolean
 *  - title: string (default: "确认离开？")
 *  - message: string (default: "未保存的内容将会丢失")
 *  - confirmLabel: string (default: "离开") — destructive action, shown RIGHT in red
 *  - cancelLabel: string (default: "取消") — safe action, shown LEFT in gray
 *  - onConfirm: () => void — executes the cancel/discard
 *  - onCancel: () => void — dismisses popup, user continues working
 */
import ConfirmDialog from "./ConfirmDialog";

export default function CancelConfirm({
  open,
  title = "确认离开？",
  message = "未保存的内容将会丢失",
  confirmLabel = "离开",
  cancelLabel = "取消",
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
