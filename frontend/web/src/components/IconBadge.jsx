/**
 * IconBadge — consistent icon-in-colored-box component.
 *
 * Renders a MUI icon inside a rounded square with a background color.
 * Use ICON_BADGES from constants for predefined configs, or pass custom props.
 *
 * @example
 *   <IconBadge config={ICON_BADGES.knowledge} />
 *   <IconBadge config={ICON_BADGES.patient} size={28} />
 */
import { Box } from "@mui/material";
import { COLOR } from "../theme";

export default function IconBadge({ config, size = 36, radius = 6, solid = false, sx }) {
  if (!config) return null;
  const { icon: Icon, bg, color, iconSize } = config;
  // Default: tinted (light bg + colored icon). solid: colored bg + white icon.
  const bgColor = solid ? bg : (bg + "18");
  const iconColor = solid ? (color || COLOR.white) : (color || bg);
  return (
    <Box sx={{
      width: size, height: size, borderRadius: `${radius}px`, flexShrink: 0,
      bgcolor: bgColor, display: "flex", alignItems: "center", justifyContent: "center",
      ...sx,
    }}>
      <Icon sx={{ fontSize: iconSize || size * 0.5, color: iconColor }} />
    </Box>
  );
}
