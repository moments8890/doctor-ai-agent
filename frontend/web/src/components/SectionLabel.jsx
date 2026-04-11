/**
 * SectionLabel — small gray group header used above card sections.
 * Example: "账户", "工具", "通用", "当前模板".
 */
import { Box, Typography } from "@mui/material";
import { TYPE, COLOR } from "../theme";

export default function SectionLabel({ children, sx }) {
  return (
    <Box sx={{ px: 1.5, pt: 2, pb: 0.5, ...sx }}>
      <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text3, fontWeight: 600, letterSpacing: 0.5 }}>
        {children}
      </Typography>
    </Box>
  );
}
