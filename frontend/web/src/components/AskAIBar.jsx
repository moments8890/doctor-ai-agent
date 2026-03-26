/**
 * AskAIBar — sticky floating bar for "问 AI 任何问题".
 * Sits just above the bottom nav on mobile, bottom of content on desktop.
 */
import { Box, Typography } from "@mui/material";
import { TYPE, COLOR } from "../theme";

export default function AskAIBar({ onClick }) {
  return (
    <Box
      onClick={onClick}
      sx={{
        mx: 1.5, mb: 1.5, px: 1.5, py: 1,
        bgcolor: COLOR.white, borderRadius: "4px",
        display: "flex", alignItems: "center", gap: 1,
        border: `0.5px solid ${COLOR.border}`,
        cursor: "pointer",
        "&:active": { bgcolor: COLOR.surfaceAlt },
      }}
    >
      <Box sx={{
        width: 28, height: 28, borderRadius: "4px", bgcolor: COLOR.success,
        display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0,
      }}>
        <Typography sx={{ color: COLOR.white, fontSize: TYPE.micro.fontSize, fontWeight: "bold" }}>AI</Typography>
      </Box>
      <Typography sx={{ fontSize: TYPE.body.fontSize, color: COLOR.text4 }}>问 AI 任何问题...</Typography>
    </Box>
  );
}
