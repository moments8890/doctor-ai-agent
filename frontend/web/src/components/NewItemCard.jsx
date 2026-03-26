/**
 * NewItemCard — dashed "+" card for creating new items.
 * Used at the top of patient list, task list, record list, etc.
 */
import { Box, Typography } from "@mui/material";
import { ICON, COLOR } from "../theme";
import ListCard from "./ListCard";

export default function NewItemCard({ title, subtitle, onClick }) {
  return (
    <ListCard
      avatar={
        <Box sx={{ width: 36, height: 36, borderRadius: "4px", border: `1.5px dashed ${COLOR.success}`,
          display: "flex", alignItems: "center", justifyContent: "center" }}>
          <Typography sx={{ fontSize: ICON.lg, color: COLOR.success, lineHeight: 1 }}>+</Typography>
        </Box>
      }
      title={title}
      subtitle={subtitle}
      onClick={onClick}
      sx={{ "& .MuiTypography-root:first-of-type": { color: COLOR.success } }}
    />
  );
}
