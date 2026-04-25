/**
 * SectionHeader — styled section divider with optional right-side action.
 *
 * Usage:
 *   <SectionHeader>鉴别诊断</SectionHeader>
 *   <SectionHeader action="+ 添加" onAction={() => {}}>鉴别诊断</SectionHeader>
 *   <SectionHeader color={APP.danger}>已逾期</SectionHeader>
 */
import { APP, FONT } from "../theme";

export default function SectionHeader({
  children,
  action,
  onAction,
  color = APP.text4,
}) {
  return (
    <div
      style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        padding: "8px 16px",
        backgroundColor: APP.surfaceAlt,
        borderTop: `0.5px solid ${APP.border}`,
        borderBottom: `0.5px solid ${APP.border}`,
      }}
    >
      <span
        style={{
          fontSize: FONT.sm,
          fontWeight: 600,
          color,
          letterSpacing: 0.3,
        }}
      >
        {children}
      </span>
      {action && (
        <span
          style={{
            fontSize: FONT.sm,
            color: APP.primary,
            cursor: "pointer",
          }}
          onClick={onAction}
        >
          {action}
        </span>
      )}
    </div>
  );
}
