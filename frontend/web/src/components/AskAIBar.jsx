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
        bgcolor: "#fff", borderRadius: "4px",
        display: "flex", alignItems: "center", gap: 1,
        border: "0.5px solid #d9d9d9",
        cursor: "pointer",
        boxShadow: "0 -2px 8px rgba(0,0,0,0.04)",
        "&:active": { bgcolor: "#f9f9f9" },
      }}
    >
      <Box sx={{
        width: 28, height: 28, borderRadius: "4px", bgcolor: COLOR.success,
        display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0,
      }}>
        <Typography sx={{ color: "#fff", fontSize: TYPE.micro.fontSize, fontWeight: "bold" }}>AI</Typography>
      </Box>
      <Typography sx={{ fontSize: TYPE.body.fontSize, color: "#bbb" }}>问 AI 任何问题...</Typography>
    </Box>
  );
}
