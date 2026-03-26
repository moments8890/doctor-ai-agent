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
import { TYPE, COLOR } from "../theme";

export default function StatusBadge({ label, colorMap, fallbackColor = COLOR.text4, sx }) {
  const color = colorMap?.[label] ?? fallbackColor;
  return (
    <Box
      component="span"
      sx={{
        display: "inline-block",
        px: 0.8,
        py: 0.1,
        borderRadius: "4px",
        border: `1px solid ${color}`,
        color,
        fontSize: TYPE.micro.fontSize,
        fontWeight: 600,
        lineHeight: 1.6,
        ml: 0.8,
        flexShrink: 0,
        ...sx,
      }}
    >
      {label}
    </Box>
  );
}
