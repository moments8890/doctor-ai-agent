/**
 * SuggestionBar — floating quick-reply options above the input bar.
 *
 * Supports multi-select (toggle chips on/off) and dismiss.
 * Selected chips are combined into text via onChange callback.
 *
 * Props:
 *  - items: string[] — suggestion labels
 *  - selected: string[] — currently selected items
 *  - onToggle(text): toggle a chip on/off
 *  - onDismiss(): hide the bar entirely
 *  - disabled: boolean — grey out when loading
 */
import { Box } from "@mui/material";
import CloseIcon from "@mui/icons-material/Close";
import { TYPE, ICON, COLOR } from "../theme";

export default function SuggestionChips({ items, selected = [], onToggle, onDismiss, disabled = false }) {
  if (!items || items.length === 0) return null;

  return (
    <Box sx={{
      display: "flex", flexWrap: "wrap", alignItems: "center", gap: 0.5,
      px: 1.5, py: 0.8,
      borderTop: `1px solid ${COLOR.border}`,
      bgcolor: COLOR.surface,
      flexShrink: 0,
    }}>
      {items.map((text, i) => {
        const isSelected = selected.includes(text);
        return (
          <Box
            key={i}
            component="button"
            onClick={() => !disabled && onToggle(text)}
            disabled={disabled}
            sx={{
              display: "inline-flex",
              alignItems: "center",
              px: 1.2,
              py: 0.5,
              border: "1px solid",
              borderColor: isSelected ? COLOR.primary : COLOR.border,
              borderRadius: "16px",
              cursor: disabled ? "default" : "pointer",
              fontSize: TYPE.secondary.fontSize,
              fontFamily: "inherit",
              whiteSpace: "nowrap",
              flexShrink: 0,
              backgroundColor: isSelected ? COLOR.primaryLight : COLOR.white,
              color: isSelected ? COLOR.primary : (disabled ? COLOR.text4 : COLOR.text2),
              fontWeight: isSelected ? 500 : 400,
              opacity: disabled ? 0.5 : 1,
              transition: "all 0.15s",
              "&:active": disabled ? {} : { opacity: 0.7 },
            }}
          >
            {text}
          </Box>
        );
      })}
      {onDismiss && (
        <Box
          onClick={onDismiss}
          sx={{
            display: "flex", alignItems: "center", justifyContent: "center",
            width: 24, height: 24, borderRadius: "50%",
            cursor: "pointer", flexShrink: 0, ml: 0.5,
            color: COLOR.text4,
            "&:active": { opacity: 0.5 },
          }}
        >
          <CloseIcon sx={{ fontSize: ICON.sm }} />
        </Box>
      )}
    </Box>
  );
}
