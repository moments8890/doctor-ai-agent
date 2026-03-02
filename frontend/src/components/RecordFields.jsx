import { Box, Divider, Typography } from "@mui/material";

const RECORD_FIELDS = [
  ["chief_complaint", "Chief Complaint"],
  ["history_of_present_illness", "HPI"],
  ["past_medical_history", "Past History"],
  ["physical_examination", "Physical Exam"],
  ["auxiliary_examinations", "Auxiliary Exams"],
  ["diagnosis", "Diagnosis"],
  ["treatment_plan", "Treatment Plan"],
  ["follow_up_plan", "Follow-up Plan"],
];

export default function RecordFields({ record }) {
  if (!record) return null;

  return (
    <Box
      sx={{
        mt: 1.5,
        p: 1.5,
        borderRadius: 2,
        bgcolor: "#fff",
        border: "1px solid #d8e1e3",
      }}
    >
      <Typography variant="subtitle2" sx={{ color: "primary.main", mb: 1 }}>
        Structured Medical Record
      </Typography>
      {RECORD_FIELDS.map(([key, label], idx) => {
        if (!record[key]) return null;
        return (
          <Box key={key} sx={{ mb: 1 }}>
            {idx > 0 ? <Divider sx={{ mb: 1 }} /> : null}
            <Typography variant="caption" color="text.secondary">
              {label}
            </Typography>
            <Typography variant="body2">{String(record[key])}</Typography>
          </Box>
        );
      })}
    </Box>
  );
}
