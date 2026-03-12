import { Box, Chip, Stack, Typography } from "@mui/material";
import { t } from "../i18n";

export default function RecordFields({ record }) {
  if (!record) return null;
  const tags = Array.isArray(record.tags) ? record.tags : [];

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
      <Typography variant="body2" sx={{ whiteSpace: "pre-wrap", lineHeight: 1.7 }}>
        {record.content || "—"}
      </Typography>
      {tags.length > 0 && (
        <Stack direction="row" spacing={0.6} flexWrap="wrap" sx={{ mt: 1.2 }}>
          {tags.map((tag, i) => (
            <Chip key={i} label={tag} size="small" variant="outlined" sx={{ fontSize: 11 }} />
          ))}
        </Stack>
      )}
    </Box>
  );
}
