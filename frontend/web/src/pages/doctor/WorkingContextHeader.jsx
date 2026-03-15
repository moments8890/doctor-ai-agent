/**
 * WorkingContextHeader — shows the doctor's current working context at a glance:
 * current patient name chip. Updates reactively via onContextUpdate from ChatSection.
 */
import { Box, Chip } from "@mui/material";
import PersonOutlineIcon from "@mui/icons-material/PersonOutline";

export default function WorkingContextHeader({ currentPatient, isMobile }) {
  if (!currentPatient) return null;

  return (
    <Box
      sx={{
        display: "flex",
        alignItems: "center",
        gap: isMobile ? 1 : 1.5,
        px: 2,
        py: isMobile ? 0.8 : 1,
        bgcolor: "#fafafa",
        borderBottom: "1px solid #eee",
        flexWrap: "wrap",
        minHeight: isMobile ? 36 : 40,
      }}
    >
      <Chip
        icon={<PersonOutlineIcon sx={{ fontSize: 16 }} />}
        label={currentPatient}
        size="small"
        sx={{
          bgcolor: "#e6f7e9",
          color: "#07C160",
          fontWeight: 600,
          fontSize: 12,
          "& .MuiChip-icon": { color: "#07C160" },
        }}
      />
    </Box>
  );
}
