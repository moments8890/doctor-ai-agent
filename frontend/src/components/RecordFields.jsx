import { Box, Divider, Typography } from "@mui/material";
import { t } from "../i18n";

const RECORD_FIELDS = [
  "chief_complaint",
  "history_of_present_illness",
  "past_medical_history",
  "physical_examination",
  "auxiliary_examinations",
  "diagnosis",
  "treatment_plan",
  "follow_up_plan",
];

export default function RecordFields({ record }) {
  if (!record) return null;

  return (
    <Box
      sx={{
        mt: 1.5,
        p: 1.5,
        borderRadius: 1.5,
        bgcolor: "#fff",
        border: "1px solid #d8e1e3",
      }}
    >
      <Typography variant="subtitle2" sx={{ color: "primary.main", mb: 1 }}>
        {t("recordFields.title")}
      </Typography>
      {RECORD_FIELDS.map((key, idx) => {
        if (!record[key]) return null;
        return (
          <Box key={key} sx={{ mb: 1 }}>
            {idx > 0 ? <Divider sx={{ mb: 1 }} /> : null}
            <Typography variant="caption" color="text.secondary">
              {t(`recordFields.fields.${key}`)}
            </Typography>
            <Typography variant="body2">{String(record[key])}</Typography>
          </Box>
        );
      })}
    </Box>
  );
}
