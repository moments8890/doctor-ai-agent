import { useEffect, useMemo, useState } from "react";
import { Navigate, useLocation, useNavigate, useParams } from "react-router-dom";
import {
  Alert,
  Autocomplete,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Container,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  IconButton,
  MenuItem,
  Paper,
  Stack,
  Switch,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Tooltip,
  Typography,
} from "@mui/material";
import StorageOutlinedIcon from "@mui/icons-material/StorageOutlined";
import DownloadOutlinedIcon from "@mui/icons-material/DownloadOutlined";
import ContentCopyOutlinedIcon from "@mui/icons-material/ContentCopyOutlined";
import PeopleOutlineOutlinedIcon from "@mui/icons-material/PeopleOutlineOutlined";
import DescriptionOutlinedIcon from "@mui/icons-material/DescriptionOutlined";
import AssignmentOutlinedIcon from "@mui/icons-material/AssignmentOutlined";
import PsychologyAltOutlinedIcon from "@mui/icons-material/PsychologyAltOutlined";
import LabelOutlinedIcon from "@mui/icons-material/LabelOutlined";
import LinkOutlinedIcon from "@mui/icons-material/LinkOutlined";
import TextSnippetOutlinedIcon from "@mui/icons-material/TextSnippetOutlined";
import AccountTreeOutlinedIcon from "@mui/icons-material/AccountTreeOutlined";
import BadgeOutlinedIcon from "@mui/icons-material/BadgeOutlined";
import TuneOutlinedIcon from "@mui/icons-material/TuneOutlined";
import UnfoldMoreIcon from "@mui/icons-material/UnfoldMore";
import ArrowUpwardIcon from "@mui/icons-material/ArrowUpward";
import ArrowDownwardIcon from "@mui/icons-material/ArrowDownward";
import EditOutlinedIcon from "@mui/icons-material/EditOutlined";
import {
  getAdminFilterOptions,
  getAdminRuntimeConfig,
  getAdminRoutingKeywords,
  getAdminTableRows,
  getAdminTables,
  applyAdminRuntimeConfig,
  putAdminRoutingKeywords,
  reloadAdminRoutingKeywords,
  updateAdminRuntimeConfig,
  verifyAdminRuntimeConfig,
  getAdminTunnelUrl,
  setAdminToken,
  onAdminAuthError,
  getAdminRoutingMetrics,
  getAdminInviteCodes,
  createAdminInviteCode,
  revokeAdminInviteCode,
  updateAdminRecord,
} from "../api";
import { t } from "../i18n";

const ADMIN_TOKEN_KEY = "adminToken";


