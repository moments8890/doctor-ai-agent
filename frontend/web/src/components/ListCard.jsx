/**
 * ListCard — unified list row used in patient list, task list, etc.
 *
 * Layout: [avatar 36px] [title + subtitle] [right meta]
 */
import { Box, Typography } from "@mui/material";
import { TYPE } from "../theme";

export default function ListCard({ avatar, title, subtitle, right, onClick, sx }) {
  return (
    <Box
      onClick={onClick}
      sx={{
        display: "flex", alignItems: "center", gap: 1.5,
        px: 1.5, py: 1, bgcolor: "#fff",
        borderBottom: "0.5px solid #f0f0f0",
        cursor: onClick ? "pointer" : "default",
        userSelect: "none", WebkitUserSelect: "none",
        "&:active": onClick ? { bgcolor: "#f5f5f5" } : {},
        ...sx,
      }}
    >
      {avatar}
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <Typography sx={{ fontWeight: 500, fontSize: TYPE.action.fontSize, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: 1 }}>
            {title}
          </Typography>
          {right && <Box sx={{ flexShrink: 0, ml: 1 }}>{right}</Box>}
        </Box>
        {subtitle && (
          <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: "#999", mt: 0.2, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {subtitle}
          </Typography>
        )}
      </Box>
    </Box>
  );
}
