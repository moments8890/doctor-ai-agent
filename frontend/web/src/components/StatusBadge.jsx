/**
 * StatusBadge — inline colored badge for status/category labels.
 *
 * Props:
 *  - label: text to display
 *  - colorMap: { [label]: color } mapping
 *  - fallbackColor: color when label not in colorMap (default "#999")
 *  - sx: additional sx overrides
 */
import { Box } from "@mui/material";
import { TYPE, COLOR, RADIUS } from "../theme";

export default function StatusBadge({ label, colorMap, fallbackColor = COLOR.text4, sx }) {
  const color = colorMap?.[label] ?? fallbackColor;
  return (
    <Box
      component="span"
      sx={{
        display: "inline-block",
        px: 1,
        py: 0.5,
        borderRadius: RADIUS.sm,
        border: `1px solid ${color}`,
        color,
        fontSize: TYPE.micro.fontSize,
        fontWeight: 600,
        lineHeight: 1.6,
        ml: 1,
        flexShrink: 0,
        ...sx,
      }}
    >
      {label}
    </Box>
  );
}
