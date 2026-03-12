import {
  Button,
  Card,
  CardContent,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import { t } from "../../i18n";

export default function PromptPanel({ basePrompt, extPrompt, onBaseChange, onExtChange, onSave }) {
  return (
    <Stack spacing={1.5}>
      <Card sx={{ borderRadius: 1.5 }}>
        <CardContent>
          <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
            {t("manage.prompt.base")}
          </Typography>
          <TextField
            multiline
            minRows={8}
            fullWidth
            value={basePrompt}
            onChange={(e) => onBaseChange(e.target.value)}
            sx={{ mt: 1 }}
          />
          <Button sx={{ mt: 1 }} variant="contained" onClick={() => onSave("structuring", basePrompt)}>
            {t("manage.prompt.saveBase")}
          </Button>
        </CardContent>
      </Card>
      <Card sx={{ borderRadius: 1.5 }}>
        <CardContent>
          <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
            {t("manage.prompt.ext")}
          </Typography>
          <TextField
            multiline
            minRows={8}
            fullWidth
            value={extPrompt}
            onChange={(e) => onExtChange(e.target.value)}
            sx={{ mt: 1 }}
          />
          <Button sx={{ mt: 1 }} variant="contained" onClick={() => onSave("structuring.extension", extPrompt)}>
            {t("manage.prompt.saveExt")}
          </Button>
        </CardContent>
      </Card>
    </Stack>
  );
}
