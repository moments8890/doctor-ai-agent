/**
 * ListSectionDivider — styled section divider with optional right-side action.
 *
 * NOTE: The internal symbol is still `SectionHeader` during the Phase 2-5
 * migration window. Phase 5 (Task 5.6) renames the function symbol and
 * removes the barrel alias together. Until then, both `ListSectionDivider`
 * and `SectionHeader` re-exports point to the same default below.
 *
 * Usage:
 *   <ListSectionDivider>鉴别诊断</ListSectionDivider>
 *   <ListSectionDivider action="+ 添加" onAction={() => {}}>鉴别诊断</ListSectionDivider>
 *   <ListSectionDivider color={APP.danger}>已逾期</ListSectionDivider>
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
