/**
 * SectionLoading — loading state for content sections.
 * Default: skeleton rows matching ListCard layout.
 * Set `spinner` prop for the legacy centered spinner behavior.
 */
import { Box, CircularProgress } from "@mui/material";
import { COLOR } from "../theme";
import ListCardSkeleton from "./ListCardSkeleton";

export default function SectionLoading({ py = 2, rows = 3, spinner = false }) {
  if (spinner) {
    return (
      <Box sx={{ display: "flex", justifyContent: "center", py }}>
        <CircularProgress size={20} sx={{ color: COLOR.text4 }} />
      </Box>
    );
  }
  return <ListCardSkeleton rows={rows} />;
}
