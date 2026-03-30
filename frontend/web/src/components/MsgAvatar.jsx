/**
 * MsgAvatar — doctor/AI avatar for chat bubbles.
 * Rounded square with hospital icon (user) or robot icon (AI).
 */
import { Box } from "@mui/material";
import SmartToyOutlinedIcon from "@mui/icons-material/SmartToyOutlined";
import LocalHospitalOutlinedIcon from "@mui/icons-material/LocalHospitalOutlined";
import { COLOR, RADIUS } from "../theme";

export default function MsgAvatar({ isUser, size = 40 }) {
  return (
    <Box sx={{
      width: size, height: size, borderRadius: RADIUS.sm, flexShrink: 0,
      bgcolor: isUser ? COLOR.accent : COLOR.primary,
      display: "flex", alignItems: "center", justifyContent: "center",
    }}>
      {isUser
        ? <LocalHospitalOutlinedIcon sx={{ color: COLOR.white, fontSize: size * 0.56 }} />
        : <SmartToyOutlinedIcon sx={{ color: COLOR.white, fontSize: size * 0.56 }} />}
    </Box>
  );
}