const TABLES = [
  { key: "doctors", icon: <BadgeOutlinedIcon fontSize="small" /> },
  { key: "patients", icon: <PeopleOutlineOutlinedIcon fontSize="small" /> },
  { key: "medical_records", icon: <DescriptionOutlinedIcon fontSize="small" /> },
  { key: "doctor_tasks", icon: <AssignmentOutlinedIcon fontSize="small" /> },
  { key: "neuro_cases", icon: <PsychologyAltOutlinedIcon fontSize="small" /> },
  { key: "patient_labels", icon: <LabelOutlinedIcon fontSize="small" /> },
  { key: "patient_label_assignments", icon: <LinkOutlinedIcon fontSize="small" /> },
  { key: "system_prompts", icon: <TextSnippetOutlinedIcon fontSize="small" /> },
  { key: "doctor_contexts", icon: <AccountTreeOutlinedIcon fontSize="small" /> },
];
const NAV_TABS = [
  { key: "invite_codes", icon: <BadgeOutlinedIcon fontSize="small" /> },
  ...TABLES,
  { key: "runtime_config", icon: <TuneOutlinedIcon fontSize="small" /> },
  { key: "routing_keywords", icon: <TuneOutlinedIcon fontSize="small" /> },
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

const RECORD_EDIT_FIELDS = [
  { key: "chief_complaint", label: "主诉" },
  { key: "history_of_present_illness", label: "现病史" },
  { key: "past_medical_history", label: "既往史" },
  { key: "physical_examination", label: "体格检查" },
  { key: "auxiliary_examinations", label: "辅助检查" },
  { key: "diagnosis", label: "诊断" },
  { key: "treatment_plan", label: "治疗方案" },
  { key: "follow_up_plan", label: "随访计划" },
];

function toCell(value) {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function renderCellContent(value) {
  if (value === null || value === undefined || value === "") {
    return <span style={{ color: "#b0bec5" }}>—</span>;
  }
  if (typeof value === "boolean") {
    return (
      <Chip
        label={value ? "true" : "false"}
        size="small"
        color={value ? "success" : "default"}
        sx={{ height: 18, fontSize: 10, fontFamily: "inherit" }}
      />
    );
  }
  const str = typeof value === "object" ? JSON.stringify(value) : String(value);
  // Format ISO datetime strings
  if (/^\d{4}-\d{2}-\d{2}T/.test(str)) {
    return <span style={{ whiteSpace: "nowrap" }}>{str.slice(0, 16).replace("T", " ")}</span>;
  }
  if (str.length > 90) {
    return (
      <Tooltip title={str} placement="top" arrow>
        <span style={{ cursor: "pointer" }}>
          {str.slice(0, 90)}<span style={{ color: "#94a3b8" }}>…</span>
        </span>
      </Tooltip>
    );
  }
  return str;
}


const COL_WIDTH = {
  id: 64,
  key: 140,
  patient_id: 84,
  doctor_id: 144,
  patient_name: 112,
  name: 112,
  gender: 72,
  year_of_birth: 88,
  chief_complaint: 220,
  diagnosis: 180,
  primary_diagnosis: 180,
  treatment_plan: 240,
  follow_up_plan: 220,
  title: 220,
  summary: 260,
  content: 320,
  created_at: 164,
  updated_at: 164,
  due_at: 164,
};

export default function AdminPage() {
  const location = useLocation();
  // "verifying" while checking stored token, "ok" once confirmed, "locked" if no/bad token
  const [status, setStatus] = useState(() =>
    localStorage.getItem(ADMIN_TOKEN_KEY) ? "verifying" : "locked"
  );

  function handleLockout() {
    localStorage.removeItem(ADMIN_TOKEN_KEY);
    setAdminToken("");
    setStatus("locked");
  }

  useEffect(() => {
    onAdminAuthError(handleLockout);
    const stored = localStorage.getItem(ADMIN_TOKEN_KEY) || "";
    if (stored) {
      setAdminToken(stored);
      getAdminRoutingMetrics()
        .then(() => setStatus("ok"))
        .catch(() => {
          localStorage.removeItem(ADMIN_TOKEN_KEY);
          setAdminToken("");
          setStatus("locked");
        });
    }
    return () => onAdminAuthError(null);
  }, []);

  if (status === "verifying") return null;
  if (status === "locked") {
    return (
      <Navigate
        to="/admin/login"
        replace
        state={{ next: location.pathname, error: "Token 不正确，请重新输入" }}
      />
    );
  }
  return <AdminDashboard onLockout={handleLockout} />;
}

function AdminDashboard({ onLockout }) {
  const [doctorId, setDoctorId] = useState("");
  const [patientName, setPatientName] = useState("");
  const [doctorInput, setDoctorInput] = useState("");
  const [patientInput, setPatientInput] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const { section } = useParams();
  const navigate = useNavigate();
  const activeTable = NAV_TABS.some((t) => t.key === section) ? section : "patients";
  function setActiveTable(key) { navigate(`/admin/${key}`); }
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState({ type: "info", text: "" });
  const [tableCounts, setTableCounts] = useState({});
  const [rows, setRows] = useState([]);
  const [runtimeConfigMap, setRuntimeConfigMap] = useState({});
  const [runtimeCategories, setRuntimeCategories] = useState([]);
  const [runtimeConfigSource, setRuntimeConfigSource] = useState("");
  const [tunnelInfo, setTunnelInfo] = useState({ ok: false, url: "", source: "", updated_at: "", detail: "" });
  const [doctorOptions, setDoctorOptions] = useState([]);
  const [patientOptions, setPatientOptions] = useState([]);
  const [routingKeywords, setRoutingKeywords] = useState({});
  const [newKwInputs, setNewKwInputs] = useState({});
  const [inviteCodes, setInviteCodes] = useState([]);
  const [newInviteDoctorId, setNewInviteDoctorId] = useState("");
  const [newInviteName, setNewInviteName] = useState("");
  const [sortCol, setSortCol] = useState("");
  const [sortDir, setSortDir] = useState("asc");
  const [selectedRow, setSelectedRow] = useState(null);
  const [rowEditMode, setRowEditMode] = useState(false);
  const [rowEditForm, setRowEditForm] = useState({});
  const [rowSaving, setRowSaving] = useState(false);
  const columns = useMemo(() => {
    const allKeys = [];
    for (const row of rows) {
      for (const key of Object.keys(row || {})) {
        if (!allKeys.includes(key)) allKeys.push(key);
      }
    }
    return allKeys;
  }, [rows]);

  const activeLabel = t(`admin.tables.${activeTable}`);
  const colCount = columns.length + 1;

  const sortedRows = useMemo(() => {
    if (!sortCol) return rows;
    return [...rows].sort((a, b) => {
      const av = a[sortCol] ?? "";
      const bv = b[sortCol] ?? "";
      const cmp = String(av).localeCompare(String(bv), undefined, { numeric: true });
      return sortDir === "asc" ? cmp : -cmp;
    });
  }, [rows, sortCol, sortDir]);

  function handleSort(col) {
    if (sortCol === col) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortCol(col);
      setSortDir("asc");
    }
  }

  async function saveRowEdit() {
    if (!selectedRow) return;
    setRowSaving(true);
    try {
      const saved = await updateAdminRecord(selectedRow.id, rowEditForm);
      setRows((prev) => prev.map((r) => (r.id === saved.id ? { ...r, ...saved } : r)));
      setSelectedRow((prev) => ({ ...prev, ...saved }));
      setRowEditMode(false);
      setStatus({ type: "success", text: "记录已保存" });
    } catch (e) {
      setStatus({ type: "error", text: e.message || "保存失败" });
    } finally {
      setRowSaving(false);
    }
  }

  const prefixFilter = (options, { inputValue }) => {
    const needle = (inputValue || "").trim().toLowerCase();
    return needle
      ? options.filter((opt) => String(opt).toLowerCase().startsWith(needle))
      : options;
  };
  const isTruthyValue = (value) => ["1", "true", "yes", "on"].includes(String(value || "").toLowerCase());

  function escapeCsv(value) {
    const text = toCell(value).replace(/"/g, '""');
    return `"${text}"`;
  }

  function downloadFile(filename, content, mime) {
    const blob = new Blob([content], { type: mime });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  }

  function exportJson() {
    const payload = JSON.stringify(rows, null, 2);
    downloadFile(`${activeTable}.json`, payload, "application/json;charset=utf-8");
  }

  function exportCsv() {
    const head = columns.map((col) => escapeCsv(t(`admin.cols.${col}`))).join(",");
    const body = rows
      .map((row) => columns.map((col) => escapeCsv(row[col])).join(","))
      .join("\n");
    const csv = [head, body].filter(Boolean).join("\n");
    downloadFile(`${activeTable}.csv`, csv, "text/csv;charset=utf-8");
  }

  async function copyRow(row) {
    try {
      await navigator.clipboard.writeText(JSON.stringify(row, null, 2));
      setStatus({ type: "success", text: t("admin.copySuccess") });
    } catch (error) {
      setStatus({ type: "error", text: t("admin.copyFailed", { message: error.message }) });
    }
  }

  function _resolveFilters(overrides = {}) {
    return {
      doctorId: (overrides.doctorId ?? doctorId).trim(),
      patientName: (overrides.patientName ?? patientName).trim(),
      dateFrom: overrides.dateFrom ?? dateFrom,
      dateTo: overrides.dateTo ?? dateTo,
    };
  }

  async function loadTableList(overrides = {}) {
    const f = _resolveFilters(overrides);
    const data = await getAdminTables({
      doctorId: f.doctorId,
      patientName: f.patientName,
      dateFrom: f.dateFrom,
      dateTo: f.dateTo,
    });
    const next = {};
    for (const item of data.items || []) {
      next[item.key] = item.count;
    }
    setTableCounts(next);
  }

  async function loadFilterOptions(doctorIdOverride = null) {
    const effectiveDoctorId = doctorIdOverride !== null ? doctorIdOverride : doctorId.trim();
    const data = await getAdminFilterOptions({ doctorId: effectiveDoctorId });
    setDoctorOptions(data.doctor_ids || []);
    setPatientOptions(data.patient_names || []);
  }

  async function loadTableData(tableKey = activeTable, overrides = {}) {
    if (tableKey === "observability") {
      setRows([]);
      return;
    }
    const f = _resolveFilters(overrides);
    const data = await getAdminTableRows({
      tableKey,
      doctorId: f.doctorId,
      patientName: f.patientName,
      dateFrom: f.dateFrom,
      dateTo: f.dateTo,
      limit: 300,
    });
    setRows(data.items || []);
  }

  async function loadRuntimeConfig() {
    const data = await getAdminRuntimeConfig();
    setRuntimeConfigSource(data.source || "");
    setRuntimeConfigMap(data.config || {});
    setRuntimeCategories(data.categories || []);
  }

  async function loadTunnelUrl() {
    const data = await getAdminTunnelUrl();
    setTunnelInfo({
      ok: !!data.ok,
      url: data.url || "",
      source: data.source || "",
      updated_at: data.updated_at || "",
      detail: data.detail || "",
    });
  }

  async function loadRoutingKeywords() {
    const payload = await getAdminRoutingKeywords();
    setRoutingKeywords(payload.config || {});
  }

  async function saveRuntimeConfig() {
    try {
      const payload = await updateAdminRuntimeConfig(runtimeConfigMap);
      setRuntimeConfigSource(payload.source || "");
      setRuntimeConfigMap(payload.config || {});
      setRuntimeCategories(payload.categories || []);
      setStatus({ type: "success", text: "配置已保存（未应用）。请先验证，再手动应用。" });
    } catch (error) {
      setStatus({ type: "error", text: t("admin.config.saveFailed", { message: error.message }) });
    }
  }

  async function verifyRuntimeConfig() {
    try {
      const payload = await verifyAdminRuntimeConfig(runtimeConfigMap);
      setRuntimeConfigMap(payload.config || {});
      setRuntimeCategories(payload.categories || []);
      const errors = payload.errors || [];
      const warnings = payload.warnings || [];
      if (!payload.ok) {
        setStatus({ type: "error", text: `配置校验失败：${errors.join("；") || "未知错误"}` });
        return;
      }
      if (warnings.length) {
        setStatus({ type: "warning", text: `配置校验通过（含警告）：${warnings.join("；")}` });
        return;
      }
      setStatus({ type: "success", text: "配置校验通过。" });
    } catch (error) {
      setStatus({ type: "error", text: `配置校验失败：${error.message}` });
    }
  }

  async function applyRuntimeConfigNow() {
    try {
      const payload = await applyAdminRuntimeConfig();
      setRuntimeConfigSource(payload.source || "");
      setRuntimeConfigMap(payload.config || {});
      setRuntimeCategories(payload.categories || []);
      setStatus({ type: "success", text: "配置已应用并热更新。" });
    } catch (error) {
      setStatus({ type: "error", text: `配置应用失败：${error.message}` });
    }
  }

  function updateRuntimeValue(key, nextValue) {
    setRuntimeConfigMap((prev) => ({ ...prev, [key]: nextValue }));
    setRuntimeCategories((prev) =>
      prev.map((cat) => ({
        ...cat,
        items: (cat.items || []).map((item) => (item.key === key ? { ...item, value: nextValue } : item)),
      }))
    );
  }

  async function loadInviteCodes() {
    const data = await getAdminInviteCodes();
    setInviteCodes(data.items || []);
  }

  async function onCreateInviteCode() {
    const id = newInviteDoctorId.trim();
    if (!id) return;
    try {
      await createAdminInviteCode(id, newInviteName.trim() || undefined);
      setNewInviteDoctorId("");
      setNewInviteName("");
      await loadInviteCodes();
    } catch (error) {
      setStatus({ type: "error", text: error.message });
    }
  }

  async function onRevokeInviteCode(code) {
    try {
      await revokeAdminInviteCode(code);
      await loadInviteCodes();
    } catch (error) {
      setStatus({ type: "error", text: error.message });
    }
  }

  async function loadAll(tableKey = activeTable, overrides = {}) {
    setLoading(true);
    setStatus({ type: "info", text: "" });
    try {
      const f = _resolveFilters(overrides);
      if (tableKey === "runtime_config") {
        await Promise.all([loadTableList(f), loadRuntimeConfig(), loadTunnelUrl(), loadFilterOptions(f.doctorId)]);
        setRows([]);
      } else if (tableKey === "routing_keywords") {
        await Promise.all([loadTableList(f), loadRoutingKeywords(), loadFilterOptions(f.doctorId)]);
        setRows([]);
      } else if (tableKey === "invite_codes") {
        await loadInviteCodes();
        setRows([]);
      } else {
        await Promise.all([loadTableList(f), loadTableData(tableKey, f), loadFilterOptions(f.doctorId)]);
      }
    } catch (error) {
      setStatus({ type: "error", text: t("admin.loadFailed", { message: error.message }) });
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadAll(activeTable);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTable]);

  return (
    <Box
      sx={{
        minHeight: "100vh",
        background:
          "radial-gradient(1200px 640px at 92% -8%, rgba(15,118,110,0.16), transparent 65%), radial-gradient(900px 520px at -12% 108%, rgba(47,79,111,0.15), transparent 62%), #f3f7f8",
      }}
    >
      <Container maxWidth="xl" sx={{ py: 2.5 }}>
        <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: { xs: "1fr", lg: "300px minmax(0,1fr)" }, alignItems: "start" }}>
          <Stack spacing={1.4} sx={{ position: { lg: "sticky" }, top: { lg: 16 } }}>
            <Card sx={{ borderRadius: 1.5 }}>
              <CardContent>
                <Stack direction="row" alignItems="center" justifyContent="space-between">
                  <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>{t("admin.pageTitle")}</Typography>
                  <Button size="small" color="inherit" onClick={onLockout} sx={{ fontSize: 12, color: "text.secondary" }}>退出</Button>
                </Stack>
                <Typography variant="caption" color="text.secondary" sx={{ mt: 0.2, display: "block" }}>
                  {t("admin.pageSubtitle")}
                </Typography>
              </CardContent>
            </Card>

            <Card sx={{ borderRadius: 1.5 }}>
              <CardContent sx={{ p: 1.8 }}>
                <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1 }}>
                  {t("admin.navTitle")}
                </Typography>
                <Stack spacing={1}>
                  {NAV_TABS.map((item) => (
                    <NavTab
                      key={item.key}
                      active={activeTable === item.key}
                      icon={item.icon}
                      onClick={() => setActiveTable(item.key)}
                    >
                      {t(`admin.tables.${item.key}`) || item.key}
                    </NavTab>
                  ))}
                </Stack>
              </CardContent>
            </Card>

            <Card sx={{ borderRadius: 1.5 }}>
              <CardContent sx={{ p: 1.5 }}>
                <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.8 }}>
                  {t("admin.counts.title")}
                </Typography>
                <Stack spacing={0.4}>
                  {TABLES.map((item, idx) => (
                    <Box key={`cnt-${item.key}`}>
                      <Stack direction="row" alignItems="center" justifyContent="space-between">
                        <Stack direction="row" spacing={0.8} alignItems="center">
                          <Box sx={{ color: "text.secondary", display: "grid", placeItems: "center" }}>{item.icon}</Box>
                          <Typography variant="body2" color="text.secondary">{t(`admin.tables.${item.key}`)}</Typography>
                        </Stack>
                        <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>{tableCounts[item.key] || 0}</Typography>
                      </Stack>
                      {idx < TABLES.length - 1 ? <Divider sx={{ mt: 0.55 }} /> : null}
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
                <Stack direction="row" spacing={0.8} alignItems="center">
                  <StorageOutlinedIcon fontSize="small" />
                  <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>{activeLabel}</Typography>
                </Stack>
                {activeTable === "runtime_config" ? (
                  <Stack direction="row" spacing={0.8}>
                    <Button variant="outlined" size="small" onClick={loadRuntimeConfig} disabled={loading}>
                      {loading ? t("common.loading") : "加载配置"}
                    </Button>
                    <Button variant="outlined" size="small" onClick={verifyRuntimeConfig} disabled={loading}>
                      {loading ? t("common.loading") : "验证配置"}
                    </Button>
                    <Button variant="contained" size="small" onClick={saveRuntimeConfig} disabled={loading}>
                      {loading ? t("common.loading") : "保存配置"}
                    </Button>
                    <Button variant="contained" color="secondary" size="small" onClick={applyRuntimeConfigNow} disabled={loading}>
                      {loading ? t("common.loading") : "应用配置"}
                    </Button>
                  </Stack>
                ) : activeTable === "routing_keywords" ? (
                  <Stack direction="row" spacing={0.8}>
                    <Button variant="outlined" size="small" onClick={loadRoutingKeywords} disabled={loading}>
                      {loading ? t("common.loading") : "加载"}
                    </Button>
                    <Button
                      variant="contained"
                      size="small"
                      disabled={loading}
                      onClick={async () => {
                        try {
                          await putAdminRoutingKeywords(null, routingKeywords);
                          setStatus({ type: "success", text: "路由关键词已保存。" });
                        } catch (error) {
                          setStatus({ type: "error", text: `保存失败：${error.message}` });
                        }
                      }}
                    >
                      {loading ? t("common.loading") : "保存"}
                    </Button>
                    <Button
                      variant="contained"
                      color="secondary"
                      size="small"
                      disabled={loading}
                      onClick={async () => {
                        try {
                          const payload = await reloadAdminRoutingKeywords();
                          setStatus({ type: "success", text: `${payload.loaded ?? ""} 个关键词已加载` });
                        } catch (error) {
                          setStatus({ type: "error", text: `热加载失败：${error.message}` });
                        }
                      }}
                    >
                      {loading ? t("common.loading") : "热加载"}
                    </Button>
                  </Stack>
                ) : (
                  <Stack direction="row" spacing={0.8}>
                    <Typography variant="caption" color="text.secondary" sx={{ alignSelf: "center", mr: 1 }}>
                      {rows.length} 行
                    </Typography>
                    <Button variant="outlined" size="small" startIcon={<DownloadOutlinedIcon fontSize="small" />} onClick={exportCsv} disabled={!rows.length}>
                      {t("admin.exportCsv")}
                    </Button>
                    <Button variant="outlined" size="small" startIcon={<DownloadOutlinedIcon fontSize="small" />} onClick={exportJson} disabled={!rows.length}>
                      {t("admin.exportJson")}
                    </Button>
                    <Button variant="contained" size="small" onClick={() => loadAll(activeTable)} disabled={loading}>
                      {loading ? t("common.loading") : t("admin.reload")}
                    </Button>
                  </Stack>
                )}
              </Stack>
              <Box sx={{ border: "1px solid #d8e3e8", borderRadius: 1.5, backgroundColor: "#f8fbfc", p: 1.2, mb: 1.2 }}>
                <Stack
                  direction={{ xs: "column", md: "row" }}
                  spacing={1}
                  sx={{ alignItems: { md: "center" } }}
                >
                  <Autocomplete
                    options={doctorOptions}
                    value={doctorId || null}
                    inputValue={doctorInput}
                    openOnFocus
                    sx={{ minWidth: { md: 220 }, flex: 1 }}
                    slotProps={{ listbox: { sx: { maxHeight: 260 } } }}
                    onInputChange={(_, value) => setDoctorInput(value)}
                    onChange={async (_, value) => {
                      const nextDoctor = (value || "").trim();
                      setDoctorId(nextDoctor);
                      setDoctorInput(nextDoctor);
                      setPatientName("");
                      setPatientInput("");
                      await loadAll(activeTable, { doctorId: nextDoctor, patientName: "" });
                    }}
                    filterOptions={prefixFilter}
                    clearOnEscape
                    renderInput={(params) => (
                      <TextField
                        {...params}
                        size="small"
                        label={t("admin.filters.doctorName")}
                        placeholder={t("common.all")}
                      />
                    )}
                  />
                  <Autocomplete
                    options={patientOptions}
                    value={patientName || null}
                    inputValue={patientInput}
                    openOnFocus
                    sx={{ minWidth: { md: 220 }, flex: 1 }}
                    slotProps={{ listbox: { sx: { maxHeight: 260 } } }}
                    onInputChange={(_, value) => setPatientInput(value)}
                    onChange={async (_, value) => {
                      const nextPatient = (value || "").trim();
                      setPatientName(nextPatient);
                      setPatientInput(nextPatient);
                      await loadAll(activeTable, { patientName: nextPatient });
                    }}
                    filterOptions={prefixFilter}
                    clearOnEscape
                    renderInput={(params) => (
                      <TextField
                        {...params}
                        size="small"
                        label={t("admin.filters.patientName")}
                        placeholder={t("common.all")}
                      />
                    )}
                  />
                  <TextField
                    size="small"
                    type="date"
                    label={t("admin.filters.dateFrom")}
                    InputLabelProps={{ shrink: true }}
                    value={dateFrom}
                    onChange={(e) => setDateFrom(e.target.value)}
                    sx={{ minWidth: { md: 160 } }}
                  />
                  <TextField
                    size="small"
                    type="date"
                    label={t("admin.filters.dateTo")}
                    InputLabelProps={{ shrink: true }}
                    value={dateTo}
                    onChange={(e) => setDateTo(e.target.value)}
                    sx={{ minWidth: { md: 160 } }}
                  />
                  <Button
                    variant="outlined"
                    size="small"
                    onClick={() => loadAll(activeTable)}
                    disabled={loading}
                    sx={{ whiteSpace: "nowrap", minWidth: 92 }}
                  >
                    {loading ? t("common.loading") : t("admin.reload")}
                  </Button>
                </Stack>
              </Box>

              {activeTable === "runtime_config" ? (
                <Box sx={{ border: "1px solid #d8e3e8", borderRadius: 1.5, backgroundColor: "#f8fbfc", p: 1.2, mb: 1.2 }}>
                  <Stack direction={{ xs: "column", md: "row" }} justifyContent="space-between" alignItems={{ xs: "flex-start", md: "center" }} spacing={1} sx={{ mb: 1 }}>
                    <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>{t("admin.config.title")}</Typography>
                    <Chip size="small" variant="outlined" label={`${t("admin.config.source")}：${runtimeConfigSource || "-"}`} />
                  </Stack>
                  <Box sx={{ border: "1px solid #d8e3e8", borderRadius: 1.2, backgroundColor: "#fff", p: 1, mb: 1 }}>
                    <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ md: "center" }} justifyContent="space-between">
                      <Box sx={{ minWidth: 0 }}>
                        <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 700, display: "block" }}>
                          Cloudflared Dev URL
                        </Typography>
                        <Typography
                          variant="body2"
                          sx={{
                            fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, Liberation Mono, monospace",
                            wordBreak: "break-all",
                          }}
                        >
                          {tunnelInfo.url || "-"}
                        </Typography>
                        <Typography variant="caption" color="text.secondary">
                          来源: {tunnelInfo.source || "-"} {tunnelInfo.updated_at ? `· 更新时间: ${tunnelInfo.updated_at}` : ""}
                        </Typography>
                        {!tunnelInfo.ok && tunnelInfo.detail ? (
                          <Typography variant="caption" color="warning.main" sx={{ display: "block" }}>
                            {tunnelInfo.detail}
                          </Typography>
                        ) : null}
                      </Box>
                      <Stack direction="row" spacing={0.8}>
                        <Button variant="outlined" size="small" onClick={loadTunnelUrl} disabled={loading}>刷新地址</Button>
                        <Button
                          variant="outlined"
                          size="small"
                          disabled={!tunnelInfo.url}
                          onClick={async () => {
                            try {
                              await navigator.clipboard.writeText(tunnelInfo.url);
                              setStatus({ type: "success", text: "Cloudflared 地址已复制。" });
                            } catch (error) {
                              setStatus({ type: "error", text: t("admin.copyFailed", { message: error.message }) });
                            }
                          }}
                        >
                          复制地址
                        </Button>
                        <Button
                          variant="contained"
                          size="small"
                          disabled={!tunnelInfo.url}
                          onClick={() => window.open(tunnelInfo.url, "_blank", "noopener,noreferrer")}
                        >
                          打开地址
                        </Button>
                      </Stack>
                    </Stack>
                  </Box>
                  <Stack spacing={1}>
                    {(runtimeCategories || []).map((cat) => (
                      <Box key={`cfg-cat-${cat.key}`} sx={{ border: "1px solid #d8e3e8", borderRadius: 1.2, backgroundColor: "#fff", overflow: "hidden" }}>
                        <Box sx={{ px: 1.2, py: 0.9, borderBottom: "1px solid #e7eef1", backgroundColor: "#eff5f7" }}>
                          <Stack direction="row" justifyContent="space-between" alignItems="center">
                            <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>{cat.key}</Typography>
                            <Chip size="small" label={`${(cat.items || []).length} 项`} sx={{ height: 22 }} />
                          </Stack>
                          <Typography variant="caption" color="text.secondary">{cat.description_zh || cat.description || "-"}</Typography>
                        </Box>
                        <Box sx={{ px: 1, py: 0.7, display: { xs: "none", md: "grid" }, gridTemplateColumns: "210px minmax(240px,0.85fr) minmax(340px,1.15fr)", gap: 1, backgroundColor: "#f8fbfc", borderBottom: "1px solid #e7eef1" }}>
                          <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 700 }}>配置项</Typography>
                          <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 700 }}>说明</Typography>
                          <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 700 }}>{t("admin.config.value")}</Typography>
                        </Box>
                        <Box>
                          {(cat.items || []).map((item, idx) => (
                            <Box
                              key={`cfg-item-${item.key}`}
                              sx={{
                                display: "grid",
                                gridTemplateColumns: { xs: "1fr", md: "210px minmax(240px,0.85fr) minmax(340px,1.15fr)" },
                                gap: 1,
                                px: 1,
                                py: 0.9,
                                borderBottom: idx < (cat.items || []).length - 1 ? "1px solid #eef3f5" : "none",
                                alignItems: "center",
                                backgroundColor: idx % 2 ? "#fcfeff" : "#ffffff",
                              }}
                            >
                              <Box>
                                <Typography
                                  sx={{
                                    fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, Liberation Mono, monospace",
                                    fontSize: 12,
                                    fontWeight: 600,
                                    overflowWrap: "anywhere",
                                    wordBreak: "break-word",
                                    lineHeight: 1.3,
                                  }}
                                >
                                  {item.key}
                                </Typography>
                              </Box>
                              <Typography variant="caption" color="text.secondary" sx={{ lineHeight: 1.45 }}>
                                {item.description_zh || item.description || "-"}
                              </Typography>
                              {item.input_type === "boolean" ? (
                                <Box sx={{ display: "flex", alignItems: "center", justifyContent: { xs: "flex-start", md: "center" }, minHeight: 40 }}>
                                  <Switch
                                    size="small"
                                    checked={isTruthyValue(runtimeConfigMap[item.key] ?? item.value ?? "")}
                                    onChange={(e) => updateRuntimeValue(item.key, e.target.checked ? "true" : "false")}
                                  />
                                  <Typography variant="caption" color="text.secondary">
                                    {isTruthyValue(runtimeConfigMap[item.key] ?? item.value ?? "") ? "开启" : "关闭"}
                                  </Typography>
                                </Box>
                              ) : (item.options || []).length ? (
                                <TextField
                                  size="small"
                                  select
                                  value={runtimeConfigMap[item.key] ?? item.value ?? ""}
                                  onChange={(e) => updateRuntimeValue(item.key, e.target.value)}
                                  label={t("admin.config.value")}
                                  fullWidth
                                >
                                  {(item.options || []).map((opt) => (
                                    <MenuItem key={`cfg-opt-${item.key}-${opt}`} value={opt}>{opt}</MenuItem>
                                  ))}
                                </TextField>
                              ) : (
                                <TextField
                                  size="small"
                                  type={item.input_type === "number" ? "number" : "text"}
                                  value={runtimeConfigMap[item.key] ?? item.value ?? ""}
                                  onChange={(e) => updateRuntimeValue(item.key, e.target.value)}
                                  label={t("admin.config.value")}
                                  fullWidth
                                />
                              )}
                            </Box>
                          ))}
                        </Box>
                      </Box>
                    ))}
                  </Stack>
                  <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.8 }}>
                    {t("admin.config.hint")}
                  </Typography>
                </Box>
              ) : activeTable === "routing_keywords" ? (
                <Box sx={{ border: "1px solid #d8e3e8", borderRadius: 1.5, backgroundColor: "#f8fbfc", p: 1.2, mb: 1.2 }}>
                  <Stack spacing={1.2}>
                    {Object.entries(routingKeywords).filter(([sectionKey]) => sectionKey !== "tier3").map(([sectionKey, section]) => (
                      <Box key={`kw-section-${sectionKey}`} sx={{ border: "1px solid #d8e3e8", borderRadius: 1.2, backgroundColor: "#fff", overflow: "hidden" }}>
                        <Box sx={{ px: 1.2, py: 0.9, borderBottom: "1px solid #e7eef1", backgroundColor: "#eff5f7" }}>
                          <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>{sectionKey}</Typography>
                          <Typography variant="caption" color="text.secondary">{section.description_zh || section.description || ""}</Typography>
                        </Box>
                        <Box sx={{ px: 1.2, py: 1 }}>
                          <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.5, mb: 1 }}>
                            {(section.keywords || []).map((kw, kwIdx) => (
                              <Chip
                                key={`kw-chip-${sectionKey}-${kwIdx}`}
                                label={kw}
                                size="small"
                                onDelete={() => {
                                  setRoutingKeywords((prev) => ({
                                    ...prev,
                                    [sectionKey]: {
                                      ...prev[sectionKey],
                                      keywords: (prev[sectionKey].keywords || []).filter((_, i) => i !== kwIdx),
                                    },
                                  }));
                                }}
                              />
                            ))}
                          </Box>
                          <Stack direction="row" spacing={1} alignItems="center">
                            <TextField
                              size="small"
                              placeholder="新关键词"
                              value={newKwInputs[sectionKey] || ""}
                              onChange={(e) => setNewKwInputs((prev) => ({ ...prev, [sectionKey]: e.target.value }))}
                              onKeyDown={(e) => {
                                if (e.key === "Enter") {
                                  const val = (newKwInputs[sectionKey] || "").trim();
                                  if (!val) return;
                                  setRoutingKeywords((prev) => ({
                                    ...prev,
                                    [sectionKey]: { ...prev[sectionKey], keywords: [...(prev[sectionKey].keywords || []), val] },
                                  }));
                                  setNewKwInputs((prev) => ({ ...prev, [sectionKey]: "" }));
                                }
                              }}
                              sx={{ flex: 1, maxWidth: 280 }}
                            />
                            <Button
                              size="small"
                              variant="outlined"
                              onClick={() => {
                                const val = (newKwInputs[sectionKey] || "").trim();
                                if (!val) return;
                                setRoutingKeywords((prev) => ({
                                  ...prev,
                                  [sectionKey]: { ...prev[sectionKey], keywords: [...(prev[sectionKey].keywords || []), val] },
                                }));
                                setNewKwInputs((prev) => ({ ...prev, [sectionKey]: "" }));
                              }}
                            >
                              添加
                            </Button>
                          </Stack>
                        </Box>
                      </Box>
                    ))}
                    {routingKeywords.tier3 && (
                      <Box sx={{ border: "1px solid #d8e3e8", borderRadius: 1.2, backgroundColor: "#fff", overflow: "hidden" }}>
                        <Box sx={{ px: 1.2, py: 0.9, borderBottom: "1px solid #e7eef1", backgroundColor: "#eff5f7" }}>
                          <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>tier3</Typography>
                          <Typography variant="caption" color="text.secondary">Tier-3 临床关键词</Typography>
                        </Box>
                        <Box sx={{ px: 1.2, py: 1 }}>
                          <Stack spacing={1}>
                            {Object.entries(routingKeywords.tier3).map(([catKey, catSection]) => (
                              <Box key={`kw-tier3-${catKey}`} sx={{ border: "1px solid #e7eef1", borderRadius: 1, overflow: "hidden" }}>
                                <Box sx={{ px: 1, py: 0.6, borderBottom: "1px solid #e7eef1", backgroundColor: "#f8fbfc" }}>
                                  <Typography variant="caption" sx={{ fontWeight: 700 }}>{catKey}</Typography>
                                  <Typography variant="caption" color="text.secondary" sx={{ ml: 1 }}>{catSection.description_zh || catSection.description || ""}</Typography>
                                </Box>
                                <Box sx={{ px: 1, py: 0.8 }}>
                                  <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.5, mb: 1 }}>
                                    {(catSection.keywords || []).map((kw, kwIdx) => (
                                      <Chip
                                        key={`kw-tier3-chip-${catKey}-${kwIdx}`}
                                        label={kw}
                                        size="small"
                                        onDelete={() => {
                                          setRoutingKeywords((prev) => ({
                                            ...prev,
                                            tier3: {
                                              ...prev.tier3,
                                              [catKey]: {
                                                ...prev.tier3[catKey],
                                                keywords: (prev.tier3[catKey].keywords || []).filter((_, i) => i !== kwIdx),
                                              },
                                            },
                                          }));
                                        }}
                                      />
                                    ))}
                                  </Box>
                                  <Stack direction="row" spacing={1} alignItems="center">
                                    <TextField
                                      size="small"
                                      placeholder="新关键词"
                                      value={(newKwInputs[`tier3__${catKey}`]) || ""}
                                      onChange={(e) => setNewKwInputs((prev) => ({ ...prev, [`tier3__${catKey}`]: e.target.value }))}
                                      onKeyDown={(e) => {
                                        if (e.key === "Enter") {
                                          const val = (newKwInputs[`tier3__${catKey}`] || "").trim();
                                          if (!val) return;
                                          setRoutingKeywords((prev) => ({
                                            ...prev,
                                            tier3: {
                                              ...prev.tier3,
                                              [catKey]: { ...prev.tier3[catKey], keywords: [...(prev.tier3[catKey].keywords || []), val] },
                                            },
                                          }));
                                          setNewKwInputs((prev) => ({ ...prev, [`tier3__${catKey}`]: "" }));
                                        }
                                      }}
                                      sx={{ flex: 1, maxWidth: 280 }}
                                    />
                                    <Button
                                      size="small"
                                      variant="outlined"
                                      onClick={() => {
                                        const val = (newKwInputs[`tier3__${catKey}`] || "").trim();
                                        if (!val) return;
                                        setRoutingKeywords((prev) => ({
                                          ...prev,
                                          tier3: {
                                            ...prev.tier3,
                                            [catKey]: { ...prev.tier3[catKey], keywords: [...(prev.tier3[catKey].keywords || []), val] },
                                          },
                                        }));
                                        setNewKwInputs((prev) => ({ ...prev, [`tier3__${catKey}`]: "" }));
                                      }}
                                    >
                                      添加
                                    </Button>
                                  </Stack>
                                </Box>
                              </Box>
                            ))}
                          </Stack>
                        </Box>
                      </Box>
                    )}
                    {!Object.keys(routingKeywords).length ? (
                      <Typography color="text.secondary" variant="body2">暂无关键词配置，请点击"加载"。</Typography>
                    ) : null}
                  </Stack>
                </Box>
              ) : activeTable === "invite_codes" ? (
                <Box>
                  <Stack direction={{ xs: "column", sm: "row" }} spacing={1} sx={{ mb: 2 }}>
                    <TextField
                      size="small"
                      label="医生账号 ID"
                      value={newInviteDoctorId}
                      onChange={(e) => setNewInviteDoctorId(e.target.value)}
                      sx={{ minWidth: 180 }}
                    />
                    <TextField
                      size="small"
                      label="显示姓名（可选）"
                      value={newInviteName}
                      onChange={(e) => setNewInviteName(e.target.value)}
                      sx={{ minWidth: 160 }}
                    />
                    <Button variant="contained" size="small" onClick={onCreateInviteCode} disabled={!newInviteDoctorId.trim()}>
                      生成邀请码
                    </Button>
                  </Stack>
                  <TableContainer sx={{ border: "1px solid #d8e3e8", borderRadius: 1.5, backgroundColor: "#f8fbfc" }}>
                    <Table size="small">
                      <TableHead>
                        <TableRow>
                          {["邀请码", "医生账号", "姓名", "状态", "创建时间", "操作"].map((h) => (
                            <TableCell key={h} sx={{ fontWeight: 700, fontSize: 12, backgroundColor: "#eef4f6", color: "text.secondary" }}>{h}</TableCell>
                          ))}
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {inviteCodes.length === 0 ? (
                          <TableRow><TableCell colSpan={6}><Typography variant="body2" color="text.secondary">暂无邀请码</Typography></TableCell></TableRow>
                        ) : inviteCodes.map((row) => (
                          <TableRow key={row.code}>
                            <TableCell sx={{ fontFamily: "monospace", fontWeight: 700 }}>{row.code}</TableCell>
                            <TableCell>{row.doctor_id}</TableCell>
                            <TableCell>{row.doctor_name || "-"}</TableCell>
                            <TableCell>
                              <Chip size="small" label={row.active ? "有效" : "已吊销"} color={row.active ? "success" : "default"} />
                            </TableCell>
                            <TableCell>{row.created_at}</TableCell>
                            <TableCell>
                              {row.active && (
                                <Button size="small" color="error" onClick={() => onRevokeInviteCode(row.code)}>吊销</Button>
                              )}
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </TableContainer>
                </Box>
              ) : (
                <>
                  <TableContainer
                    sx={{
                      border: "1px solid #d8e3e8",
                      borderRadius: 1.5,
                      backgroundColor: "#f8fbfc",
                      maxHeight: "74vh",
                    }}
                  >
                    <Table size="small" stickyHeader sx={{ tableLayout: "fixed", minWidth: 980 }}>
                      <TableHead>
                        <TableRow>
                          {columns.map((key) => (
                            <TableCell
                              key={`head-${key}`}
                              onClick={() => handleSort(key)}
                              sx={{
                                fontWeight: 700,
                                color: "text.secondary",
                                whiteSpace: "nowrap",
                                width: COL_WIDTH[key] || 140,
                                maxWidth: COL_WIDTH[key] || 140,
                                backgroundColor: "#eef4f6",
                                px: 1,
                                py: 0.75,
                                fontSize: 12,
                                cursor: "pointer",
                                userSelect: "none",
                                "&:hover": { backgroundColor: "#e2edf0" },
                              }}
                            >
                              <Stack direction="row" alignItems="center" spacing={0.3}>
                                <span>{t(`admin.cols.${key}`)}</span>
                                {sortCol === key ? (
                                  sortDir === "asc"
                                    ? <ArrowUpwardIcon sx={{ fontSize: 13, color: "primary.main" }} />
                                    : <ArrowDownwardIcon sx={{ fontSize: 13, color: "primary.main" }} />
                                ) : (
                                  <UnfoldMoreIcon sx={{ fontSize: 13, color: "#ccc" }} />
                                )}
                              </Stack>
                            </TableCell>
                          ))}
                          <TableCell sx={{ width: 56, maxWidth: 56, backgroundColor: "#eef4f6", px: 0.5, py: 0.75 }} />
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {sortedRows.map((row, rowIdx) => (
                          <TableRow
                            key={`row-${row.id ?? row.key ?? rowIdx}`}
                            hover
                            onClick={() => {
                              setSelectedRow(row);
                              setRowEditMode(false);
                            }}
                            sx={{ cursor: "pointer" }}
                          >
                            {columns.map((key) => (
                              <TableCell
                                key={`cell-${rowIdx}-${key}`}
                                sx={{
                                  verticalAlign: "top",
                                  borderBottom: "1px solid #e4edf0",
                                  width: COL_WIDTH[key] || 140,
                                  maxWidth: COL_WIDTH[key] || 140,
                                  py: 0.45,
                                  px: 1,
                                  fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, Liberation Mono, monospace",
                                  fontSize: 12,
                                  lineHeight: 1.35,
                                  overflow: "hidden",
                                  textOverflow: "ellipsis",
                                  whiteSpace: "nowrap",
                                }}
                              >
                                {renderCellContent(row[key])}
                              </TableCell>
                            ))}
                            <TableCell
                              sx={{ py: 0.2, px: 0.2, borderBottom: "1px solid #e4edf0", verticalAlign: "top" }}
                              onClick={(e) => e.stopPropagation()}
                            >
                              <IconButton size="small" onClick={() => copyRow(row)} title={t("admin.copyRow")}>
                                <ContentCopyOutlinedIcon sx={{ fontSize: 15 }} />
                              </IconButton>
                            </TableCell>
                          </TableRow>
                        ))}
                        {!sortedRows.length ? (
                          <TableRow>
                            <TableCell colSpan={colCount} sx={{ py: 1.2 }}>
                              <Typography color="text.secondary">{t("admin.empty")}</Typography>
                            </TableCell>
                          </TableRow>
                        ) : null}
                      </TableBody>
                    </Table>
                  </TableContainer>

                  {/* Row detail / edit dialog */}
                  <Dialog
                    open={!!selectedRow}
                    onClose={() => { setSelectedRow(null); setRowEditMode(false); }}
                    maxWidth="md"
                    fullWidth
                    PaperProps={{ sx: { borderRadius: 2 } }}
                  >
                    <DialogTitle sx={{ fontWeight: 700, pb: 1 }}>
                      <Stack direction="row" alignItems="center" justifyContent="space-between">
                        <span>
                          {t(`admin.tables.${activeTable}`)}
                          <Typography component="span" variant="body2" color="text.secondary" sx={{ ml: 1 }}>
                            #{selectedRow?.id}
                          </Typography>
                        </span>
                        {activeTable === "medical_records" && !rowEditMode && (
                          <Button
                            size="small"
                            startIcon={<EditOutlinedIcon fontSize="small" />}
                            onClick={() => {
                              const init = {};
                              RECORD_EDIT_FIELDS.forEach(({ key }) => { init[key] = selectedRow?.[key] || ""; });
                              setRowEditForm(init);
                              setRowEditMode(true);
                            }}
                          >
                            编辑
                          </Button>
                        )}
                      </Stack>
                    </DialogTitle>
                    <DialogContent dividers>
                      {rowEditMode ? (
                        <Stack spacing={2}>
                          {RECORD_EDIT_FIELDS.map(({ key, label }) => (
                            <TextField
                              key={key}
                              label={label}
                              multiline
                              minRows={2}
                              maxRows={8}
                              size="small"
                              fullWidth
                              value={rowEditForm[key] || ""}
                              onChange={(e) => setRowEditForm((f) => ({ ...f, [key]: e.target.value }))}
                            />
                          ))}
                        </Stack>
                      ) : (
                        <Stack spacing={0}>
                          {selectedRow && Object.entries(selectedRow).map(([key, value]) => (
                            <Box key={key} sx={{ display: "flex", borderBottom: "1px solid #f0f4f6", py: 0.8 }}>
                              <Typography
                                variant="caption"
                                sx={{ fontWeight: 700, color: "text.secondary", width: 180, flexShrink: 0, pt: 0.1 }}
                              >
                                {t(`admin.cols.${key}`)}
                              </Typography>
                              <Typography
                                variant="body2"
                                sx={{ fontFamily: "ui-monospace, monospace", fontSize: 12, whiteSpace: "pre-wrap", wordBreak: "break-all", flex: 1 }}
                              >
                                {toCell(value)}
                              </Typography>
                            </Box>
                          ))}
                        </Stack>
                      )}
                    </DialogContent>
                    <DialogActions>
                      {rowEditMode ? (
                        <>
                          <Button onClick={() => setRowEditMode(false)} disabled={rowSaving}>取消</Button>
                          <Button variant="contained" onClick={saveRowEdit} disabled={rowSaving}>
                            {rowSaving ? "保存中…" : "保存"}
                          </Button>
                        </>
                      ) : (
                        <Button onClick={() => { setSelectedRow(null); }}>关闭</Button>
                      )}
                    </DialogActions>
                  </Dialog>
                </>
              )}
            </CardContent>
          </Card>
        </Box>
      </Container>
    </Box>
  );
}
