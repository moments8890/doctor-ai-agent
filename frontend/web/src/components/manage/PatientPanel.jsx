import { useMemo, useState } from "react";
import {
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  Tooltip,
  Typography,
} from "@mui/material";
import { t } from "../../i18n";
import { exportPatientPdf } from "../../api";

function PatientCard({ p, labels, doctorId, onViewRecords, onToggleLabel }) {
  const [expanded, setExpanded] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState("");

  async function handleExportPdf() {
    setExporting(true);
    setExportError("");
    try {
      await exportPatientPdf(p.id, doctorId);
    } catch (err) {
      setExportError(err.message || t("manage.patient.exportFailed"));
    } finally {
      setExporting(false);
    }
  }

  return (
    <Card sx={{ borderRadius: 1.5 }}>
      <CardContent sx={{ p: 1.5 }}>
        <Stack
          direction={{ xs: "column", sm: "row" }}
          spacing={0.8}
          sx={{ justifyContent: "space-between", alignItems: { sm: "center" } }}
        >
          <Stack direction="row" spacing={0.7} sx={{ alignItems: "center", flexWrap: "wrap" }}>
            <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
              {p.name}
            </Typography>
            {p.primary_category ? (
              <Chip size="small" label={`${t("manage.patient.categoryPrefix")}：${p.primary_category}`} />
            ) : null}
            {(p.labels || []).map((label) => (
              <Chip
                key={`brief-tag-${p.id}-${label.id}`}
                size="small"
                variant="outlined"
                label={label.name}
                sx={{
                  borderColor: label.color || "#cbd5e1",
                  color: "#334155",
                  backgroundColor: "rgba(248,250,252,0.9)",
                }}
              />
            ))}
          </Stack>
          <Stack direction="row" spacing={0.7} alignItems="center">
            <Button size="small" variant="outlined" onClick={() => onViewRecords(p)}>
              {t("manage.patient.filterRecords")}
            </Button>
            <Tooltip title={exportError || t("manage.patient.exportPdf")} arrow>
              <span>
                <Button
                  size="small"
                  variant="outlined"
                  color={exportError ? "error" : "primary"}
                  onClick={handleExportPdf}
                  disabled={exporting}
                  startIcon={exporting ? <CircularProgress size={14} /> : null}
                >
                  {exporting ? t("manage.patient.exporting") : t("manage.patient.exportPdf")}
                </Button>
              </span>
            </Tooltip>
            <Button
              size="small"
              variant={expanded ? "contained" : "outlined"}
              onClick={() => setExpanded((v) => !v)}
            >
              {expanded ? t("manage.patient.hideDetails") : t("manage.patient.showDetails")}
            </Button>
          </Stack>
        </Stack>

        <Box sx={{ mt: 0.7 }}>
          <Typography variant="caption" color="text.secondary">
            {p.gender || t("manage.patient.genderUnknown")} |{" "}
            {p.year_of_birth
              ? `${new Date().getFullYear() - p.year_of_birth}${t("manage.patient.ageSuffix")}`
              : t("manage.patient.ageNA")}{" "}
            | {t("manage.patient.recordCount")}={p.record_count}
          </Typography>
          {expanded ? (
            <Box sx={{ mt: 0.35 }}>
              <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
                {t("manage.patient.createdAt")}：{p.created_at || "-"}
              </Typography>
              {labels.length > 0 ? (
                <Stack direction="row" spacing={0.5} sx={{ flexWrap: "wrap", mt: 0.6 }}>
                  {labels.map((label) => {
                    const active = (p.labels || []).some((l) => l.id === label.id);
                    return (
                      <Chip
                        key={`tag-toggle-inline-${p.id}-${label.id}`}
                        size="small"
                        variant={active ? "filled" : "outlined"}
                        color={active ? "primary" : "default"}
                        label={`${active ? "✓ " : ""}${label.name}`}
                        onClick={() => onToggleLabel(p, label)}
                        sx={{ cursor: "pointer" }}
                      />
                    );
                  })}
                </Stack>
              ) : null}
            </Box>
          ) : null}
        </Box>
      </CardContent>
    </Card>
  );
}

export default function PatientPanel({
  patients,
  labels,
  doctorId,
  tagFilter,
  loading,
  onTagFilterChange,
  onViewRecords,
  onToggleLabel,
}) {
  const displayed = useMemo(() => {
    if (!tagFilter) return patients;
    return patients.filter((p) => (p.labels || []).some((l) => String(l.id) === String(tagFilter)));
  }, [patients, tagFilter]);

  return (
    <Stack spacing={1.25}>
      <Card sx={{ borderRadius: 1.5 }}>
        <CardContent sx={{ display: "flex", flexWrap: "wrap", gap: 1 }}>
          <FormControl size="small" sx={{ minWidth: 180 }}>
            <InputLabel id="tag-filter-label">{t("manage.filters.tag")}</InputLabel>
            <Select
              labelId="tag-filter-label"
              label={t("manage.filters.tag")}
              value={tagFilter}
              onChange={(e) => onTagFilterChange(e.target.value)}
            >
              <MenuItem value="">{t("common.all")}</MenuItem>
              {labels.map((label) => (
                <MenuItem key={`tag-filter-${label.id}`} value={String(label.id)}>
                  {label.name}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
        </CardContent>
      </Card>

      {displayed.map((p) => (
        <PatientCard
          key={p.id}
          p={p}
          labels={labels}
          doctorId={doctorId}
          onViewRecords={onViewRecords}
          onToggleLabel={onToggleLabel}
        />
      ))}
      {!displayed.length && !loading ? (
        <Typography color="text.secondary">{t("manage.patient.empty")}</Typography>
      ) : null}
    </Stack>
  );
}
