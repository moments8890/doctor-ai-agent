/**
 * SectionLoading — centered spinner for content sections.
 *
 * Replaces ad-hoc CircularProgress+Box patterns across pages.
 * Use for section/page-level loading. For button-level loading,
 * use AppButton's loading prop instead.
 */
import { Box, CircularProgress } from "@mui/material";
import { COLOR } from "../theme";

export default function SectionLoading({ size = 20, py = 3 }) {
  return (
    <Box sx={{ display: "flex", justifyContent: "center", py }}>
      <CircularProgress size={size} sx={{ color: COLOR.text4 }} />
    </Box>
  );
}
