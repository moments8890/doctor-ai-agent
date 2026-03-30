/**
 * StatColumn — single stat display: large number + micro label.
 * Used in dashboard stat bars (MyAIPage, TaskPage).
 */
import { Box, Skeleton, Typography } from "@mui/material";
import { TYPE, COLOR } from "../theme";

export default function StatColumn({ value, label, sublabel, color, onClick }) {
  return (
    <Box onClick={onClick} sx={{ flex: 1, textAlign: "center", cursor: onClick ? "pointer" : "default", "&:active": onClick ? { opacity: 0.5 } : {} }}>
      <Typography sx={{ fontSize: TYPE.title.fontSize, fontWeight: 600, color: color || COLOR.text1 }}>
        {value ?? <Skeleton width={20} sx={{ mx: "auto" }} />}
      </Typography>
      <Typography sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.text4, mt: "2px" }}>
        {label}
      </Typography>
      {sublabel && (
        <Typography sx={{ fontSize: 10, color: COLOR.primary, mt: "1px" }}>
          {sublabel}
        </Typography>
      )}
    </Box>
  );
}
