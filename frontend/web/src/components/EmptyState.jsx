/**
 * EmptyState — centered placeholder for empty lists/sections.
 */
import { Box, Typography } from "@mui/material";
import { ICON, COLOR } from "../theme";

export default function EmptyState({ icon, title, subtitle }) {
  return (
    <Box sx={{ display: "flex", flexDirection: "column", alignItems: "center", py: 8, gap: 1, px: 2 }}>
      {icon && <Box sx={{ "& svg": { fontSize: ICON.display, color: COLOR.text4 } }}>{icon}</Box>}
      <Typography variant="body2" color="text.disabled" sx={{ fontWeight: 500 }}>
        {title}
      </Typography>
      {subtitle && (
        <Typography variant="caption" color="text.disabled" sx={{ textAlign: "center", maxWidth: 200 }}>
          {subtitle}
        </Typography>
      )}
    </Box>
  );
}
