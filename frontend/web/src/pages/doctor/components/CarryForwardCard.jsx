/**
 * CarryForwardCard — one-tap confirmation of stable medical history fields
 * from prior visit records.
 *
 * Props:
 *  - items: [{field, label, value, source_date}]
 *  - onConfirm(field): confirm a single field
 *  - onDismiss(field): dismiss a single field
 *  - onConfirmAll(): confirm all remaining fields
 *  - disabled: boolean
 */
import { Box, Button, Typography } from "@mui/material";
import { TYPE, COLOR } from "../../../theme";

export default function CarryForwardCard({ items, onConfirm, onDismiss, onConfirmAll, disabled = false }) {
  if (!items || items.length === 0) return null;

  const sourceDate = items[0]?.source_date || "";

  return (
    <Box sx={{
      mx: 1.5, mt: 1, mb: 0.5, p: 1.5,
      bgcolor: COLOR.white,
      border: `1px solid ${COLOR.border}`,
      borderRadius: "8px",
    }}>
      {/* Header */}
      <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", mb: 1 }}>
        <Typography sx={{ fontSize: TYPE.secondary.fontSize, fontWeight: 500, color: COLOR.text2 }}>
          {"\uD83D\uDCCB"} 上次记录{sourceDate ? ` (${sourceDate})` : ""}
        </Typography>
        <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4 }}>
          {items.length} 项可沿用
        </Typography>
      </Box>

      {/* Per-field rows */}
      {items.map((item) => (
        <Box key={item.field} sx={{
          display: "flex", alignItems: "center", gap: 1,
          py: 0.8,
          borderTop: `1px solid ${COLOR.borderLight}`,
        }}>
          {/* Label + value */}
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Typography sx={{
              fontSize: TYPE.caption.fontSize, fontWeight: 500,
              color: COLOR.text3, mb: 0.2,
            }}>
              {item.label}
            </Typography>
            <Typography sx={{
              fontSize: TYPE.secondary.fontSize, color: COLOR.text2,
              overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
            }}>
              {item.value}
            </Typography>
          </Box>

          {/* Action buttons */}
          <Box sx={{ display: "flex", gap: 0.5, flexShrink: 0 }}>
            <Button
              size="small"
              variant="contained"
              disableElevation
              disabled={disabled}
              onClick={() => onConfirm(item.field)}
              sx={{
                minWidth: 48, px: 1, py: 0.3,
                fontSize: TYPE.caption.fontSize,
                bgcolor: COLOR.success,
                color: COLOR.white,
                "&:hover": { bgcolor: "#47b566" },
                "&.Mui-disabled": { bgcolor: "#ccc", color: "#fff" },
              }}
            >
              沿用
            </Button>
            <Button
              size="small"
              variant="outlined"
              disableElevation
              disabled={disabled}
              onClick={() => onDismiss(item.field)}
              sx={{
                minWidth: 48, px: 1, py: 0.3,
                fontSize: TYPE.caption.fontSize,
                color: COLOR.text4,
                borderColor: COLOR.border,
                "&:hover": { borderColor: COLOR.text4 },
                "&.Mui-disabled": { borderColor: "#eee", color: "#ccc" },
              }}
            >
              忽略
            </Button>
          </Box>
        </Box>
      ))}

      {/* Footer: confirm all */}
      {items.length > 1 && (
        <Box sx={{ mt: 1, pt: 0.8, borderTop: `1px solid ${COLOR.borderLight}`, textAlign: "center" }}>
          <Button
            size="small"
            variant="outlined"
            disableElevation
            disabled={disabled}
            onClick={onConfirmAll}
            sx={{
              fontSize: TYPE.caption.fontSize,
              color: COLOR.success,
              borderColor: COLOR.success,
              "&:hover": { bgcolor: COLOR.successLight, borderColor: COLOR.success },
              "&.Mui-disabled": { borderColor: "#ccc", color: "#ccc" },
            }}
          >
            全部沿用
          </Button>
        </Box>
      )}
    </Box>
  );
}
