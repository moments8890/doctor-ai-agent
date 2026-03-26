/**
 * 患者头像组件：根据患者姓名首字生成彩色圆形头像。
 */
import { Box, Typography } from "@mui/material";
import { AVATAR_COLORS } from "../pages/doctor/constants";

export function nameColor(name) {
  let h = 0;
  for (let i = 0; i < (name || "").length; i++) {
    h = (h * 31 + name.charCodeAt(i)) & 0xffff;
  }
  return AVATAR_COLORS[h % AVATAR_COLORS.length];
}

export default function PatientAvatar({ name, size = 42 }) {
  return (
    <Box sx={{
      width: size, height: size, borderRadius: "4px", flexShrink: 0,
      bgcolor: nameColor(name),
      display: "flex", alignItems: "center", justifyContent: "center",
    }}>
      <Typography sx={{ color: "#fff", fontSize: size * 0.42, fontWeight: 600, lineHeight: 1 }}>
        {(name || "?")[0]}
      </Typography>
    </Box>
  );
}
