/**
 * BarButton — plain text button for SubpageHeader actions.
 */
import { Box, CircularProgress } from "@mui/material";
import { TYPE, COLOR } from "../theme";

export default function BarButton({ children, onClick, disabled = false, loading = false, color = COLOR.success, sx }) {
  const isDisabled = disabled || loading;
  return (
    <Box
      onClick={!isDisabled ? onClick : undefined}
      sx={{
        fontSize: TYPE.action.fontSize, fontWeight: TYPE.action.fontWeight, color,
        cursor: isDisabled ? "default" : "pointer",
        opacity: isDisabled ? 0.4 : 1,
        px: 1, py: 0.5,
        userSelect: "none", WebkitUserSelect: "none",
        "&:active": isDisabled ? {} : { opacity: 0.5 },
        ...sx,
      }}
    >
      {loading ? <CircularProgress size={14} sx={{ color: "inherit" }} /> : children}
    </Box>
  );
}
