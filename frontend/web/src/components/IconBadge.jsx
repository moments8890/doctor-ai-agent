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

export default function IconBadge({ config, size = 36, radius = 6, sx }) {
  if (!config) return null;
  const { icon: Icon, bg, color = "#fff", iconSize } = config;
  return (
    <Box sx={{
      width: size, height: size, borderRadius: `${radius}px`, flexShrink: 0,
      bgcolor: bg, display: "flex", alignItems: "center", justifyContent: "center",
      ...sx,
    }}>
      <Icon sx={{ fontSize: iconSize || size * 0.5, color }} />
    </Box>
  );
}
