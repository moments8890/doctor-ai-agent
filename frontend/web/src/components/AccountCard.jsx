/**
 * AccountCard — shared profile card for doctor and patient accounts.
 *
 * Layout: [colored avatar] [name + subtitle]
 * Below: optional info rows (key-value pairs).
 *
 * Props:
 *  - name: string (display name)
 *  - subtitle: string (e.g., doctorId, phone)
 *  - color: string (avatar background color, defaults to primary green)
 *  - rows: [{ label, value, onClick? }] (optional info rows below avatar)
 */
import { Box, Typography } from "@mui/material";
import { TYPE, ICON, COLOR, RADIUS } from "../theme";

export default function AccountCard({ name, subtitle, color, rows }) {
  const initial = (name || "?").slice(-1);
  const bg = color || COLOR.primary;

  return (
    <Box sx={{ bgcolor: COLOR.white }}>
      {/* Avatar + name row */}
      <Box sx={{ display: "flex", alignItems: "center", px: 2, py: 2, borderBottom: `0.5px solid ${COLOR.borderLight}` }}>
        <Box sx={{
          width: 52, height: 52, borderRadius: RADIUS.sm, bgcolor: bg,
          display: "flex", alignItems: "center", justifyContent: "center",
          flexShrink: 0, mr: 1.5,
        }}>
          <Typography sx={{ color: COLOR.white, fontSize: ICON.xl, fontWeight: 600 }}>
            {initial}
          </Typography>
        </Box>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography sx={{ fontWeight: 600, fontSize: TYPE.title.fontSize }}>{name || "未设置"}</Typography>
          {subtitle && <Typography variant="caption" color="text.secondary">{subtitle}</Typography>}
        </Box>
      </Box>

      {/* Info rows */}
      {rows && rows.map((row, i) => (
        <Box
          key={i}
          onClick={row.onClick}
          sx={{
            display: "flex", alignItems: "center", px: 2, py: 1.5,
            borderBottom: `0.5px solid ${COLOR.borderLight}`,
            "&:last-child": { borderBottom: "none" },
            cursor: row.onClick ? "pointer" : "default",
            "&:active": row.onClick ? { bgcolor: COLOR.surface } : {},
          }}
        >
          <Typography sx={{ fontSize: TYPE.body.fontSize, color: COLOR.text1, flex: 1 }}>{row.label}</Typography>
          <Typography sx={{ fontSize: TYPE.body.fontSize, color: COLOR.text4, mr: 0.8 }} noWrap>{row.value || "未设置"}</Typography>
        </Box>
      ))}
    </Box>
  );
}
