/**
 * EmptyState — consistent empty/no-data state.
 *
 * Uses antd-mobile `Empty` (the small list-friendly variant) instead of
 * `ErrorBlock` (the big page-takeover illustration). The two-line
 * title + description treatment is preserved in the description slot.
 *
 * Usage:
 *   <EmptyState title="暂无患者" description="点击右上角 + 新建" />
 *   <EmptyState title="暂无任务" action="新建任务" onAction={() => {}} />
 */
import { Empty, Button } from "antd-mobile";
import { APP, FONT } from "../theme";

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
        paddingTop: 32,
        ...style,
      }}
    >
      <Empty
        description={
          <>
            {title && (
              <div style={{ fontSize: FONT.md, color: APP.text1, marginBottom: 4 }}>
                {title}
              </div>
            )}
            {description && (
              <div style={{ fontSize: FONT.sm, color: APP.text4 }}>
                {description}
              </div>
            )}
          </>
        }
      />
      {action && onAction && (
        <Button
          color="primary"
          size="small"
          onClick={onAction}
          style={{ marginTop: 16 }}
        >
          {action}
        </Button>
      )}
    </div>
  );
}
