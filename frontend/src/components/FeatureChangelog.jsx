import { Card, CardContent, Chip, Stack, Typography } from "@mui/material";

const ITEMS = [
  {
    date: "2026-03-01",
    title: "Web chat + management UI",
    summary: "Use Chat for intake and Manage for patients, records, and prompt customization.",
  },
  {
    date: "2026-03-01",
    title: "Editable structuring prompts",
    summary: "Tune `structuring` and `structuring.extension` directly in Manage without restarts.",
  },
  {
    date: "2026-03-01",
    title: "Seed DB import/export tool",
    summary: "Bootstrap demo data with `tools/seed_db.py` and safely re-run imports with deduplication.",
  },
];

export default function FeatureChangelog() {
  return (
    <Card sx={{ mb: 2 }}>
      <CardContent>
        <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
          What&apos;s New
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5, mb: 1.25 }}>
          Quick changelog of currently available features.
        </Typography>
        <Stack spacing={1}>
          {ITEMS.map((item) => (
            <Stack key={`${item.date}-${item.title}`} spacing={0.4}>
              <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
                <Chip size="small" label={item.date} />
                <Typography variant="body2" sx={{ fontWeight: 600 }}>
                  {item.title}
                </Typography>
              </Stack>
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
