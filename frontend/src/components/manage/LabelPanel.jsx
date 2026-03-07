import { useState } from "react";
import {
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import { t } from "../../i18n";

export default function LabelPanel({
  labels,
  patients,
  tagFilter,
  onTagFilterChange,
  onCreateLabel,
  onDeleteLabel,
  onToggleLabel,
}) {
  const [newLabelName, setNewLabelName] = useState("");
  const [newLabelColor, setNewLabelColor] = useState("#0f766e");

  const displayed = tagFilter
    ? patients.filter((p) => (p.labels || []).some((l) => String(l.id) === String(tagFilter)))
    : patients;

  function handleCreate() {
    const name = newLabelName.trim();
    if (!name) return;
    onCreateLabel(name, newLabelColor);
    setNewLabelName("");
  }

  return (
    <Stack spacing={1.25}>
      <Card sx={{ borderRadius: 1.5 }}>
        <CardContent>
          <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1 }}>
            {t("manage.labels.title")}
          </Typography>
          <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
            <TextField
              size="small"
              label={t("manage.labels.name")}
              value={newLabelName}
              onChange={(e) => setNewLabelName(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") handleCreate(); }}
            />
            <TextField
              size="small"
              type="color"
              label={t("manage.labels.color")}
              value={newLabelColor}
              onChange={(e) => setNewLabelColor(e.target.value)}
              sx={{ width: { xs: "100%", sm: 96 } }}
            />
            <Button variant="contained" onClick={handleCreate}>
              {t("manage.labels.add")}
            </Button>
          </Stack>
          <Stack direction="row" spacing={0.8} sx={{ flexWrap: "wrap", mt: 1.2 }}>
            {labels.map((label) => (
              <Chip
                key={label.id}
                label={label.name}
                onDelete={() => onDeleteLabel(label.id)}
                sx={{ backgroundColor: label.color || "#e2e8f0", color: "#0f172a", border: "1px solid rgba(15,23,42,0.14)" }}
              />
            ))}
            {!labels.length ? (
              <Typography variant="caption" color="text.secondary">
                {t("manage.labels.empty")}
              </Typography>
            ) : null}
          </Stack>
        </CardContent>
      </Card>

      <Card sx={{ borderRadius: 1.5 }}>
        <CardContent>
          <FormControl size="small" sx={{ minWidth: 220, mb: 1.2 }}>
            <InputLabel id="tag-filter-tab-label">{t("manage.filters.tag")}</InputLabel>
            <Select
              labelId="tag-filter-tab-label"
              label={t("manage.filters.tag")}
              value={tagFilter}
              onChange={(e) => onTagFilterChange(e.target.value)}
            >
              <MenuItem value="">{t("common.all")}</MenuItem>
              {labels.map((label) => (
                <MenuItem key={`tab-tag-filter-${label.id}`} value={String(label.id)}>
                  {label.name}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1 }}>
            {t("manage.labels.assignTitle")}
          </Typography>
          <Stack spacing={1}>
            {displayed.map((p) => (
              <Box key={`tag-row-${p.id}`}>
                <Typography variant="body2" sx={{ mb: 0.6, fontWeight: 600 }}>
                  {p.name}
                </Typography>
                <Stack direction="row" spacing={0.7} sx={{ flexWrap: "wrap" }}>
                  {labels.map((label) => {
                    const active = (p.labels || []).some((l) => l.id === label.id);
                    return (
                      <Chip
                        key={`tag-toggle-${p.id}-${label.id}`}
                        size="small"
                        variant={active ? "filled" : "outlined"}
                        color={active ? "primary" : "default"}
                        label={`${active ? "✓ " : ""}${label.name}`}
                        onClick={() => onToggleLabel(p, label)}
                      />
                    );
                  })}
                </Stack>
              </Box>
            ))}
            {!displayed.length ? (
              <Typography color="text.secondary">{t("manage.patient.empty")}</Typography>
            ) : null}
          </Stack>
        </CardContent>
      </Card>
    </Stack>
  );
}
