import { Card, CardContent, Stack, Typography } from "@mui/material";
import { t, traw } from "../i18n";

export default function FeatureChangelog() {
  const items = traw("features.items");
  return (
    <Card sx={{ mb: 2 }}>
      <CardContent>
        <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
          {t("features.title")}
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5, mb: 1.25 }}>
          {t("features.subtitle")}
        </Typography>
        <Stack spacing={1}>
          {items.map((item) => (
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
