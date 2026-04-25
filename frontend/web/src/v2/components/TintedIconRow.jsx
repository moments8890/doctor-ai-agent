/**
 * TintedIconRow — list row used inside a Card. 36px circular tinted icon on
 * the left, title + optional subtitle in the middle, optional `extra` slot or
 * chevron on the right.
 *
 * Use for settings rows, action menus, navigation rows. See doctor SettingsPage
 * for canonical usage. Pass `isFirst` on the first row in a Card to suppress
 * the top divider; subsequent rows render a 0.5px borderLight divider.
 */
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import { APP, FONT, ICON, RADIUS } from "../theme";

export default function TintedIconRow({
  Icon,
  iconColor,
  iconBg,
  title,
  subtitle,
  onClick,
  extra,
  isFirst,
}) {
  return (
    <div
      onClick={onClick}
      style={{
        display: "flex",
        alignItems: "center",
        gap: 12,
        padding: "14px 16px",
        cursor: onClick ? "pointer" : "default",
        borderTop: isFirst ? "none" : `0.5px solid ${APP.borderLight}`,
      }}
    >
      <div
        style={{
          width: 36,
          height: 36,
          borderRadius: RADIUS.md,
          background: iconBg,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          flexShrink: 0,
        }}
      >
        <Icon sx={{ fontSize: ICON.sm, color: iconColor }} />
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: FONT.base, fontWeight: 600, color: APP.text1 }}>
          {title}
        </div>
        {subtitle && (
          <div style={{ fontSize: FONT.sm, color: APP.text4, marginTop: 2 }}>
            {subtitle}
          </div>
        )}
      </div>
      {extra ?? (onClick && <ChevronRightIcon sx={{ fontSize: ICON.sm, color: APP.text4 }} />)}
    </div>
  );
}
