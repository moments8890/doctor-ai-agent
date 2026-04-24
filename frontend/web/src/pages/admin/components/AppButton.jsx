/**
 * AppButton — standardized button for content-level UI contexts.
 *
 * Variants:
 *  - primary:   green bg, white text — one per screen max (save, confirm, complete)
 *  - secondary: gray bg, dark text — cancel, dismiss
 *  - danger:    red bg, white text — destructive (delete, reject)
 *
 * Sizes:
 *  - lg: detail-view primary actions (py 1.3, fontSize 15)
 *  - md: dialog buttons (shared compact height, fontSize 14) — default
 *  - sm: inline/field buttons (same shared compact metrics)
 *
 * For most inline actions (edit, delete), use plain text buttons instead
 * of AppButton — the app's default pattern is colored text, not filled buttons.
 */
import { Box, CircularProgress } from "@mui/material";
import { TYPE, BUTTON, COLOR, RADIUS } from "../../../theme";

const VARIANT_STYLES = {
  primary:   { bgcolor: COLOR.primary, color: COLOR.white, fontWeight: 600 },
  secondary: { bgcolor: COLOR.surface, color: COLOR.text3, fontWeight: 400 },
  danger:    { bgcolor: COLOR.danger, color: COLOR.white, fontWeight: 600 },
};

const SIZE_STYLES = {
  lg: { minHeight: BUTTON.largeHeight, py: 1, px: 2.5, fontSize: TYPE.action.fontSize, borderRadius: RADIUS.sm, lineHeight: 1.25 },
  md: { minHeight: BUTTON.compactHeight, py: BUTTON.compactPaddingY, px: BUTTON.compactPaddingX, fontSize: BUTTON.compactFontSize, borderRadius: BUTTON.compactRadius, lineHeight: BUTTON.compactLineHeight },
  sm: { minHeight: BUTTON.compactHeight, py: BUTTON.compactPaddingY, px: BUTTON.compactPaddingX, fontSize: BUTTON.compactFontSize, borderRadius: BUTTON.compactRadius, lineHeight: BUTTON.compactLineHeight },
};

export default function AppButton({
  children, variant = "primary", size = "md",
  onClick, loading = false, loadingLabel, disabled = false,
  fullWidth = false, sx,
}) {
  const vStyles = VARIANT_STYLES[variant] || VARIANT_STYLES.primary;
  const sStyles = SIZE_STYLES[size] || SIZE_STYLES.md;
  const isDisabled = disabled || loading;
  const label = loading ? (loadingLabel || children) : children;

  return (
    <Box
      onClick={!isDisabled ? onClick : undefined}
      sx={{
        display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 1,
        textAlign: "center", cursor: isDisabled ? "default" : "pointer",
        whiteSpace: "normal", wordBreak: "break-word", maxWidth: "100%",
        opacity: isDisabled ? 0.5 : 1,
        userSelect: "none", WebkitUserSelect: "none",
        "&:active": isDisabled ? {} : { opacity: 0.7 },
        ...(fullWidth && { display: "flex", width: "100%" }),
        ...vStyles, ...sStyles, ...sx,
      }}
    >
      {loading && <CircularProgress size={14} sx={{ color: "inherit" }} />}
      {label}
    </Box>
  );
}
