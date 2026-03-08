import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { setWebToken } from "../api";
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Container,
  Divider,
  Stack,
  Typography,
} from "@mui/material";
import FolderSharedOutlinedIcon from "@mui/icons-material/FolderSharedOutlined";
import DescriptionOutlinedIcon from "@mui/icons-material/DescriptionOutlined";
import WarningAmberRoundedIcon from "@mui/icons-material/WarningAmberRounded";
import EventBusyOutlinedIcon from "@mui/icons-material/EventBusyOutlined";
import LabelOutlinedIcon from "@mui/icons-material/LabelOutlined";
import AssignmentLateOutlinedIcon from "@mui/icons-material/AssignmentLateOutlined";
import PeopleOutlineOutlinedIcon from "@mui/icons-material/PeopleOutlineOutlined";
import AssignmentOutlinedIcon from "@mui/icons-material/AssignmentOutlined";
import TuneOutlinedIcon from "@mui/icons-material/TuneOutlined";
import SellOutlinedIcon from "@mui/icons-material/SellOutlined";
import ForumOutlinedIcon from "@mui/icons-material/ForumOutlined";
import DashboardOutlinedIcon from "@mui/icons-material/DashboardOutlined";
import { Link as RouterLink } from "react-router-dom";
import {
  assignLabelToPatient,
  getPatientTimeline,
  getRecords,
  getPrompts,
  removeLabelFromPatient,
  updatePrompt,
} from "../api";
import { t } from "../i18n";
import { useDoctorStore } from "../store/doctorStore";
import { usePatientData } from "../hooks/usePatientData";
import { useTaskData } from "../hooks/useTaskData";
import { useLabelData } from "../hooks/useLabelData";
import PatientPanel from "../components/manage/PatientPanel";
import TaskPanel from "../components/manage/TaskPanel";
import RecordPanel from "../components/manage/RecordPanel";
import LabelPanel from "../components/manage/LabelPanel";
import PromptPanel from "../components/manage/PromptPanel";

