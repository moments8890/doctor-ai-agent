/**
 * WorkingContextHeader — shows the doctor's current working context at a glance:
 * current patient, pending draft status, and next-step guidance.
 *
 * UX contract: "At any moment, the doctor can tell who the current patient is
 * and whether a draft is pending."
 */
import { Box, Chip, Typography } from "@mui/material";
import PersonOutlineIcon from "@mui/icons-material/PersonOutline";
import EditNoteOutlinedIcon from "@mui/icons-material/EditNoteOutlined";
import { TYPE, ICON } from "../../../theme";

export default function WorkingContextHeader({ context, isMobile }) {
  if (!context) return null;

  const { current_patient, pending_draft, next_step } = context;

  // Only show when there's actual content (patient selected or draft pending)
  if (!current_patient && !pending_draft) return null;

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
      {/* Current patient */}
      {current_patient && (
        <Chip
          icon={<PersonOutlineIcon sx={{ fontSize: ICON.sm }} />}
          label={current_patient.name}
          size="small"
          sx={{
            bgcolor: "#e6f7e9",
            color: "#07C160",
            fontWeight: 600,
            fontSize: TYPE.caption.fontSize,
            "& .MuiChip-icon": { color: "#07C160" },
          }}
        />
      )}

      {/* Pending draft indicator */}
      {pending_draft && (
        <Chip
          icon={<EditNoteOutlinedIcon sx={{ fontSize: ICON.sm }} />}
          label={`草稿：${pending_draft.patient_name}`}
          size="small"
          sx={{
            bgcolor: "#fff7e6",
            color: "#d46b08",
            fontWeight: 500,
            fontSize: TYPE.caption.fontSize,
            "& .MuiChip-icon": { color: "#d46b08" },
          }}
        />
      )}

      {/* Next step guidance */}
      {next_step && !pending_draft && (
        <Typography
          variant="caption"
          sx={{
            color: "#888",
            fontSize: TYPE.caption.fontSize,
            ml: "auto",
          }}
        >
          {next_step}
        </Typography>
      )}
    </Box>
  );
}
