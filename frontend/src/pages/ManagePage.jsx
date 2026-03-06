import { useEffect, useMemo, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Container,
  Divider,
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableRow,
  TextField,
  Typography,
} from "@mui/material";
import FolderSharedOutlinedIcon from "@mui/icons-material/FolderSharedOutlined";
import DescriptionOutlinedIcon from "@mui/icons-material/DescriptionOutlined";
import WarningAmberRoundedIcon from "@mui/icons-material/WarningAmberRounded";
import EventBusyOutlinedIcon from "@mui/icons-material/EventBusyOutlined";
import LabelOutlinedIcon from "@mui/icons-material/LabelOutlined";
import PeopleOutlineOutlinedIcon from "@mui/icons-material/PeopleOutlineOutlined";
import AssignmentOutlinedIcon from "@mui/icons-material/AssignmentOutlined";
import TuneOutlinedIcon from "@mui/icons-material/TuneOutlined";
import SellOutlinedIcon from "@mui/icons-material/SellOutlined";
import ForumOutlinedIcon from "@mui/icons-material/ForumOutlined";
import DashboardOutlinedIcon from "@mui/icons-material/DashboardOutlined";
import { Link as RouterLink } from "react-router-dom";
import {
  assignLabelToPatient,
  createLabel,
  deleteLabelById,
  getLabels,
  getPatientTimeline,
  getPatients,
  getPrompts,
  getRecords,
  removeLabelFromPatient,
  updatePrompt,
} from "../api";
import { t } from "../i18n";

function NavTab({ active, onClick, icon, children }) {
  return (
    <Button
      variant={active ? "contained" : "outlined"}
      onClick={onClick}
      startIcon={icon}
      sx={{ justifyContent: "flex-start", borderRadius: 2, width: "100%", minHeight: 42 }}
    >
      {children}
    </Button>
  );
}

