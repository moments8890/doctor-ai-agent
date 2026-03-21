/**
 * SectionLabel — small gray group header used above card sections.
 * Example: "账户", "工具", "通用", "当前模板".
 */
import { Box, Typography } from "@mui/material";
import { TYPE } from "../theme";

export default function SectionLabel({ children, sx }) {
  return (
    <Box sx={{ px: 1.5, pt: 1, pb: 1, ...sx }}>
      <Typography sx={{ fontSize: TYPE.caption.fontSize, color: "#666", fontWeight: 600, letterSpacing: 0.5 }}>
        {children}
      </Typography>
    </Box>
  );
}
