import { useMemo, useState } from "react";
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
  Typography,
} from "@mui/material";
import { t } from "../../i18n";

const RISK_BORDER = {
  critical: "#ef4444",
  high: "#f97316",
  medium: "#f59e0b",
  low: "#22c55e",
};

const RISK_CHIP_COLOR = {
  critical: "error",
  high: "warning",
  medium: "default",
  low: "success",
};

function PatientCard({ p, labels, onViewRecords, onToggleLabel }) {
  const [expanded, setExpanded] = useState(false);
  const borderColor = RISK_BORDER[p.primary_risk_level] || "transparent";

  return (
    <Card
      sx={{
        borderRadius: 1.5,
        borderLeft: `4px solid ${borderColor}`,
      }}
    >
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
            {p.primary_risk_level ? (
              <Chip
                size="small"
                color={RISK_CHIP_COLOR[p.primary_risk_level] || "default"}
                label={`${t("manage.patient.riskPrefix")}：${t("manage.risk." + p.primary_risk_level) || p.primary_risk_level}`}
              />
            ) : null}
            {p.follow_up_state && p.follow_up_state !== "not_needed" ? (
              <Chip
                size="small"
                variant="outlined"
                color={p.follow_up_state === "overdue" ? "error" : p.follow_up_state === "due_soon" ? "warning" : "default"}
                label={t("manage.followUp." + p.follow_up_state) || p.follow_up_state}
              />
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
          <Stack direction="row" spacing={0.7}>
            <Button size="small" variant="outlined" onClick={() => onViewRecords(p)}>
              {t("manage.patient.filterRecords")}
            </Button>
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
                risk_score={p.risk_score ?? "-"} | risk_rules={p.risk_rules_version || "-"} | risk_at=
                {p.risk_computed_at || "-"}
              </Typography>
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
  riskFilter,
  followUpFilter,
  tagFilter,
  loading,
  onRiskFilterChange,
  onFollowUpFilterChange,
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
          <FormControl size="small" sx={{ minWidth: 170 }}>
            <InputLabel id="risk-filter-label">{t("manage.filters.risk")}</InputLabel>
            <Select
              labelId="risk-filter-label"
              label={t("manage.filters.risk")}
              value={riskFilter}
              onChange={(e) => onRiskFilterChange(e.target.value)}
            >
              <MenuItem value="">{t("common.all")}</MenuItem>
              <MenuItem value="critical">{t("manage.risk.critical")}</MenuItem>
              <MenuItem value="high">{t("manage.risk.high")}</MenuItem>
              <MenuItem value="medium">{t("manage.risk.medium")}</MenuItem>
              <MenuItem value="low">{t("manage.risk.low")}</MenuItem>
            </Select>
          </FormControl>
          <FormControl size="small" sx={{ minWidth: 190 }}>
            <InputLabel id="followup-filter-label">{t("manage.filters.followUp")}</InputLabel>
            <Select
              labelId="followup-filter-label"
              label={t("manage.filters.followUp")}
              value={followUpFilter}
              onChange={(e) => onFollowUpFilterChange(e.target.value)}
            >
              <MenuItem value="">{t("common.all")}</MenuItem>
              <MenuItem value="not_needed">{t("manage.followUp.not_needed")}</MenuItem>
              <MenuItem value="scheduled">{t("manage.followUp.scheduled")}</MenuItem>
              <MenuItem value="due_soon">{t("manage.followUp.due_soon")}</MenuItem>
              <MenuItem value="overdue">{t("manage.followUp.overdue")}</MenuItem>
            </Select>
          </FormControl>
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
