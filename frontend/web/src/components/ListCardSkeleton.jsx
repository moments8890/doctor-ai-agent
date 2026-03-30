/**
 * ListCardSkeleton — skeleton loading placeholder for ListCard rows.
 * Shows shimmering avatar + title + subtitle shapes that match ListCard layout.
 */
import { Box, Skeleton } from "@mui/material";
import { COLOR } from "../theme";

export default function ListCardSkeleton({ rows = 3, avatarSize = 36, showSubtitle = true }) {
  return Array.from({ length: rows }, (_, i) => (
    <Box
      key={i}
      sx={{
        display: "flex", alignItems: "center", gap: 1.5,
        px: 1.5, py: 1, bgcolor: COLOR.white,
        borderBottom: `0.5px solid ${COLOR.borderLight}`,
      }}
    >
      <Skeleton variant="rounded" width={avatarSize} height={avatarSize} animation="wave" />
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Skeleton variant="text" width={`${60 + (i % 3) * 15}%`} height={16} animation="wave" />
        {showSubtitle && (
          <Skeleton variant="text" width={`${40 + (i % 2) * 20}%`} height={12} animation="wave" sx={{ mt: 0.5 }} />
        )}
      </Box>
      <Skeleton variant="circular" width={14} height={14} animation="wave" />
    </Box>
  ));
}
