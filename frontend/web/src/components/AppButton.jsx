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
 *  - md: dialog buttons (py 1, fontSize 14) — default
 *  - sm: inline/field buttons (py 0.6, fontSize 13)
 *
 * For most inline actions (edit, delete), use plain text buttons instead
 * of AppButton — the app's default pattern is colored text, not filled buttons.
 */
import { Box, CircularProgress } from "@mui/material";
import { TYPE, COLOR } from "../theme";

const VARIANT_STYLES = {
  primary:   { bgcolor: COLOR.primary, color: "#fff", fontWeight: 600 },
  secondary: { bgcolor: "#f5f5f5", color: "#666", fontWeight: 400 },
  danger:    { bgcolor: COLOR.danger, color: "#fff", fontWeight: 600 },
};

const SIZE_STYLES = {
  lg: { py: 1.3, px: 2.5, fontSize: TYPE.action.fontSize, borderRadius: "4px" },
  md: { py: 1,   px: 2,   fontSize: TYPE.body.fontSize, borderRadius: "4px" },
  sm: { py: 0.6, px: 1.5, fontSize: TYPE.secondary.fontSize, borderRadius: "4px" },
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
        display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 0.8,
        textAlign: "center", cursor: isDisabled ? "default" : "pointer",
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
