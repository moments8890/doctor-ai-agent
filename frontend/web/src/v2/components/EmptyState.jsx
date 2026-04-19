/**
 * EmptyState — consistent empty/no-data state.
 *
 * Wraps antd-mobile ErrorBlock with optional action button.
 *
 * Usage:
 *   <EmptyState title="暂无患者" description="点击右上角 + 新建" />
 *   <EmptyState title="暂无任务" action="新建任务" onAction={() => {}} />
 */
import { ErrorBlock, Button } from "antd-mobile";

export default function EmptyState({
  title,
  description,
  action,
  onAction,
  style,
}) {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        paddingTop: 48,
        ...style,
      }}
    >
      <ErrorBlock status="empty" title={title} description={description} />
      {action && onAction && (
        <Button
          color="primary"
          size="small"
          onClick={onAction}
          style={{ marginTop: 12 }}
        >
          {action}
        </Button>
      )}
    </div>
  );
}
