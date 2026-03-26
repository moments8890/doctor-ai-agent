/**
 * BarButton — plain text button for SubpageHeader actions.
 */
import { Box, CircularProgress } from "@mui/material";
import { TYPE, BUTTON, COLOR } from "../theme";

export default function BarButton({ children, onClick, disabled = false, loading = false, color = COLOR.success, sx }) {
  const isDisabled = disabled || loading;
  return (
    <Box
      onClick={!isDisabled ? onClick : undefined}
      sx={{
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        minHeight: BUTTON.compactHeight,
        fontSize: BUTTON.compactFontSize, lineHeight: BUTTON.compactLineHeight, fontWeight: TYPE.body.fontWeight, color,
        cursor: isDisabled ? "default" : "pointer",
        opacity: isDisabled ? 0.4 : 1,
        px: BUTTON.compactPaddingX, py: BUTTON.compactPaddingY,
        userSelect: "none", WebkitUserSelect: "none",
        "&:active": isDisabled ? {} : { opacity: 0.5 },
        ...sx,
      }}
    >
      {loading ? <CircularProgress size={14} sx={{ color: "inherit" }} /> : children}
    </Box>
  );
}