export default function ManagePage() {
  const [doctorId, setDoctorId] = useState("web_doctor");
  const [tab, setTab] = useState(0);
  const [status, setStatus] = useState({ type: "info", text: "" });
  const [recordPatientNameFilter, setRecordPatientNameFilter] = useState("");
  const [recordDateFrom, setRecordDateFrom] = useState("");
  const [recordDateTo, setRecordDateTo] = useState("");
  const [patients, setPatients] = useState([]);
  const [records, setRecords] = useState([]);
  const [basePrompt, setBasePrompt] = useState("");
  const [extPrompt, setExtPrompt] = useState("");
  const [loading, setLoading] = useState(false);
  const [riskFilter, setRiskFilter] = useState("");
  const [followUpFilter, setFollowUpFilter] = useState("");
  const [tagFilter, setTagFilter] = useState("");
  const [selectedPatientId, setSelectedPatientId] = useState("");
  const [timeline, setTimeline] = useState([]);
  const [labels, setLabels] = useState([]);
  const [newLabelName, setNewLabelName] = useState("");
  const [newLabelColor, setNewLabelColor] = useState("#0f766e");
  const [expandedPatientId, setExpandedPatientId] = useState("");
  const [expandedRecordId, setExpandedRecordId] = useState("");
  const [expandedTimelineKey, setExpandedTimelineKey] = useState("");

  const displayedPatients = useMemo(() => {
    if (!tagFilter) return patients;
    return patients.filter((p) => (p.labels || []).some((l) => String(l.id) === String(tagFilter)));
  }, [patients, tagFilter]);

  const highRiskCount = useMemo(
    () => displayedPatients.filter((p) => p.primary_risk_level === "high" || p.primary_risk_level === "critical").length,
    [displayedPatients]
  );

  const overdueCount = useMemo(
    () => displayedPatients.filter((p) => p.follow_up_state === "overdue").length,
    [displayedPatients]
  );

  const statsRows = [
    { key: "patients", label: t("manage.stats.patients"), value: displayedPatients.length, icon: <FolderSharedOutlinedIcon fontSize="small" /> },
    { key: "records", label: t("manage.stats.records"), value: records.length, icon: <DescriptionOutlinedIcon fontSize="small" /> },
    { key: "highRisk", label: t("manage.stats.highRisk"), value: highRiskCount, icon: <WarningAmberRoundedIcon fontSize="small" /> },
    { key: "overdue", label: t("manage.stats.overdue"), value: overdueCount, icon: <EventBusyOutlinedIcon fontSize="small" /> },
    { key: "tags", label: t("manage.stats.tags"), value: labels.length, icon: <LabelOutlinedIcon fontSize="small" /> },
  ];

  const activeTabLabel =
    tab === 0
      ? t("manage.tabPlain.patients")
      : tab === 1
        ? t("manage.tabPlain.records")
        : tab === 2
          ? t("manage.tabPlain.customization")
          : t("manage.tabPlain.tags");

  async function loadAll(overrides = {}) {
    setLoading(true);
    setStatus({ type: "info", text: "" });
    try {
      const doctor = doctorId.trim() || "web_doctor";
      const nextPatientName = overrides.recordPatientNameFilter ?? recordPatientNameFilter;
      const nextDateFrom = overrides.recordDateFrom ?? recordDateFrom;
      const nextDateTo = overrides.recordDateTo ?? recordDateTo;
      const [p, r, prompts, labelResp] = await Promise.all([
        getPatients(doctor, { risk: riskFilter, followUpState: followUpFilter }),
        getRecords({
          doctorId: doctor,
          patientName: nextPatientName.trim(),
          dateFrom: nextDateFrom,
          dateTo: nextDateTo,
        }),
        getPrompts(),
        getLabels(doctor),
      ]);
      setPatients(p.items || []);
      setRecords(r.items || []);
      setBasePrompt(prompts.structuring || "");
      setExtPrompt(prompts.structuring_extension || "");
      setLabels(labelResp.items || []);
    } catch (error) {
      setStatus({ type: "error", text: t("manage.loadFailed", { message: error.message }) });
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    loadAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [riskFilter, followUpFilter]);

  async function savePrompt(key, content) {
    try {
      await updatePrompt(key, content);
      setStatus({ type: "success", text: t("manage.promptSaved", { key }) });
    } catch (error) {
      setStatus({ type: "error", text: t("manage.saveFailed", { message: error.message }) });
    }
  }

  function formatRawValue(value) {
    if (value === null || value === undefined) return "null";
    if (typeof value === "object") return JSON.stringify(value);
    return String(value);
  }

  function getRecordDisplayRows(record) {
    const fields = [
      "patient_name",
      "chief_complaint",
      "history_of_present_illness",
      "past_medical_history",
      "physical_examination",
      "auxiliary_examinations",
      "diagnosis",
      "treatment_plan",
      "follow_up_plan",
      "created_at",
    ];
    return fields.map((field) => ({
      key: field,
      label: t(`manage.record.fields.${field}`),
      value: record[field] === null || record[field] === undefined || record[field] === "" ? "-" : formatRawValue(record[field]),
    }));
  }

  function getTimelineEventKey(event) {
    return `${event.type || "event"}-${event.id ?? ""}-${event.timestamp || ""}`;
  }

  function getTimelineRows(event) {
    const payload = event.payload || {};
    const base = [{ key: "timestamp", value: event.timestamp || "-" }];
    const recordFields = ["chief_complaint", "diagnosis", "treatment_plan", "follow_up_plan"];
    const taskFields = ["task_type", "title", "status", "due_at", "trigger_source", "trigger_reason"];
    const fields = event.type === "record" ? recordFields : event.type === "task" ? taskFields : Object.keys(payload || {});
    const payloadRows = fields.map((field) => ({
      key: field,
      value: payload[field] === null || payload[field] === undefined || payload[field] === "" ? "-" : formatRawValue(payload[field]),
    }));
    return [...base, ...payloadRows].map((row) => ({
      ...row,
      label: t(`manage.timeline.fields.${row.key}`),
    }));
  }

  function getTimelineSummary(event) {
    const payload = event.payload || {};
    if (event.type === "record") return payload.chief_complaint || "-";
    if (event.type === "task") return payload.title || "-";
    return "-";
  }

  async function loadTimeline(patientId) {
    if (!patientId) return;
    try {
      const data = await getPatientTimeline({
        doctorId: doctorId.trim() || "web_doctor",
        patientId,
        limit: 100,
      });
      setTimeline(data.events || []);
    } catch (error) {
      setStatus({ type: "error", text: t("manage.timelineLoadFailed", { message: error.message }) });
      setTimeline([]);
    }
  }

  async function onCreateLabel() {
    const doctor = doctorId.trim() || "web_doctor";
    const name = newLabelName.trim();
    if (!name) return;
    try {
      await createLabel({ doctorId: doctor, name, color: newLabelColor });
      setNewLabelName("");
      const labelResp = await getLabels(doctor);
      setLabels(labelResp.items || []);
    } catch (error) {
      setStatus({ type: "error", text: t("manage.labels.createFailed", { message: error.message }) });
    }
  }

  async function onDeleteLabel(labelId) {
    const doctor = doctorId.trim() || "web_doctor";
    try {
      await deleteLabelById({ doctorId: doctor, labelId });
      await loadAll();
    } catch (error) {
      setStatus({ type: "error", text: t("manage.labels.deleteFailed", { message: error.message }) });
    }
  }

  async function onTogglePatientLabel(patient, label) {
    const doctor = doctorId.trim() || "web_doctor";
    const hasLabel = (patient.labels || []).some((l) => l.id === label.id);
    try {
      if (hasLabel) {
        await removeLabelFromPatient({ doctorId: doctor, patientId: patient.id, labelId: label.id });
      } else {
        await assignLabelToPatient({ doctorId: doctor, patientId: patient.id, labelId: label.id });
      }
      await loadAll();
    } catch (error) {
      setStatus({ type: "error", text: t("manage.labels.assignFailed", { message: error.message }) });
    }
  }

  return (
    <Box
      sx={{
        minHeight: "100vh",
        background:
          "radial-gradient(1150px 640px at 86% -12%, rgba(15,118,110,0.18), transparent 64%), radial-gradient(860px 520px at -6% 108%, rgba(47,79,111,0.14), transparent 62%), #f3f7f8",
      }}
    >
      <Container maxWidth="xl" sx={{ py: 2.5 }}>
        <Card sx={{ borderRadius: 1.5, mb: 1.5 }}>
          <CardContent sx={{ py: "10px !important", px: 1.2 }}>
            <Stack direction="row" spacing={1} sx={{ width: "100%" }}>
              <Button component={RouterLink} to="/" variant="outlined" size="small" startIcon={<ForumOutlinedIcon fontSize="small" />} sx={{ flex: 1 }}>
                {t("nav.openChat")}
              </Button>
              <Button component={RouterLink} to="/manage" variant="contained" size="small" disabled startIcon={<DashboardOutlinedIcon fontSize="small" />} sx={{ flex: 1 }}>
                {t("nav.openManage")}
              </Button>
            </Stack>
          </CardContent>
        </Card>

        <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: { xs: "1fr", lg: "300px minmax(0,1fr)" }, alignItems: "start" }}>
          <Stack spacing={1.4} sx={{ position: { lg: "sticky" }, top: { lg: 16 } }}>
            <Card sx={{ borderRadius: 1.5 }}>
              <CardContent>
                <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>{t("manage.pageTitle")}</Typography>
                <Typography variant="caption" color="text.secondary" sx={{ mt: 0.2, display: "block" }}>
                  {t("manage.pageSubtitle")}
                </Typography>
                <TextField
                  size="small"
                  label={t("chat.doctorId")}
                  value={doctorId}
                  onChange={(e) => setDoctorId(e.target.value)}
                  sx={{ mt: 1 }}
                  fullWidth
                />
              </CardContent>
            </Card>

            <Card sx={{ borderRadius: 1.5 }}>
              <CardContent sx={{ p: 1.8 }}>
                <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1 }}>
                  {t("manage.workspaceTitle")}
                </Typography>
                <Stack spacing={1}>
                  <NavTab active={tab === 0} onClick={() => setTab(0)} icon={<PeopleOutlineOutlinedIcon fontSize="small" />}>
                    {t("manage.tabPlain.patients")}
                  </NavTab>
                  <NavTab active={tab === 1} onClick={() => setTab(1)} icon={<AssignmentOutlinedIcon fontSize="small" />}>
                    {t("manage.tabPlain.records")}
                  </NavTab>
                  <NavTab active={tab === 3} onClick={() => setTab(3)} icon={<SellOutlinedIcon fontSize="small" />}>
                    {t("manage.tabPlain.tags")}
                  </NavTab>
                  <NavTab active={tab === 2} onClick={() => setTab(2)} icon={<TuneOutlinedIcon fontSize="small" />}>
                    {t("manage.tabPlain.customization")}
                  </NavTab>
                </Stack>
              </CardContent>
            </Card>

            <Card sx={{ borderRadius: 1.5 }}>
              <CardContent sx={{ p: 1.5 }}>
                <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.8 }}>
                  {t("manage.stats.title")}
                </Typography>
                <Stack spacing={0.4}>
                  {statsRows.map((row, idx) => (
                    <Box key={row.key}>
                      <Stack direction="row" alignItems="center" justifyContent="space-between">
                        <Stack direction="row" spacing={0.8} alignItems="center">
                          <Box sx={{ color: "text.secondary", display: "grid", placeItems: "center" }}>{row.icon}</Box>
                          <Typography variant="body2" color="text.secondary">{row.label}</Typography>
                        </Stack>
                        <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>{row.value}</Typography>
                      </Stack>
                      {idx < statsRows.length - 1 ? <Divider sx={{ mt: 0.55 }} /> : null}
                    </Box>
                  ))}
                </Stack>
              </CardContent>
            </Card>
          </Stack>

          <Card sx={{ borderRadius: 1.5 }}>
            <CardContent>
              {!!status.text ? <Alert severity={status.type} sx={{ mb: 1.5 }}>{status.text}</Alert> : null}

              <Stack direction="row" sx={{ justifyContent: "space-between", alignItems: "center", mb: 1.2 }}>
                <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
                  {t("manage.workspaceTitle")} · {activeTabLabel}
                </Typography>
                <Button variant="contained" size="small" onClick={() => loadAll()} disabled={loading}>
                  {loading ? t("common.loading") : t("manage.reload")}
                </Button>
              </Stack>

              {tab === 0 ? (
                <Stack spacing={1.25}>
                  <Card sx={{ borderRadius: 1.5 }}>
                    <CardContent sx={{ display: "flex", flexWrap: "wrap", gap: 1 }}>
                      <FormControl size="small" sx={{ minWidth: 170 }}>
                        <InputLabel id="risk-filter-label">{t("manage.filters.risk")}</InputLabel>
                        <Select labelId="risk-filter-label" label={t("manage.filters.risk")} value={riskFilter} onChange={(e) => setRiskFilter(e.target.value)}>
                          <MenuItem value="">{t("common.all")}</MenuItem>
                          <MenuItem value="critical">{t("manage.risk.critical")}</MenuItem>
                          <MenuItem value="high">{t("manage.risk.high")}</MenuItem>
                          <MenuItem value="medium">{t("manage.risk.medium")}</MenuItem>
                          <MenuItem value="low">{t("manage.risk.low")}</MenuItem>
                        </Select>
                      </FormControl>
                      <FormControl size="small" sx={{ minWidth: 190 }}>
                        <InputLabel id="followup-filter-label">{t("manage.filters.followUp")}</InputLabel>
                        <Select labelId="followup-filter-label" label={t("manage.filters.followUp")} value={followUpFilter} onChange={(e) => setFollowUpFilter(e.target.value)}>
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
                          onChange={(e) => setTagFilter(e.target.value)}
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

                  {displayedPatients.map((p) => {
                    const isExpanded = String(p.id) === expandedPatientId;
                    return (
                      <Card key={p.id} sx={{ borderRadius: 1.5 }}>
                        <CardContent sx={{ p: 1.5 }}>
                          <Stack direction={{ xs: "column", sm: "row" }} spacing={0.8} sx={{ justifyContent: "space-between", alignItems: { sm: "center" } }}>
                            <Stack direction="row" spacing={0.7} sx={{ alignItems: "center", flexWrap: "wrap" }}>
                              <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>{p.name}</Typography>
                              {p.primary_category ? <Chip size="small" label={`${t("manage.patient.categoryPrefix")}：${p.primary_category}`} /> : null}
                              {p.primary_risk_level ? <Chip size="small" color="warning" label={`${t("manage.patient.riskPrefix")}：${p.primary_risk_level}`} /> : null}
                              {p.follow_up_state ? <Chip size="small" variant="outlined" label={`${t("manage.patient.followUpPrefix")}：${p.follow_up_state}`} /> : null}
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
                              <Button
                                size="small"
                                variant="outlined"
                                onClick={() => {
                                  setTab(1);
                                  setRecordPatientNameFilter(p.name || "");
                                  setSelectedPatientId(String(p.id));
                                  loadAll({ recordPatientNameFilter: p.name || "" });
                                  loadTimeline(p.id);
                                }}
                              >
                                {t("manage.patient.filterRecords")}
                              </Button>
                              <Button
                                size="small"
                                variant={isExpanded ? "contained" : "outlined"}
                                onClick={() => setExpandedPatientId(isExpanded ? "" : String(p.id))}
                              >
                                {isExpanded ? t("manage.patient.hideDetails") : t("manage.patient.showDetails")}
                              </Button>
                            </Stack>
                          </Stack>

                          <Box sx={{ mt: 0.7 }}>
                            <Typography variant="caption" color="text.secondary">
                              {p.gender || t("manage.patient.genderUnknown")} | {p.year_of_birth ? `${new Date().getFullYear() - p.year_of_birth}${t("manage.patient.ageSuffix")}` : t("manage.patient.ageNA")} | {t("manage.patient.recordCount")}={p.record_count}
                            </Typography>
                            {isExpanded ? (
                              <Box sx={{ mt: 0.35 }}>
                                <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
                                  risk_score={p.risk_score ?? "-"} | risk_rules={p.risk_rules_version || "-"} | risk_at={p.risk_computed_at || "-"}
                                </Typography>
                                <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
                                  {t("manage.patient.createdAt")}：{p.created_at || "-"}
                                </Typography>
                              </Box>
                            ) : null}
                          </Box>
                        </CardContent>
                      </Card>
                    );
                  })}
                  {!displayedPatients.length ? <Typography color="text.secondary">{t("manage.patient.empty")}</Typography> : null}
                </Stack>
              ) : null}

              {tab === 1 ? (
                <Box>
                  <Card sx={{ borderRadius: 1.5, mb: 1.5 }}>
                    <CardContent sx={{ display: "flex", gap: 1, flexDirection: { xs: "column", sm: "row" } }}>
                      <TextField
                        size="small"
                        label={t("manage.filters.patientName")}
                        value={recordPatientNameFilter}
                        onChange={(e) => setRecordPatientNameFilter(e.target.value)}
                      />
                      <TextField
                        size="small"
                        type="date"
                        label={t("manage.filters.dateFrom")}
                        InputLabelProps={{ shrink: true }}
                        value={recordDateFrom}
                        onChange={(e) => setRecordDateFrom(e.target.value)}
                      />
                      <TextField
                        size="small"
                        type="date"
                        label={t("manage.filters.dateTo")}
                        InputLabelProps={{ shrink: true }}
                        value={recordDateTo}
                        onChange={(e) => setRecordDateTo(e.target.value)}
                      />
                      <Button variant="outlined" onClick={loadAll}>{t("common.apply")}</Button>
                    </CardContent>
                  </Card>

                  <Stack spacing={1.25}>
                    {records.map((r) => (
                      <Card key={r.id} sx={{ borderRadius: 1.5 }}>
                        <CardContent sx={{ p: 1.5 }}>
                          <Stack
                            direction={{ xs: "column", sm: "row" }}
                            spacing={0.8}
                            sx={{ justifyContent: "space-between", alignItems: { sm: "center" } }}
                          >
                            <Box>
                              <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
                                {t("manage.record.patientName")}：{r.patient_name || t("manage.record.unlinkedPatient")}
                              </Typography>
                              <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.15 }}>
                                {t("manage.record.date")}：{r.created_at || "-"}
                              </Typography>
                              <Typography variant="caption" sx={{ display: "block", mt: 0.35 }}>
                                {t("manage.record.chiefComplaint")}：{r.chief_complaint || t("manage.record.noChiefComplaint")}
                              </Typography>
                            </Box>
                            <Stack direction="row" spacing={0.7}>
                              <Chip size="small" label={t("manage.record.recordTag")} />
                              <Button
                                size="small"
                                variant={String(r.id) === expandedRecordId ? "contained" : "outlined"}
                                onClick={() =>
                                  setExpandedRecordId(String(r.id) === expandedRecordId ? "" : String(r.id))
                                }
                              >
                                {String(r.id) === expandedRecordId
                                  ? t("manage.record.hideDetails")
                                  : t("manage.record.showDetails")}
                              </Button>
                            </Stack>
                          </Stack>
                          {String(r.id) === expandedRecordId ? (
                            <>
                              <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1 }}>
                                {t("manage.record.rawFieldView")}
                              </Typography>
                              <TableContainer
                                sx={{
                                  mt: 0.6,
                                  border: "1px solid #d8e3e8",
                                  borderRadius: 1.5,
                                  backgroundColor: "#f8fbfc",
                                }}
                              >
                                <Table size="small">
                                  <TableBody>
                                    {getRecordDisplayRows(r).map((row) => (
                                      <TableRow key={`${r.id}-${row.key}`}>
                                        <TableCell
                                          sx={{
                                            width: "34%",
                                            fontWeight: 700,
                                            color: "text.secondary",
                                            borderBottom: "1px solid #e4edf0",
                                          }}
                                        >
                                          {row.label}
                                        </TableCell>
                                        <TableCell
                                          sx={{
                                            whiteSpace: "pre-wrap",
                                            wordBreak: "break-word",
                                            borderBottom: "1px solid #e4edf0",
                                          }}
                                        >
                                          {row.value}
                                        </TableCell>
                                      </TableRow>
                                    ))}
                                  </TableBody>
                                </Table>
                              </TableContainer>
                            </>
                          ) : null}
                        </CardContent>
                      </Card>
                    ))}
                    {!records.length ? <Typography color="text.secondary">{t("manage.record.empty")}</Typography> : null}
                  </Stack>

                  <Divider sx={{ my: 2.2 }} />
                  <Typography variant="subtitle1" sx={{ fontWeight: 700, mb: 1 }}>{t("manage.timeline.title")}</Typography>
                  {!selectedPatientId ? <Typography color="text.secondary">{t("manage.timeline.emptyHint")}</Typography> : null}
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
                                {e.type === "record" ? t("manage.timeline.summary.record") : t("manage.timeline.summary.task")}：{getTimelineSummary(e)}
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
                            <TableContainer
                              sx={{
                                mt: 0.8,
                                border: "1px solid #d8e3e8",
                                borderRadius: 1.5,
                                backgroundColor: "#f8fbfc",
                              }}
                            >
                              <Table size="small">
                                <TableBody>
                                  {getTimelineRows(e).map((row) => (
                                    <TableRow key={`${getTimelineEventKey(e)}-${row.key}`}>
                                      <TableCell
                                        sx={{
                                          width: "34%",
                                          fontWeight: 700,
                                          color: "text.secondary",
                                          borderBottom: "1px solid #e4edf0",
                                        }}
                                      >
                                        {row.label}
                                      </TableCell>
                                      <TableCell
                                        sx={{
                                          whiteSpace: "pre-wrap",
                                          wordBreak: "break-word",
                                          borderBottom: "1px solid #e4edf0",
                                        }}
                                      >
                                        {row.value}
                                      </TableCell>
                                    </TableRow>
                                  ))}
                                </TableBody>
                              </Table>
                            </TableContainer>
                          ) : null}
                        </CardContent>
                      </Card>
                    ))}
                    {selectedPatientId && !timeline.length ? <Typography color="text.secondary">{t("manage.timeline.empty")}</Typography> : null}
                  </Stack>
                </Box>
              ) : null}

              {tab === 2 ? (
                <Stack spacing={1.5}>
                  <Card sx={{ borderRadius: 1.5 }}>
                    <CardContent>
                      <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>{t("manage.prompt.base")}</Typography>
                      <TextField multiline minRows={8} fullWidth value={basePrompt} onChange={(e) => setBasePrompt(e.target.value)} sx={{ mt: 1 }} />
                      <Button sx={{ mt: 1 }} variant="contained" onClick={() => savePrompt("structuring", basePrompt)}>
                        {t("manage.prompt.saveBase")}
                      </Button>
                    </CardContent>
                  </Card>
                  <Card sx={{ borderRadius: 1.5 }}>
                    <CardContent>
                      <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>{t("manage.prompt.ext")}</Typography>
                      <TextField multiline minRows={8} fullWidth value={extPrompt} onChange={(e) => setExtPrompt(e.target.value)} sx={{ mt: 1 }} />
                      <Button sx={{ mt: 1 }} variant="contained" onClick={() => savePrompt("structuring.extension", extPrompt)}>
                        {t("manage.prompt.saveExt")}
                      </Button>
                    </CardContent>
                  </Card>
                </Stack>
              ) : null}

              {tab === 3 ? (
                <Stack spacing={1.25}>
                  <Card sx={{ borderRadius: 1.5 }}>
                    <CardContent>
                      <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1 }}>
                        {t("manage.labels.title")}
                      </Typography>
                      <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
                        <TextField size="small" label={t("manage.labels.name")} value={newLabelName} onChange={(e) => setNewLabelName(e.target.value)} />
                        <TextField size="small" type="color" label={t("manage.labels.color")} value={newLabelColor} onChange={(e) => setNewLabelColor(e.target.value)} sx={{ width: { xs: "100%", sm: 96 } }} />
                        <Button variant="contained" onClick={onCreateLabel}>{t("manage.labels.add")}</Button>
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
                        {!labels.length ? <Typography variant="caption" color="text.secondary">{t("manage.labels.empty")}</Typography> : null}
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
                          onChange={(e) => setTagFilter(e.target.value)}
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
                        {displayedPatients.map((p) => (
                          <Box key={`tag-row-${p.id}`}>
                            <Typography variant="body2" sx={{ mb: 0.6, fontWeight: 600 }}>{p.name}</Typography>
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
                                    onClick={() => onTogglePatientLabel(p, label)}
                                  />
                                );
                              })}
                            </Stack>
                          </Box>
                        ))}
                        {!displayedPatients.length ? <Typography color="text.secondary">{t("manage.patient.empty")}</Typography> : null}
                      </Stack>
                    </CardContent>
                  </Card>
                </Stack>
              ) : null}
            </CardContent>
          </Card>
        </Box>
      </Container>
    </Box>
  );
}
