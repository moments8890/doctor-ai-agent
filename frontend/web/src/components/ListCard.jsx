/**
 * ListCard — unified list row for all list-style UI.
 *
 * Layout: [avatar] [title + subtitle] [right meta OR › chevron]
 *
 * Props:
 *  - avatar: React element (36px icon/avatar)
 *  - title: string
 *  - subtitle: string (optional)
 *  - right: React element — custom right content (timestamp, count, etc.)
 *  - chevron: boolean — show › arrow on right (for navigation rows)
 *  - onClick: function
 *
 * Use `right` for data display (timestamps, counts).
 * Use `chevron` for navigation targets (settings rows, briefing cards).
 * If both provided, `right` is shown before the chevron.
 */
import { Box, Typography } from "@mui/material";
import ChevronRightOutlinedIcon from "@mui/icons-material/ChevronRightOutlined";
import { TYPE, COLOR } from "../theme";

export default function ListCard({ avatar, title, subtitle, right, chevron, onClick, sx }) {
  return (
    <Box
      role={onClick ? "button" : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={onClick ? (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onClick(e); } } : undefined}
      onClick={onClick}
      sx={{
        display: "flex", alignItems: "center", gap: 1.5,
        px: 2, py: 1.5, bgcolor: COLOR.white,
        borderBottom: `0.5px solid ${COLOR.borderLight}`,
        cursor: onClick ? "pointer" : "default",
        userSelect: "none", WebkitUserSelect: "none",
        "&:active": onClick ? { bgcolor: COLOR.surface } : {},
        ...sx,
      }}
    >
      {avatar}
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Typography sx={{ fontWeight: 500, fontSize: TYPE.action.fontSize, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {title}
        </Typography>
        {subtitle && (
          <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text4, mt: 0.2, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {subtitle}
          </Typography>
        )}
      </Box>
      {right && <Box sx={{ flexShrink: 0 }}>{right}</Box>}
      {chevron && (
        <ChevronRightOutlinedIcon sx={{ fontSize: 16, color: COLOR.text4, flexShrink: 0 }} />
      )}
    </Box>
  );
}
