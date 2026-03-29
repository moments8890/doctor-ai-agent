import { Box, Typography } from "@mui/material";
import { COLOR, RADIUS } from "../theme";

export default function NameAvatar({ name, size = 42 }) {
  return (
    <Box sx={{
      width: size, height: size, borderRadius: RADIUS.sm, flexShrink: 0,
      bgcolor: COLOR.borderLight,
      display: "flex", alignItems: "center", justifyContent: "center",
    }}>
      <Typography sx={{ color: COLOR.text4, fontSize: size * 0.42, fontWeight: 600, lineHeight: 1 }}>
        {(name || "?")[0]}
      </Typography>
    </Box>
  );
}
