import { useState } from "react";
import {
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Divider,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableRow,
  TextField,
  Typography,
} from "@mui/material";
import { t } from "../../i18n";

function formatRawValue(value) {
  if (value === null || value === undefined) return "null";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function getRecordDisplayRows(record) {
  const fields = ["patient_name", "record_type", "content", "tags", "created_at"];
  return fields.map((field) => ({
    key: field,
    label: t(`manage.record.fields.${field}`),
    value:
      record[field] === null || record[field] === undefined || record[field] === ""
        ? "-"
        : formatRawValue(record[field]),
  }));
}

function getTimelineEventKey(event) {
  return `${event.type || "event"}-${event.id ?? ""}-${event.timestamp || ""}`;
}

function getTimelineRows(event) {
  const payload = event.payload || {};
  const base = [{ key: "timestamp", value: event.timestamp || "-" }];
  const recordFields = ["content", "tags"];
  const taskFields = ["task_type", "title", "status", "due_at"];
  const fields =
    event.type === "record" ? recordFields : event.type === "task" ? taskFields : Object.keys(payload || {});
  const payloadRows = fields.map((field) => ({
    key: field,
    value:
      payload[field] === null || payload[field] === undefined || payload[field] === ""
        ? "-"
        : formatRawValue(payload[field]),
  }));
  return [...base, ...payloadRows].map((row) => ({
    ...row,
    label: t(`manage.timeline.fields.${row.key}`),
  }));
}

function getTimelineSummary(event) {
  const payload = event.payload || {};
  if (event.type === "record") {
    const content = payload.content || "";
    return content.length > 50 ? content.slice(0, 50) + "…" : content || "-";
  }
  if (event.type === "task") return payload.title || "-";
  return "-";
}

const detailTableSx = {
  mt: 0.6,
  border: "1px solid #d8e3e8",
  borderRadius: 1.5,
  backgroundColor: "#f8fbfc",
};

const labelCellSx = { width: "28%", fontWeight: 700, color: "text.secondary", borderBottom: "1px solid #e4edf0" };
const valueCellSx = { whiteSpace: "pre-wrap", wordBreak: "break-word", borderBottom: "1px solid #e4edf0" };

export default function RecordPanel({
  records,
  timeline,
  selectedPatientId,
  doctorId,
  patientNameFilter,
  dateFrom,
  dateTo,
  loading,
  onPatientNameFilterChange,
  onDateFromChange,
  onDateToChange,
  onApplyFilters,
}) {
  const [expandedRecordId, setExpandedRecordId] = useState("");
  const [expandedTimelineKey, setExpandedTimelineKey] = useState("");

  return (
    <Box>
      <Card sx={{ borderRadius: 1.5, mb: 1.5 }}>
        <CardContent sx={{ display: "flex", gap: 1, flexDirection: { xs: "column", sm: "row" } }}>
          <TextField
            size="small"
            label={t("manage.filters.patientName")}
            value={patientNameFilter}
            onChange={(e) => onPatientNameFilterChange(e.target.value)}
          />
          <TextField
            size="small"
            type="date"
            label={t("manage.filters.dateFrom")}
            InputLabelProps={{ shrink: true }}
            value={dateFrom}
            onChange={(e) => onDateFromChange(e.target.value)}
          />
          <TextField
            size="small"
            type="date"
            label={t("manage.filters.dateTo")}
            InputLabelProps={{ shrink: true }}
            value={dateTo}
            onChange={(e) => onDateToChange(e.target.value)}
          />
          <Button variant="outlined" onClick={onApplyFilters}>{t("common.apply")}</Button>
        </CardContent>
      </Card>

      <Stack spacing={1.25}>
        {records.map((r) => {
          const tags = Array.isArray(r.tags) ? r.tags : [];
          const snippet = r.content ? (r.content.length > 80 ? r.content.slice(0, 80) + "…" : r.content) : null;
          return (
            <Card key={r.id} sx={{ borderRadius: 1.5 }}>
              <CardContent sx={{ p: 1.5 }}>
                <Stack
                  direction={{ xs: "column", sm: "row" }}
                  spacing={0.8}
                  sx={{ justifyContent: "space-between", alignItems: { sm: "flex-start" } }}
                >
                  <Box sx={{ flex: 1, minWidth: 0 }}>
                    <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
                      {t("manage.record.patientName")}：{r.patient_name || t("manage.record.unlinkedPatient")}
                    </Typography>
                    <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.15 }}>
                      {t("manage.record.date")}：{r.created_at || "-"}
                    </Typography>
                    {snippet && (
                      <Typography variant="body2" sx={{ mt: 0.5, lineHeight: 1.6 }}>
                        {snippet}
                      </Typography>
                    )}
                    {tags.length > 0 && (
                      <Stack direction="row" spacing={0.5} flexWrap="wrap" sx={{ mt: 0.6 }}>
                        {tags.map((tag, i) => (
                          <Chip key={i} label={tag} size="small" variant="outlined" sx={{ fontSize: 11 }} />
                        ))}
                      </Stack>
                    )}
                  </Box>
                  <Stack direction="row" spacing={0.7} sx={{ flexShrink: 0 }}>
                    <Chip size="small" label={r.record_type || "visit"} />
                    <Button
                      size="small"
                      variant={String(r.id) === expandedRecordId ? "contained" : "outlined"}
                      onClick={() => setExpandedRecordId(String(r.id) === expandedRecordId ? "" : String(r.id))}
                    >
                      {String(r.id) === expandedRecordId ? t("manage.record.hideDetails") : t("manage.record.showDetails")}
                    </Button>
                  </Stack>
                </Stack>
                {String(r.id) === expandedRecordId ? (
                  <>
                    <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1 }}>
                      {t("manage.record.rawFieldView")}
                    </Typography>
                    <TableContainer sx={detailTableSx}>
                      <Table size="small">
                        <TableBody>
                          {getRecordDisplayRows(r).map((row) => (
                            <TableRow key={`${r.id}-${row.key}`}>
                              <TableCell sx={labelCellSx}>{row.label}</TableCell>
                              <TableCell sx={valueCellSx}>{row.value}</TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </TableContainer>
                  </>
                ) : null}
              </CardContent>
            </Card>
          );
        })}
        {!records.length && !loading ? (
          <Typography color="text.secondary">{t("manage.record.empty")}</Typography>
        ) : null}
      </Stack>

      <Divider sx={{ my: 2.2 }} />
      <Stack direction="row" sx={{ alignItems: "center", mb: 1, gap: 1 }}>
        <Typography variant="subtitle1" sx={{ fontWeight: 700, flex: 1 }}>
          {t("manage.timeline.title")}
        </Typography>
        {selectedPatientId ? (
          <Button
            size="small"
            variant="outlined"
            component="a"
            href={`/api/export/patient/${selectedPatientId}/pdf?doctor_id=${encodeURIComponent(doctorId || "")}`}
            target="_blank"
            rel="noopener noreferrer"
          >
            📄 {t("manage.timeline.exportPdf")}
          </Button>
        ) : null}
      </Stack>
      {!selectedPatientId ? (
        <Typography color="text.secondary">{t("manage.timeline.emptyHint")}</Typography>
      ) : null}
      <Stack spacing={1}>
        {timeline.map((e) => (
          <Card key={getTimelineEventKey(e)} sx={{ borderRadius: 1.5 }}>
            <CardContent>
              <Stack
                direction={{ xs: "column", sm: "row" }}
                spacing={1}
                sx={{ justifyContent: "space-between", alignItems: { sm: "center" } }}
              >
                <Box>
                  <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
                    {t(`manage.timeline.eventType.${e.type || "unknown"}`)}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    {t("manage.timeline.fields.timestamp")}：{e.timestamp || "-"}
                  </Typography>
                  <Typography variant="body2" sx={{ mt: 0.4 }}>
                    {e.type === "record"
                      ? t("manage.timeline.summary.record")
                      : t("manage.timeline.summary.task")}
                    ：{getTimelineSummary(e)}
                  </Typography>
                </Box>
                <Button
                  size="small"
                  variant={getTimelineEventKey(e) === expandedTimelineKey ? "contained" : "outlined"}
                  onClick={() =>
                    setExpandedTimelineKey(
                      getTimelineEventKey(e) === expandedTimelineKey ? "" : getTimelineEventKey(e)
                    )
                  }
                >
                  {getTimelineEventKey(e) === expandedTimelineKey
                    ? t("manage.timeline.hideDetails")
                    : t("manage.timeline.showDetails")}
                </Button>
              </Stack>
              {getTimelineEventKey(e) === expandedTimelineKey ? (
                <TableContainer sx={{ ...detailTableSx, mt: 0.8 }}>
                  <Table size="small">
                    <TableBody>
                      {getTimelineRows(e).map((row) => (
                        <TableRow key={`${getTimelineEventKey(e)}-${row.key}`}>
                          <TableCell sx={labelCellSx}>{row.label}</TableCell>
                          <TableCell sx={valueCellSx}>{row.value}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              ) : null}
            </CardContent>
          </Card>
        ))}
        {selectedPatientId && !timeline.length ? (
          <Typography color="text.secondary">{t("manage.timeline.empty")}</Typography>
        ) : null}
      </Stack>
    </Box>
  );
}