const TABS = [
  { id: 0, key: "patients", icon: <PeopleOutlineOutlinedIcon fontSize="small" /> },
  { id: 1, key: "tasks", icon: <AssignmentOutlinedIcon fontSize="small" /> },
  { id: 2, key: "records", icon: <DescriptionOutlinedIcon fontSize="small" /> },
  { id: 3, key: "tags", icon: <SellOutlinedIcon fontSize="small" /> },
  { id: 4, key: "customization", icon: <TuneOutlinedIcon fontSize="small" /> },
];

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
  const navigate = useNavigate();
  const { doctorId, doctorName, clearAuth } = useDoctorStore();
  const [tab, setTab] = useState(0);

  function onLogout() {
    setWebToken("");
    clearAuth();
    navigate("/login", { replace: true });
  }
  const [status, setStatus] = useState({ type: "info", text: "" });

  const [riskFilter, setRiskFilter] = useState("");
  const [followUpFilter, setFollowUpFilter] = useState("");
  const [tagFilter, setTagFilter] = useState("");

  // Records state (kept inline — complex with timeline)
  const [records, setRecords] = useState([]);
  const [recordsLoading, setRecordsLoading] = useState(false);
  const [recordPatientNameFilter, setRecordPatientNameFilter] = useState("");
  const [recordDateFrom, setRecordDateFrom] = useState("");
  const [recordDateTo, setRecordDateTo] = useState("");
  const [timeline, setTimeline] = useState([]);
  const [selectedPatientId, setSelectedPatientId] = useState("");

  // Prompt state (kept inline — belongs to PromptPanel only)
  const [basePrompt, setBasePrompt] = useState("");
  const [extPrompt, setExtPrompt] = useState("");

  const doctor = doctorId || "";

  const { patients, loading: patientsLoading, reload: reloadPatients } = usePatientData(doctor, riskFilter, followUpFilter);
  const { tasks, loading: tasksLoading, error: taskError, reload: reloadTasks, completeTask, cancelTask } = useTaskData(doctor);
  const { labels, reload: reloadLabels, createLabel: createLabelFn, deleteLabel: deleteLabelFn } = useLabelData(doctor);

  const loading = patientsLoading || recordsLoading || tasksLoading;

  const highRiskCount = useMemo(
    () => patients.filter((p) => p.primary_risk_level === "high" || p.primary_risk_level === "critical").length,
    [patients]
  );
  const overdueCount = useMemo(
    () => patients.filter((p) => p.follow_up_state === "overdue").length,
    [patients]
  );
  const pendingTaskCount = useMemo(
    () => tasks.filter((tk) => tk.status === "pending").length,
    [tasks]
  );

  const statsRows = [
    { key: "patients", label: t("manage.stats.patients"), value: patients.length, icon: <FolderSharedOutlinedIcon fontSize="small" /> },
    { key: "records", label: t("manage.stats.records"), value: records.length, icon: <DescriptionOutlinedIcon fontSize="small" /> },
    { key: "highRisk", label: t("manage.stats.highRisk"), value: highRiskCount, icon: <WarningAmberRoundedIcon fontSize="small" /> },
    { key: "overdue", label: t("manage.stats.overdue"), value: overdueCount, icon: <EventBusyOutlinedIcon fontSize="small" /> },
    { key: "pendingTasks", label: t("manage.stats.pendingTasks"), value: pendingTaskCount, icon: <AssignmentLateOutlinedIcon fontSize="small" /> },
    { key: "tags", label: t("manage.stats.tags"), value: labels.length, icon: <LabelOutlinedIcon fontSize="small" /> },
  ];

  async function loadRecords(overrides = {}) {
    setRecordsLoading(true);
    setStatus({ type: "info", text: "" });
    try {
      const nextPatientName = overrides.recordPatientNameFilter ?? recordPatientNameFilter;
      const nextDateFrom = overrides.recordDateFrom ?? recordDateFrom;
      const nextDateTo = overrides.recordDateTo ?? recordDateTo;
      const [r, prompts] = await Promise.all([
        getRecords({ doctorId: doctor, patientName: nextPatientName.trim(), dateFrom: nextDateFrom, dateTo: nextDateTo }),
        getPrompts(),
      ]);
      setRecords(r.items || []);
      setBasePrompt(prompts.structuring || "");
      setExtPrompt(prompts.structuring_extension || "");
    } catch (error) {
      setStatus({ type: "error", text: t("manage.loadFailed", { message: error.message }) });
    } finally {
      setRecordsLoading(false);
    }
  }

  async function reloadAll() {
    reloadPatients();
    reloadTasks();
    reloadLabels();
    await loadRecords();
  }

  async function savePrompt(key, content) {
    try {
      await updatePrompt(key, content);
      setStatus({ type: "success", text: t("manage.promptSaved", { key }) });
    } catch (error) {
      setStatus({ type: "error", text: t("manage.saveFailed", { message: error.message }) });
    }
  }

  async function loadTimeline(patientId) {
    if (!patientId) return;
    try {
      const data = await getPatientTimeline({ doctorId: doctor, patientId, limit: 100 });
      setTimeline(data.events || []);
    } catch (error) {
      setStatus({ type: "error", text: t("manage.timelineLoadFailed", { message: error.message }) });
      setTimeline([]);
    }
  }

  async function onCreateLabel(name, color) {
    try {
      await createLabelFn(name, color);
    } catch (error) {
      setStatus({ type: "error", text: t("manage.labels.createFailed", { message: error.message }) });
    }
  }

  async function onDeleteLabel(labelId) {
    try {
      await deleteLabelFn(labelId);
      reloadPatients();
    } catch (error) {
      setStatus({ type: "error", text: t("manage.labels.deleteFailed", { message: error.message }) });
    }
  }

  async function onTogglePatientLabel(patient, label) {
    const hasLabel = (patient.labels || []).some((l) => l.id === label.id);
    try {
      if (hasLabel) {
        await removeLabelFromPatient({ doctorId: doctor, patientId: patient.id, labelId: label.id });
      } else {
        await assignLabelToPatient({ doctorId: doctor, patientId: patient.id, labelId: label.id });
      }
      reloadPatients();
      reloadLabels();
    } catch (error) {
      setStatus({ type: "error", text: t("manage.labels.assignFailed", { message: error.message }) });
    }
  }

  async function onCompleteTask(taskId) {
    try {
      await completeTask(taskId);
    } catch (error) {
      setStatus({ type: "error", text: t("manage.tasks.updateFailed", { message: error.message }) });
    }
  }

  async function onCancelTask(taskId) {
    try {
      await cancelTask(taskId);
    } catch (error) {
      setStatus({ type: "error", text: t("manage.tasks.updateFailed", { message: error.message }) });
    }
  }

  function onViewRecords(patient) {
    setTab(2);
    setRecordPatientNameFilter(patient.name || "");
    setSelectedPatientId(String(patient.id));
    loadRecords({ recordPatientNameFilter: patient.name || "" });
    loadTimeline(patient.id);
  }

  const activeTabLabel = TABS.find((tb) => tb.id === tab)?.key || "patients";

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
          {/* Sidebar */}
          <Stack spacing={1.4} sx={{ position: { lg: "sticky" }, top: { lg: 16 } }}>
            <Card sx={{ borderRadius: 1.5 }}>
              <CardContent>
                <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>{t("manage.pageTitle")}</Typography>
                <Typography variant="caption" color="text.secondary" sx={{ mt: 0.2, display: "block" }}>
                  {t("manage.pageSubtitle")}
                </Typography>
                <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mt: 1 }}>
                  <Typography variant="body2" color="text.secondary">
                    {t("login.loggedInAs")}：<strong>{doctorName || doctorId}</strong>
                  </Typography>
                  <Button size="small" color="inherit" onClick={onLogout} sx={{ ml: 1, flexShrink: 0 }}>
                    {t("login.logout")}
                  </Button>
                </Stack>
              </CardContent>
            </Card>

            <Card sx={{ borderRadius: 1.5 }}>
              <CardContent sx={{ p: 1.8 }}>
                <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1 }}>
                  {t("manage.workspaceTitle")}
                </Typography>
                <Stack spacing={1}>
                  {TABS.map((tb) => (
                    <NavTab key={tb.id} active={tab === tb.id} onClick={() => setTab(tb.id)} icon={tb.icon}>
                      {t(`manage.tabPlain.${tb.key}`)}
                      {tb.key === "tasks" && pendingTaskCount > 0 ? (
                        <Box
                          component="span"
                          sx={{ ml: 0.8, px: 0.8, py: 0.1, bgcolor: "error.main", color: "#fff", borderRadius: 8, fontSize: "0.7rem", fontWeight: 700 }}
                        >
                          {pendingTaskCount}
                        </Box>
                      ) : null}
                    </NavTab>
                  ))}
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

          {/* Main content */}
          <Card sx={{ borderRadius: 1.5 }}>
            <CardContent>
              {status.text ? <Alert severity={status.type} sx={{ mb: 1.5 }}>{status.text}</Alert> : null}

              <Stack direction="row" sx={{ justifyContent: "space-between", alignItems: "center", mb: 1.2 }}>
                <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
                  {t("manage.workspaceTitle")} · {t(`manage.tabPlain.${activeTabLabel}`)}
                </Typography>
                <Button
                  variant="contained"
                  size="small"
                  onClick={reloadAll}
                  disabled={loading}
                >
                  {loading ? t("common.loading") : t("manage.reload")}
                </Button>
              </Stack>

              {tab === 0 ? (
                <PatientPanel
                  patients={patients}
                  labels={labels}
                  riskFilter={riskFilter}
                  followUpFilter={followUpFilter}
                  tagFilter={tagFilter}
                  loading={patientsLoading}
                  onRiskFilterChange={setRiskFilter}
                  onFollowUpFilterChange={setFollowUpFilter}
                  onTagFilterChange={setTagFilter}
                  onViewRecords={onViewRecords}
                  onToggleLabel={onTogglePatientLabel}
                />
              ) : null}

              {tab === 1 ? (
                <TaskPanel
                  tasks={tasks}
                  loading={tasksLoading}
                  error={taskError}
                  onComplete={onCompleteTask}
                  onCancel={onCancelTask}
                />
              ) : null}

              {tab === 2 ? (
                <RecordPanel
                  records={records}
                  timeline={timeline}
                  selectedPatientId={selectedPatientId}
                  doctorId={doctor}
                  patientNameFilter={recordPatientNameFilter}
                  dateFrom={recordDateFrom}
                  dateTo={recordDateTo}
                  loading={recordsLoading}
                  onPatientNameFilterChange={setRecordPatientNameFilter}
                  onDateFromChange={setRecordDateFrom}
                  onDateToChange={setRecordDateTo}
                  onApplyFilters={loadRecords}
                />
              ) : null}

              {tab === 3 ? (
                <LabelPanel
                  labels={labels}
                  patients={patients}
                  tagFilter={tagFilter}
                  onTagFilterChange={setTagFilter}
                  onCreateLabel={onCreateLabel}
                  onDeleteLabel={onDeleteLabel}
                  onToggleLabel={onTogglePatientLabel}
                />
              ) : null}

              {tab === 4 ? (
                <PromptPanel
                  basePrompt={basePrompt}
                  extPrompt={extPrompt}
                  onBaseChange={setBasePrompt}
                  onExtChange={setExtPrompt}
                  onSave={savePrompt}
                />
              ) : null}
            </CardContent>
          </Card>
        </Box>
      </Container>
    </Box>
  );
}
