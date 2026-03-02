import { Card, CardContent, Stack, Typography } from "@mui/material";

const ITEMS = [
  {
    title: "Web chat + management UI",
    summary: "Use Chat for intake and Manage for patients, records, and prompt customization.",
  },
  {
    title: "Editable structuring prompts",
    summary: "Tune `structuring` and `structuring.extension` directly in Manage without restarts.",
  },
  {
    title: "Seed DB import/export tool",
    summary: "Bootstrap demo data with `tools/seed_db.py` and safely re-run imports with deduplication.",
  },
];

export default function FeatureChangelog() {
  return (
    <Card sx={{ mb: 2 }}>
      <CardContent>
        <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
          Available Features
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5, mb: 1.25 }}>
          Quick overview of what you can use in this app.
        </Typography>
        <Stack spacing={1}>
          {ITEMS.map((item) => (
            <Stack key={item.title} spacing={0.4}>
              <Typography variant="body2" sx={{ fontWeight: 600 }}>
                {item.title}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                {item.summary}
              </Typography>
            </Stack>
          ))}
        </Stack>
      </CardContent>
    </Card>
  );
}
