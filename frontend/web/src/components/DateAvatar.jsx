import { Box, Typography } from "@mui/material";
import { TYPE, COLOR, RADIUS } from "../theme";

export default function DateAvatar({ date, size = 36 }) {
  const d = new Date(date);
  const month = `${d.getMonth() + 1}月`;
  const day = `${d.getDate()}日`;

  return (
    <Box sx={{
      width: size, height: size, borderRadius: RADIUS.sm, bgcolor: COLOR.surface,
      display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center",
      flexShrink: 0,
    }}>
      <Typography sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.text4, lineHeight: 1.2 }}>{month}</Typography>
      <Typography sx={{ fontSize: TYPE.heading.fontSize, fontWeight: 600, color: COLOR.text1, lineHeight: 1.2 }}>{day}</Typography>
    </Box>
  );
}
