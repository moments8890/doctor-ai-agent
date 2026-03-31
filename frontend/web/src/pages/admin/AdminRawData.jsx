/** AdminRawData — raw table browser (extracted from AdminPage.jsx) */
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  Alert,
  Autocomplete,
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  IconButton,
  MenuItem,
  Snackbar,
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
import InboxOutlinedIcon from "@mui/icons-material/InboxOutlined";
import VisibilityOutlinedIcon from "@mui/icons-material/VisibilityOutlined";
import QrCode2OutlinedIcon from "@mui/icons-material/QrCode2Outlined";
import QRDialog from "../../components/QRDialog";
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
  getAdminRoutingMetrics,
  getAdminInviteCodes,
  createAdminInviteCode,
  revokeAdminInviteCode,
  updateAdminRecord,
  getAdminPrompts,
  updateAdminPrompt,
  generateQRToken,
} from "../../api";
import { t } from "../../i18n";
import { TYPE, ICON } from "../../theme";

// ── Table groups (dense tabs, grouped by category) ─────────────────────────────
export const TABLE_GROUPS = {
  "核心": [
    "doctors", "patients", "patient_messages", "medical_records",
    "ai_suggestions", "doctor_tasks", "message_drafts",
  ],
  "设置": [
    "doctor_knowledge_items", "doctor_contexts",
    "interview_sessions", "doctor_chat_log",
  ],
  "系统": [
    "audit_log", "invite_codes", "system_prompts",
    "system_prompt_versions", "runtime_config",
    "routing_keywords",
  ],
};

// All browsable table keys (flat list, for nav matching)
const ALL_TABLE_KEYS = Object.values(TABLE_GROUPS).flat();

// Legacy tab definitions reused for icons
const CORE_TABS = [
  { key: "invite_codes", icon: <BadgeOutlinedIcon fontSize="small" /> },
  { key: "doctors", icon: <BadgeOutlinedIcon fontSize="small" /> },
  { key: "patients", icon: <PeopleOutlineOutlinedIcon fontSize="small" /> },
  { key: "medical_records", icon: <DescriptionOutlinedIcon fontSize="small" /> },
  { key: "pending_records", icon: <InboxOutlinedIcon fontSize="small" /> },
  { key: "pending_messages", icon: <InboxOutlinedIcon fontSize="small" /> },
];
const FUTURE_TABS = [
  { key: "doctor_tasks", icon: <AssignmentOutlinedIcon fontSize="small" /> },
  { key: "audit_log", icon: <VisibilityOutlinedIcon fontSize="small" /> },
  { key: "chat_archive", icon: <TextSnippetOutlinedIcon fontSize="small" /> },
  { key: "doctor_contexts", icon: <AccountTreeOutlinedIcon fontSize="small" /> },
  { key: "doctor_knowledge_items", icon: <TextSnippetOutlinedIcon fontSize="small" /> },
  { key: "patient_labels", icon: <LabelOutlinedIcon fontSize="small" /> },
  { key: "patient_label_assignments", icon: <LinkOutlinedIcon fontSize="small" /> },
  { key: "medical_record_versions", icon: <DescriptionOutlinedIcon fontSize="small" /> },
  { key: "medical_record_exports", icon: <DescriptionOutlinedIcon fontSize="small" /> },
];
const SYSTEM_TABS = [
  { key: "system_prompts", icon: <TextSnippetOutlinedIcon fontSize="small" /> },
  { key: "system_prompt_versions", icon: <TextSnippetOutlinedIcon fontSize="small" /> },
  { key: "runtime_config", icon: <TuneOutlinedIcon fontSize="small" /> },
  { key: "routing_keywords", icon: <TuneOutlinedIcon fontSize="small" /> },
];
const NAV_TABS = [...CORE_TABS, ...FUTURE_TABS, ...SYSTEM_TABS];

const RECORD_EDIT_FIELDS = [
  { key: "record_type", label: "记录类型" },
  { key: "content", label: "临床笔记" },
  { key: "tags", label: "关键词标签" },
];

const ENUM_ZH = {
  follow_up: "随访", review: "复查", call: "电话联系", message: "发送消息",
  prescription: "处方续开", referral: "转诊", education: "患者教育",
  pending: "待处理", done: "已完成", cancelled: "已取消", snoozed: "已推迟",
  active: "有效", expired: "已过期", confirmed: "已确认", abandoned: "已撤销",
  system: "系统", doctor: "医生", patient: "患者", ai: "AI",
  inpatient: "住院", outpatient: "门诊", unknown: "未知",
  first_visit: "初诊", follow_up_visit: "复诊",
  visit: "门诊记录", dictation: "语音录入", import: "导入", interview_summary: "问诊总结",
  overdue: "已逾期", due_soon: "即将到期", ok: "正常", not_needed: "无需随访",
  scheduled: "已安排",
  critical: "危重", high: "高风险", medium: "中风险", low: "低风险",
  male: "男", female: "女",
  app: "邀请码登录", wechat_mini: "微信小程序",
  stroke: "脑卒中", parkinson: "帕金森", dementia: "痴呆", epilepsy: "癫痫",
  headache: "头痛", heart_failure: "心力衰竭", arrhythmia: "心律失常",
  hypertension: "高血压", coronary: "冠心病", diabetes: "糖尿病",
  chat: "对话",
};

function toCell(value) {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function renderCellContent(value) {
  if (value === null || value === undefined || value === "") {
    return <span style={{ color: "#b0bec5" }}>—</span>;
  }
  if (typeof value === "boolean") return value ? "是" : "否";
  const str = typeof value === "object" ? JSON.stringify(value, null, 0) : String(value);
  if (ENUM_ZH[str]) return ENUM_ZH[str];
  if (/^\d{4}-\d{2}-\d{2}T/.test(str)) {
    return <span style={{ whiteSpace: "nowrap" }}>{str.slice(0, 16).replace("T", " ")}</span>;
  }
  const MAX = 60;
  if (str.length > MAX) {
    return (
      <Tooltip title={<span style={{ whiteSpace: "pre-wrap", maxWidth: 400, display: "block", fontSize: 11 }}>{str.slice(0, 500)}{str.length > 500 ? "…" : ""}</span>} placement="top" arrow>
        <span style={{ cursor: "pointer" }}>
          {str.slice(0, MAX)}<span style={{ color: "#94a3b8" }}>…</span>
        </span>
      </Tooltip>
    );
  }
  return str;
}

const COL_WIDTH = {
  id: 64, key: 140, patient_id: 84, doctor_id: 144, patient_name: 112,
  name: 112, gender: 72, year_of_birth: 88, record_type: 120, tags: 220,
  diagnosis: 180, primary_diagnosis: 180, title: 220, summary: 260,
  content: 320, created_at: 164, updated_at: 164, due_at: 164,
};

// ── Dense grouped tab bar ──────────────────────────────────────────────────────
function GroupedTabBar({ activeTable, tableCounts, onSelect }) {
  return (
    <div style={{
      display: "flex",
      flexWrap: "wrap",
      gap: 4,
      padding: "8px 10px",
      borderBottom: "1px solid #f0f0f0",
      background: "#fff",
    }}>
      {Object.entries(TABLE_GROUPS).map(([groupName, keys]) => (
        <>
          <span key={`grp-${groupName}`} style={{
            fontSize: 9,
            color: "#999",
            textTransform: "uppercase",
            letterSpacing: "0.4px",
            padding: "0 4px",
            alignSelf: "center",
          }}>
            {groupName}
          </span>
          {keys.map((key) => {
            const isActive = activeTable === key;
            const count = tableCounts[key];
            return (
              <div
                key={key}
                onClick={() => onSelect(key)}
                style={{
                  padding: "3px 8px",
                  borderRadius: 3,
                  fontSize: 11,
                  cursor: "pointer",
                  border: `1px solid ${isActive ? "#1565c0" : "#e0e0e0"}`,
                  background: isActive ? "#1565c0" : "transparent",
                  color: isActive ? "#fff" : "#555",
                  userSelect: "none",
                }}
              >
                {key}
                {count != null && (
                  <span style={{
                    fontSize: 9,
                    marginLeft: 2,
                    color: isActive ? "rgba(255,255,255,0.6)" : "#aaa",
                  }}>
                    {count}
                  </span>
                )}
              </div>
            );
          })}
        </>
      ))}
    </div>
  );
}

// ── Main component ─────────────────────────────────────────────────────────────
export default function AdminRawData() {
  const [doctorId, setDoctorId] = useState("");
  const [patientName, setPatientName] = useState("");
  const [doctorInput, setDoctorInput] = useState("");
  const [patientInput, setPatientInput] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const { section } = useParams();
  const navigate = useNavigate();

  // Default to first table in "核心" group
  const defaultTable = TABLE_GROUPS["核心"][0];
  const activeTable = ALL_TABLE_KEYS.includes(section) ? section : defaultTable;
  function setActiveTable(key) { navigate(`/admin/${key}`); }

  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState({ type: "info", text: "" });
  const [tableCounts, setTableCounts] = useState({});
  const [rows, setRows] = useState([]);
  const [rowsHasMore, setRowsHasMore] = useState(false);
  const [rowsLoadingMore, setRowsLoadingMore] = useState(false);
  const [runtimeConfigMap, setRuntimeConfigMap] = useState({});
  const [runtimeCategories, setRuntimeCategories] = useState([]);
  const [runtimeConfigSource, setRuntimeConfigSource] = useState("");
  const [tunnelInfo, setTunnelInfo] = useState({ ok: false, url: "", source: "", updated_at: "", detail: "" });
  const [doctorOptions, setDoctorOptions] = useState([]);
  const [patientOptions, setPatientOptions] = useState([]);
  const [routingKeywords, setRoutingKeywords] = useState({});
  const [newKwInputs, setNewKwInputs] = useState({});
  const [inviteCodes, setInviteCodes] = useState([]);
  const [newInviteName, setNewInviteName] = useState("");
  const [newInviteCode, setNewInviteCode] = useState("");
  const [sortCol, setSortCol] = useState("");
  const [sortDir, setSortDir] = useState("asc");
  const [selectedRow, setSelectedRow] = useState(null);
  const [rowEditMode, setRowEditMode] = useState(false);
  const [rowEditForm, setRowEditForm] = useState({});
  const [rowSaving, setRowSaving] = useState(false);
  const [prompts, setPrompts] = useState([]);
  const [promptEdits, setPromptEdits] = useState({});
  const [promptSaving, setPromptSaving] = useState({});
  const [revokeTarget, setRevokeTarget] = useState(null);
  const [snack, setSnack] = useState({ open: false, message: "", severity: "success" });

  const [adminQrOpen, setAdminQrOpen] = useState(false);
  const [adminQrUrl, setAdminQrUrl] = useState("");
  const [adminQrError, setAdminQrError] = useState("");
  const [adminQrName, setAdminQrName] = useState("");
  const [adminQrDoctorId, setAdminQrDoctorId] = useState("");
  const [adminQrLoading, setAdminQrLoading] = useState(false);

  async function handleAdminQR(doctorId, doctorName) {
    setAdminQrDoctorId(doctorId);
    setAdminQrName(doctorName || doctorId);
    setAdminQrLoading(true);
    setAdminQrError("");
    setAdminQrOpen(true);
    try {
      const data = await generateQRToken("doctor", doctorId);
      setAdminQrUrl(data.url);
    } catch (e) {
      setAdminQrUrl("");
      setAdminQrError(e.message || "生成失败");
    } finally {
      setAdminQrLoading(false);
    }
  }

  function showSnack(message, severity = "success") {
    setSnack({ open: true, message, severity });
  }

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
  const isSystemTab = SYSTEM_TABS.some((st) => st.key === activeTable);

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
      showSnack("记录已保存");
    } catch (e) {
      setStatus({ type: "error", text: e.message || "保存失败" });
    } finally {
      setRowSaving(false);
    }
  }

  async function loadPrompts() {
    try {
      const data = await getAdminPrompts();
      const list = data.prompts || [];
      setPrompts(list);
      const edits = {};
      list.forEach((p) => { edits[p.key] = p.content; });
      setPromptEdits(edits);
    } catch (e) {
      setStatus({ type: "error", text: e.message });
    }
  }

  async function savePrompt(key) {
    setPromptSaving((s) => ({ ...s, [key]: true }));
    try {
      await updateAdminPrompt(key, promptEdits[key] ?? "");
      setPrompts((prev) => prev.map((p) => p.key === key ? { ...p, content: promptEdits[key], updated_at: new Date().toISOString().slice(0, 16).replace("T", " ") } : p));
      setStatus({ type: "success", text: `提示词 "${key}" 已保存` });
    } catch (e) {
      setStatus({ type: "error", text: e.message });
    } finally {
      setPromptSaving((s) => ({ ...s, [key]: false }));
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
    downloadFile(`${activeTable}.json`, JSON.stringify(rows, null, 2), "application/json;charset=utf-8");
  }

  function exportCsv() {
    const head = columns.map((col) => escapeCsv(t(`admin.cols.${col}`))).join(",");
    const body = rows.map((row) => columns.map((col) => escapeCsv(row[col])).join(",")).join("\n");
    const csv = [head, body].filter(Boolean).join("\n");
    downloadFile(`${activeTable}.csv`, csv, "text/csv;charset=utf-8");
  }

  async function copyRow(row) {
    try {
      await navigator.clipboard.writeText(JSON.stringify(row, null, 2));
      showSnack("已复制到剪贴板");
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
    const data = await getAdminTables({ doctorId: f.doctorId, patientName: f.patientName, dateFrom: f.dateFrom, dateTo: f.dateTo });
    const next = {};
    for (const item of data.items || []) { next[item.key] = item.count; }
    setTableCounts(next);
  }

  async function loadFilterOptions(doctorIdOverride = null) {
    const effectiveDoctorId = doctorIdOverride !== null ? doctorIdOverride : doctorId.trim();
    const data = await getAdminFilterOptions({ doctorId: effectiveDoctorId });
    setDoctorOptions(data.doctor_ids || []);
    setPatientOptions(data.patient_names || []);
  }

  async function loadTableData(tableKey = activeTable, overrides = {}) {
    if (tableKey === "observability") { setRows([]); setRowsHasMore(false); return; }
    const f = _resolveFilters(overrides);
    const PAGE = 50;
    const data = await getAdminTableRows({
      tableKey, doctorId: f.doctorId, patientName: f.patientName,
      dateFrom: f.dateFrom, dateTo: f.dateTo, limit: PAGE + 1,
    });
    const items = data.items || [];
    setRowsHasMore(items.length > PAGE);
    setRows(items.slice(0, PAGE));
  }

  async function loadMoreRows() {
    if (rowsLoadingMore || !rowsHasMore) return;
    setRowsLoadingMore(true);
    const PAGE = 50;
    const f = _resolveFilters({});
    try {
      const data = await getAdminTableRows({
        tableKey: activeTable, doctorId: f.doctorId, patientName: f.patientName,
        dateFrom: f.dateFrom, dateTo: f.dateTo, limit: PAGE + 1, offset: rows.length,
      });
      const items = data.items || [];
      setRowsHasMore(items.length > PAGE);
      setRows((prev) => [...prev, ...items.slice(0, PAGE)]);
    } finally {
      setRowsLoadingMore(false);
    }
  }

  async function loadRuntimeConfig() {
    const data = await getAdminRuntimeConfig();
    setRuntimeConfigSource(data.source || "");
    setRuntimeConfigMap(data.config || {});
    setRuntimeCategories(data.categories || []);
  }

  async function loadTunnelUrl() {
    const data = await getAdminTunnelUrl();
    setTunnelInfo({ ok: !!data.ok, url: data.url || "", source: data.source || "", updated_at: data.updated_at || "", detail: data.detail || "" });
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
      if (!payload.ok) { setStatus({ type: "error", text: `配置校验失败：${errors.join("；") || "未知错误"}` }); return; }
      if (warnings.length) { setStatus({ type: "warning", text: `配置校验通过（含警告）：${warnings.join("；")}` }); return; }
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
    try {
      await createAdminInviteCode(newInviteName.trim() || undefined, newInviteCode.trim() || undefined);
      setNewInviteName(""); setNewInviteCode("");
      await loadInviteCodes();
      showSnack("邀请码已生成");
    } catch (error) {
      setStatus({ type: "error", text: error.message });
    }
  }

  async function onRevokeInviteCode(code) {
    try {
      await revokeAdminInviteCode(code);
      await loadInviteCodes();
      showSnack("邀请码已吊销");
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
        setRows([]); setRowsHasMore(false);
      } else if (tableKey === "routing_keywords") {
        await Promise.all([loadTableList(f), loadRoutingKeywords(), loadFilterOptions(f.doctorId)]);
        setRows([]); setRowsHasMore(false);
      } else if (tableKey === "invite_codes") {
        await loadInviteCodes();
        setRows([]); setRowsHasMore(false);
      } else if (tableKey === "system_prompts") {
        await Promise.all([loadTableList(f), loadPrompts()]);
        setRows([]); setRowsHasMore(false);
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
    setSortCol(""); setSortDir("asc");
    setStatus({ type: "info", text: "" });
    loadAll(activeTable);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTable]);

  const dateFilterRef = useRef(null);
  useEffect(() => {
    if (!dateFrom && !dateTo) return;
    clearTimeout(dateFilterRef.current);
    dateFilterRef.current = setTimeout(() => { loadAll(activeTable, { dateFrom, dateTo }); }, 600);
    return () => clearTimeout(dateFilterRef.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dateFrom, dateTo]);

  return (
    <Box sx={{ p: "10px 16px" }}>
      {/* Dense panel with grouped tab bar + content */}
      <Box sx={{ background: "#fff", border: "1px solid #e0e0e0", borderRadius: 1, overflow: "hidden" }}>
        <GroupedTabBar activeTable={activeTable} tableCounts={tableCounts} onSelect={setActiveTable} />

        <Box sx={{ p: 1.5 }}>
          {!!status.text && <Alert severity={status.type} sx={{ mb: 1.5, fontSize: 12 }}>{status.text}</Alert>}

          {/* Toolbar row */}
          <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 1, position: "sticky", top: 0, zIndex: 2, background: "#fff", pb: 0.5 }}>
            <Stack direction="row" spacing={0.8} alignItems="center">
              <StorageOutlinedIcon sx={{ fontSize: 16, color: "text.secondary" }} />
              <Typography sx={{ fontWeight: 700, fontSize: 13 }}>{activeLabel}</Typography>
            </Stack>
            {activeTable === "runtime_config" ? (
              <Stack direction="row" spacing={0.8}>
                <Button variant="outlined" size="small" onClick={loadRuntimeConfig} disabled={loading}>加载配置</Button>
                <Button variant="outlined" size="small" onClick={verifyRuntimeConfig} disabled={loading}>验证配置</Button>
                <Button variant="contained" size="small" onClick={saveRuntimeConfig} disabled={loading}>保存配置</Button>
                <Button variant="contained" color="secondary" size="small" onClick={applyRuntimeConfigNow} disabled={loading}>应用配置</Button>
              </Stack>
            ) : activeTable === "routing_keywords" ? (
              <Stack direction="row" spacing={0.8}>
                <Button variant="outlined" size="small" onClick={loadRoutingKeywords} disabled={loading}>加载</Button>
                <Button variant="contained" size="small" disabled={loading}
                  onClick={async () => {
                    try { await putAdminRoutingKeywords(null, routingKeywords); showSnack("路由关键词已保存。"); }
                    catch (error) { setStatus({ type: "error", text: `保存失败：${error.message}` }); }
                  }}>保存</Button>
                <Button variant="contained" color="secondary" size="small" disabled={loading}
                  onClick={async () => {
                    try { const payload = await reloadAdminRoutingKeywords(); setStatus({ type: "success", text: `${payload.loaded ?? ""} 个关键词已加载` }); }
                    catch (error) { setStatus({ type: "error", text: `热加载失败：${error.message}` }); }
                  }}>热加载</Button>
              </Stack>
            ) : activeTable === "system_prompts" ? (
              <Stack direction="row" spacing={0.8}>
                <Button variant="outlined" size="small" onClick={loadPrompts} disabled={loading}>刷新</Button>
                <Typography variant="caption" color="text.secondary" sx={{ alignSelf: "center" }}>{prompts.length} 个提示词</Typography>
              </Stack>
            ) : (
              <Stack direction="row" spacing={0.8}>
                <Typography variant="caption" color="text.secondary" sx={{ alignSelf: "center", mr: 1 }}>{rows.length} 行</Typography>
                {rowsHasMore && (
                  <Chip label={rowsLoadingMore ? "加载中…" : "加载更多"} size="small" color="primary" variant="outlined"
                    onClick={loadMoreRows} disabled={rowsLoadingMore}
                    sx={{ fontSize: TYPE.micro.fontSize, cursor: "pointer" }} />
                )}
                <Button variant="outlined" size="small" startIcon={<DownloadOutlinedIcon fontSize="small" />} onClick={exportCsv} disabled={!rows.length}>CSV</Button>
                <Button variant="outlined" size="small" startIcon={<DownloadOutlinedIcon fontSize="small" />} onClick={exportJson} disabled={!rows.length}>JSON</Button>
                <Button variant="contained" size="small" onClick={() => loadAll(activeTable)} disabled={loading}>
                  {loading ? "加载中…" : t("admin.reload")}
                </Button>
              </Stack>
            )}
          </Box>

          {/* Filters — shown for non-system, non-invite tables */}
          {!isSystemTab && activeTable !== "invite_codes" && (
            <Box sx={{ border: "1px solid #f0f0f0", borderRadius: 1.5, backgroundColor: "#f8fbfc", p: 1.2, mb: 1.2 }}>
              <Stack direction={{ xs: "column", md: "row" }} spacing={1} sx={{ alignItems: { md: "center" } }}>
                <Autocomplete options={doctorOptions} value={doctorId || null} inputValue={doctorInput}
                  openOnFocus sx={{ minWidth: { md: 220 }, flex: 1 }}
                  slotProps={{ listbox: { sx: { maxHeight: 260 } } }}
                  onInputChange={(_, value) => setDoctorInput(value)}
                  onChange={async (_, value) => {
                    const nextDoctor = (value || "").trim();
                    setDoctorId(nextDoctor); setDoctorInput(nextDoctor);
                    setPatientName(""); setPatientInput("");
                    await loadAll(activeTable, { doctorId: nextDoctor, patientName: "" });
                  }}
                  filterOptions={prefixFilter} clearOnEscape
                  renderInput={(params) => <TextField {...params} size="small" label={t("admin.filters.doctorName")} placeholder={t("common.all")} />}
                />
                <Autocomplete options={patientOptions} value={patientName || null} inputValue={patientInput}
                  openOnFocus sx={{ minWidth: { md: 220 }, flex: 1 }}
                  slotProps={{ listbox: { sx: { maxHeight: 260 } } }}
                  onInputChange={(_, value) => setPatientInput(value)}
                  onChange={async (_, value) => {
                    const nextPatient = (value || "").trim();
                    setPatientName(nextPatient); setPatientInput(nextPatient);
                    await loadAll(activeTable, { patientName: nextPatient });
                  }}
                  filterOptions={prefixFilter} clearOnEscape
                  renderInput={(params) => <TextField {...params} size="small" label={t("admin.filters.patientName")} placeholder={t("common.all")} />}
                />
                <TextField size="small" type="date" label={t("admin.filters.dateFrom")}
                  InputLabelProps={{ shrink: true }} value={dateFrom}
                  onChange={(e) => setDateFrom(e.target.value)} sx={{ minWidth: { md: 160 } }} />
                <TextField size="small" type="date" label={t("admin.filters.dateTo")}
                  InputLabelProps={{ shrink: true }} value={dateTo}
                  onChange={(e) => setDateTo(e.target.value)} sx={{ minWidth: { md: 160 } }} />
                <Button variant="outlined" size="small" onClick={() => loadAll(activeTable)} disabled={loading} sx={{ whiteSpace: "nowrap", minWidth: 92 }}>
                  {loading ? "加载中…" : t("admin.reload")}
                </Button>
                <Button size="small" variant="text" sx={{ whiteSpace: "nowrap", color: "text.secondary" }}
                  disabled={!doctorId && !patientName && !dateFrom && !dateTo}
                  onClick={() => {
                    setDoctorId(""); setDoctorInput(""); setPatientName(""); setPatientInput("");
                    setDateFrom(""); setDateTo("");
                    loadAll(activeTable, { doctorId: "", patientName: "", dateFrom: "", dateTo: "" });
                  }}>清除筛选</Button>
              </Stack>
            </Box>
          )}

          {/* Content: runtime_config */}
          {activeTable === "runtime_config" ? (
            <Box sx={{ border: "1px solid #f0f0f0", borderRadius: 1.5, backgroundColor: "#f8fbfc", p: 1.2, mb: 1.2 }}>
              <Stack direction={{ xs: "column", md: "row" }} justifyContent="space-between" alignItems={{ xs: "flex-start", md: "center" }} spacing={1} sx={{ mb: 1 }}>
                <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>{t("admin.config.title")}</Typography>
                <Chip size="small" variant="outlined" label={`${t("admin.config.source")}：${runtimeConfigSource || "-"}`} />
              </Stack>
              <Box sx={{ border: "1px solid #f0f0f0", borderRadius: 1.2, backgroundColor: "#fff", p: 1, mb: 1 }}>
                <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ md: "center" }} justifyContent="space-between">
                  <Box sx={{ minWidth: 0 }}>
                    <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 700, display: "block" }}>Cloudflared Dev URL</Typography>
                    <Typography variant="body2" sx={{ fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, Liberation Mono, monospace", wordBreak: "break-all" }}>
                      {tunnelInfo.url || "-"}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      来源: {tunnelInfo.source || "-"} {tunnelInfo.updated_at ? `· 更新时间: ${tunnelInfo.updated_at}` : ""}
                    </Typography>
                    {!tunnelInfo.ok && tunnelInfo.detail ? (
                      <Typography variant="caption" color="warning.main" sx={{ display: "block" }}>{tunnelInfo.detail}</Typography>
                    ) : null}
                  </Box>
                  <Stack direction="row" spacing={0.8}>
                    <Button variant="outlined" size="small" onClick={loadTunnelUrl} disabled={loading}>刷新地址</Button>
                    <Button variant="outlined" size="small" disabled={!tunnelInfo.url}
                      onClick={async () => {
                        try { await navigator.clipboard.writeText(tunnelInfo.url); setStatus({ type: "success", text: "Cloudflared 地址已复制。" }); }
                        catch (error) { setStatus({ type: "error", text: t("admin.copyFailed", { message: error.message }) }); }
                      }}>复制地址</Button>
                    <Button variant="contained" size="small" disabled={!tunnelInfo.url}
                      onClick={() => window.open(tunnelInfo.url, "_blank", "noopener,noreferrer")}>打开地址</Button>
                  </Stack>
                </Stack>
              </Box>
              <Stack spacing={1}>
                {(runtimeCategories || []).map((cat) => (
                  <Box key={`cfg-cat-${cat.key}`} sx={{ border: "1px solid #f0f0f0", borderRadius: 1.2, backgroundColor: "#fff", overflow: "hidden" }}>
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
                        <Box key={`cfg-item-${item.key}`}
                          sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "210px minmax(240px,0.85fr) minmax(340px,1.15fr)" }, gap: 1, px: 1, py: 0.9, borderBottom: idx < (cat.items || []).length - 1 ? "1px solid #eef3f5" : "none", alignItems: "center", backgroundColor: idx % 2 ? "#fcfeff" : "#ffffff" }}>
                          <Box>
                            <Typography sx={{ fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, Liberation Mono, monospace", fontSize: TYPE.caption.fontSize, fontWeight: 600, overflowWrap: "anywhere", wordBreak: "break-word", lineHeight: 1.3 }}>
                              {item.key}
                            </Typography>
                          </Box>
                          <Typography variant="caption" color="text.secondary" sx={{ lineHeight: 1.45 }}>
                            {item.description_zh || item.description || "-"}
                          </Typography>
                          {item.input_type === "boolean" ? (
                            <Box sx={{ display: "flex", alignItems: "center", justifyContent: { xs: "flex-start", md: "center" }, minHeight: 40 }}>
                              <Switch size="small" checked={isTruthyValue(runtimeConfigMap[item.key] ?? item.value ?? "")}
                                onChange={(e) => updateRuntimeValue(item.key, e.target.checked ? "true" : "false")} />
                              <Typography variant="caption" color="text.secondary">
                                {isTruthyValue(runtimeConfigMap[item.key] ?? item.value ?? "") ? "开启" : "关闭"}
                              </Typography>
                            </Box>
                          ) : (item.options || []).length ? (
                            <TextField size="small" select value={runtimeConfigMap[item.key] ?? item.value ?? ""}
                              onChange={(e) => updateRuntimeValue(item.key, e.target.value)}
                              label={t("admin.config.value")} fullWidth>
                              {(item.options || []).map((opt) => (
                                <MenuItem key={`cfg-opt-${item.key}-${opt}`} value={opt}>{opt}</MenuItem>
                              ))}
                            </TextField>
                          ) : (
                            <TextField size="small" type={item.input_type === "number" ? "number" : "text"}
                              value={runtimeConfigMap[item.key] ?? item.value ?? ""}
                              onChange={(e) => updateRuntimeValue(item.key, e.target.value)}
                              label={t("admin.config.value")} fullWidth />
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
            <Box sx={{ border: "1px solid #f0f0f0", borderRadius: 1.5, backgroundColor: "#f8fbfc", p: 1.2, mb: 1.2 }}>
              <Stack spacing={1.2}>
                {Object.entries(routingKeywords).filter(([sectionKey]) => sectionKey !== "tier3").map(([sectionKey, section]) => (
                  <Box key={`kw-section-${sectionKey}`} sx={{ border: "1px solid #f0f0f0", borderRadius: 1.2, backgroundColor: "#fff", overflow: "hidden" }}>
                    <Box sx={{ px: 1.2, py: 0.9, borderBottom: "1px solid #e7eef1", backgroundColor: "#eff5f7" }}>
                      <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>{sectionKey}</Typography>
                      <Typography variant="caption" color="text.secondary">{section.description_zh || section.description || ""}</Typography>
                    </Box>
                    <Box sx={{ px: 1.2, py: 1 }}>
                      <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.5, mb: 1 }}>
                        {(section.keywords || []).map((kw, kwIdx) => (
                          <Chip key={`kw-chip-${sectionKey}-${kwIdx}`} label={kw} size="small"
                            onDelete={() => {
                              setRoutingKeywords((prev) => ({ ...prev, [sectionKey]: { ...prev[sectionKey], keywords: (prev[sectionKey].keywords || []).filter((_, i) => i !== kwIdx) } }));
                            }} />
                        ))}
                      </Box>
                      <Stack direction="row" spacing={1} alignItems="center">
                        <TextField size="small" placeholder="新关键词" value={newKwInputs[sectionKey] || ""}
                          onChange={(e) => setNewKwInputs((prev) => ({ ...prev, [sectionKey]: e.target.value }))}
                          onKeyDown={(e) => {
                            if (e.key === "Enter") {
                              const val = (newKwInputs[sectionKey] || "").trim();
                              if (!val) return;
                              setRoutingKeywords((prev) => ({ ...prev, [sectionKey]: { ...prev[sectionKey], keywords: [...(prev[sectionKey].keywords || []), val] } }));
                              setNewKwInputs((prev) => ({ ...prev, [sectionKey]: "" }));
                            }
                          }}
                          sx={{ flex: 1, maxWidth: 280 }} />
                        <Button size="small" variant="outlined"
                          onClick={() => {
                            const val = (newKwInputs[sectionKey] || "").trim();
                            if (!val) return;
                            setRoutingKeywords((prev) => ({ ...prev, [sectionKey]: { ...prev[sectionKey], keywords: [...(prev[sectionKey].keywords || []), val] } }));
                            setNewKwInputs((prev) => ({ ...prev, [sectionKey]: "" }));
                          }}>添加</Button>
                      </Stack>
                    </Box>
                  </Box>
                ))}
                {routingKeywords.tier3 && (
                  <Box sx={{ border: "1px solid #f0f0f0", borderRadius: 1.2, backgroundColor: "#fff", overflow: "hidden" }}>
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
                                  <Chip key={`kw-tier3-chip-${catKey}-${kwIdx}`} label={kw} size="small"
                                    onDelete={() => {
                                      setRoutingKeywords((prev) => ({ ...prev, tier3: { ...prev.tier3, [catKey]: { ...prev.tier3[catKey], keywords: (prev.tier3[catKey].keywords || []).filter((_, i) => i !== kwIdx) } } }));
                                    }} />
                                ))}
                              </Box>
                              <Stack direction="row" spacing={1} alignItems="center">
                                <TextField size="small" placeholder="新关键词" value={(newKwInputs[`tier3__${catKey}`]) || ""}
                                  onChange={(e) => setNewKwInputs((prev) => ({ ...prev, [`tier3__${catKey}`]: e.target.value }))}
                                  onKeyDown={(e) => {
                                    if (e.key === "Enter") {
                                      const val = (newKwInputs[`tier3__${catKey}`] || "").trim();
                                      if (!val) return;
                                      setRoutingKeywords((prev) => ({ ...prev, tier3: { ...prev.tier3, [catKey]: { ...prev.tier3[catKey], keywords: [...(prev.tier3[catKey].keywords || []), val] } } }));
                                      setNewKwInputs((prev) => ({ ...prev, [`tier3__${catKey}`]: "" }));
                                    }
                                  }}
                                  sx={{ flex: 1, maxWidth: 280 }} />
                                <Button size="small" variant="outlined"
                                  onClick={() => {
                                    const val = (newKwInputs[`tier3__${catKey}`] || "").trim();
                                    if (!val) return;
                                    setRoutingKeywords((prev) => ({ ...prev, tier3: { ...prev.tier3, [catKey]: { ...prev.tier3[catKey], keywords: [...(prev.tier3[catKey].keywords || []), val] } } }));
                                    setNewKwInputs((prev) => ({ ...prev, [`tier3__${catKey}`]: "" }));
                                  }}>添加</Button>
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
                <TextField size="small" label="显示姓名（可选）" value={newInviteName}
                  onChange={(e) => setNewInviteName(e.target.value)} sx={{ minWidth: 160 }} />
                <TextField size="small" label="自定义邀请码（可选）" value={newInviteCode}
                  onChange={(e) => setNewInviteCode(e.target.value)} placeholder="留空则自动生成"
                  inputProps={{ maxLength: 32 }} sx={{ minWidth: 180 }} />
                <Button variant="contained" size="small" onClick={onCreateInviteCode}>生成邀请码</Button>
              </Stack>
              <TableContainer sx={{ border: "1px solid #f0f0f0", borderRadius: 1.5, backgroundColor: "#f8fbfc" }}>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      {["邀请码", "医生账号", "姓名", "状态", "创建时间", "操作"].map((h) => (
                        <TableCell key={h} sx={{ fontWeight: 700, fontSize: TYPE.caption.fontSize, backgroundColor: "#eef4f6", color: "text.secondary" }}>{h}</TableCell>
                      ))}
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {inviteCodes.length === 0 ? (
                      <TableRow><TableCell colSpan={6}><Typography variant="body2" color="text.secondary">暂无邀请码</Typography></TableCell></TableRow>
                    ) : inviteCodes.map((row) => (
                      <TableRow key={row.code}>
                        <TableCell sx={{ fontFamily: "monospace", fontWeight: 700 }}>{row.code}</TableCell>
                        <TableCell sx={{ color: row.doctor_id ? "text.primary" : "text.disabled", fontStyle: row.doctor_id ? "normal" : "italic" }}>
                          {row.doctor_id || "待首次登录"}
                        </TableCell>
                        <TableCell>{row.doctor_name || "-"}</TableCell>
                        <TableCell>
                          <Chip size="small" label={row.active ? "有效" : "已吊销"} color={row.active ? "success" : "default"} />
                        </TableCell>
                        <TableCell>{row.created_at}</TableCell>
                        <TableCell>
                          {row.active && <Button size="small" color="error" onClick={() => setRevokeTarget(row.code)}>吊销</Button>}
                          <IconButton size="small" onClick={() => handleAdminQR(row.doctor_id, row.doctor_name)}>
                            <QrCode2OutlinedIcon sx={{ fontSize: ICON.xs }} />
                          </IconButton>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
              <Dialog open={!!revokeTarget} onClose={() => setRevokeTarget(null)}>
                <DialogTitle>确认吊销邀请码</DialogTitle>
                <DialogContent>
                  <Typography>确认吊销邀请码 <strong>{revokeTarget}</strong>？此操作不可撤销。</Typography>
                </DialogContent>
                <DialogActions>
                  <Button onClick={() => setRevokeTarget(null)}>取消</Button>
                  <Button color="error" variant="contained"
                    onClick={async () => { await onRevokeInviteCode(revokeTarget); setRevokeTarget(null); }}>吊销</Button>
                </DialogActions>
              </Dialog>
            </Box>
          ) : activeTable === "system_prompts" ? (
            <Stack spacing={2}>
              {prompts.length === 0 && !loading && (
                <Typography color="text.secondary" variant="body2">暂无提示词，请点击"刷新"。</Typography>
              )}
              {prompts.map((p) => {
                const isDirty = (promptEdits[p.key] ?? p.content) !== p.content;
                const isSaving = !!promptSaving[p.key];
                return (
                  <Box key={p.key} sx={{ border: "1px solid #f0f0f0", borderRadius: 1.5, overflow: "hidden" }}>
                    <Stack direction="row" alignItems="center" justifyContent="space-between"
                      sx={{ px: 1.5, py: 1, backgroundColor: "#eef4f6", borderBottom: "1px solid #f0f0f0" }}>
                      <Stack direction="row" spacing={1} alignItems="center">
                        <Chip label={p.key} size="small" sx={{ fontFamily: "ui-monospace, monospace", fontWeight: 700, fontSize: TYPE.caption.fontSize }} />
                        {isDirty && <Chip label="未保存" size="small" color="warning" sx={{ height: 18, fontSize: TYPE.micro.fontSize }} />}
                      </Stack>
                      <Stack direction="row" spacing={1} alignItems="center">
                        <Typography variant="caption" color="text.secondary">{p.updated_at ? `更新：${p.updated_at}` : ""}</Typography>
                        <Button size="small" variant={isDirty ? "contained" : "outlined"} disabled={isSaving || !isDirty} onClick={() => savePrompt(p.key)}>
                          {isSaving ? "保存中…" : "保存"}
                        </Button>
                      </Stack>
                    </Stack>
                    <TextField multiline fullWidth minRows={6} maxRows={30}
                      value={promptEdits[p.key] ?? p.content}
                      onChange={(e) => setPromptEdits((prev) => ({ ...prev, [p.key]: e.target.value }))}
                      sx={{
                        "& .MuiOutlinedInput-root": { borderRadius: 0, border: "none" },
                        "& .MuiOutlinedInput-notchedOutline": { border: "none" },
                        "& textarea": { fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace", fontSize: TYPE.secondary.fontSize, lineHeight: 1.6, backgroundColor: "#fff" },
                      }} />
                  </Box>
                );
              })}
            </Stack>
          ) : (
            <>
              <TableContainer sx={{ border: "1px solid #f0f0f0", borderRadius: 1.5, backgroundColor: "#f8fbfc", maxHeight: "65vh" }}>
                <Table size="small" stickyHeader sx={{ tableLayout: "fixed", minWidth: 980 }}>
                  <TableHead>
                    <TableRow>
                      {columns.map((key) => (
                        <TableCell key={`head-${key}`} onClick={() => handleSort(key)}
                          sx={{ fontWeight: 700, color: "text.secondary", whiteSpace: "nowrap", width: COL_WIDTH[key] || 140, maxWidth: COL_WIDTH[key] || 140, backgroundColor: "#eef4f6", px: 1, py: 0.75, fontSize: TYPE.caption.fontSize, cursor: "pointer", userSelect: "none", "&:hover": { backgroundColor: "#e2edf0" } }}>
                          <Stack direction="row" alignItems="center" spacing={0.3}>
                            <span>{t(`admin.cols.${key}`)}</span>
                            {sortCol === key ? (
                              sortDir === "asc"
                                ? <ArrowUpwardIcon sx={{ fontSize: ICON.xs, color: "primary.main" }} />
                                : <ArrowDownwardIcon sx={{ fontSize: ICON.xs, color: "primary.main" }} />
                            ) : (
                              <UnfoldMoreIcon sx={{ fontSize: ICON.xs, color: "#ccc" }} />
                            )}
                          </Stack>
                        </TableCell>
                      ))}
                      <TableCell sx={{ width: 56, maxWidth: 56, backgroundColor: "#eef4f6", px: 0.5, py: 0.75 }} />
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {sortedRows.map((row, rowIdx) => (
                      <TableRow key={`row-${row.id ?? row.key ?? rowIdx}`} hover
                        onClick={() => { setSelectedRow(row); setRowEditMode(false); }}
                        sx={{ cursor: "pointer", "&:hover": { backgroundColor: "#f0f7ff" } }}>
                        {columns.map((key) => (
                          <TableCell key={`cell-${rowIdx}-${key}`}
                            sx={{ verticalAlign: "top", borderBottom: "1px solid #e4edf0", width: COL_WIDTH[key] || 140, maxWidth: COL_WIDTH[key] || 140, py: 0.45, px: 1, fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, Liberation Mono, monospace", fontSize: TYPE.caption.fontSize, lineHeight: 1.35, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                            {renderCellContent(row[key])}
                          </TableCell>
                        ))}
                        <TableCell sx={{ py: 0.45, px: 0.5, borderBottom: "1px solid #e4edf0" }}>
                          <IconButton size="small" onClick={(e) => { e.stopPropagation(); copyRow(row); }}
                            sx={{ opacity: 0.4, "&:hover": { opacity: 1 } }}>
                            <ContentCopyOutlinedIcon sx={{ fontSize: ICON.xs }} />
                          </IconButton>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>

              {/* Row detail dialog */}
              <Dialog open={!!selectedRow} onClose={() => setSelectedRow(null)} maxWidth="md" fullWidth
                PaperProps={{ sx: { borderRadius: 2 } }}>
                <DialogTitle sx={{ fontWeight: 700, pb: 1 }}>
                  <Stack direction="row" alignItems="center" justifyContent="space-between">
                    <span>
                      {t(`admin.tables.${activeTable}`)}
                      <Typography component="span" variant="body2" color="text.secondary" sx={{ ml: 1 }}>
                        #{selectedRow?.id}
                      </Typography>
                    </span>
                    {activeTable === "medical_records" && !rowEditMode && (
                      <Button size="small" startIcon={<EditOutlinedIcon fontSize="small" />}
                        onClick={() => {
                          const init = {};
                          RECORD_EDIT_FIELDS.forEach(({ key }) => { init[key] = selectedRow?.[key] || ""; });
                          setRowEditForm(init);
                          setRowEditMode(true);
                        }}>编辑</Button>
                    )}
                  </Stack>
                </DialogTitle>
                <DialogContent dividers>
                  {rowEditMode ? (
                    <Stack spacing={2}>
                      {RECORD_EDIT_FIELDS.map(({ key, label }) => (
                        <TextField key={key} label={label} multiline minRows={2} maxRows={8} size="small" fullWidth
                          value={rowEditForm[key] || ""}
                          onChange={(e) => setRowEditForm((f) => ({ ...f, [key]: e.target.value }))} />
                      ))}
                    </Stack>
                  ) : (
                    <Stack spacing={0}>
                      {selectedRow && Object.entries(selectedRow).map(([key, value]) => (
                        <Box key={key} sx={{ display: "flex", borderBottom: "1px solid #f0f4f6", py: 0.8 }}>
                          <Typography variant="caption" sx={{ fontWeight: 700, color: "text.secondary", width: 180, flexShrink: 0, pt: 0.1 }}>
                            {t(`admin.cols.${key}`)}
                          </Typography>
                          <Typography variant="body2" sx={{ fontFamily: "ui-monospace, monospace", fontSize: TYPE.caption.fontSize, whiteSpace: "pre-wrap", wordBreak: "break-all", flex: 1 }}>
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
                    <Button onClick={() => setSelectedRow(null)}>关闭</Button>
                  )}
                </DialogActions>
              </Dialog>
            </>
          )}
        </Box>
      </Box>

      <Snackbar open={snack.open} autoHideDuration={3000}
        onClose={() => setSnack((s) => ({ ...s, open: false }))}
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}>
        <Alert severity={snack.severity} onClose={() => setSnack((s) => ({ ...s, open: false }))} sx={{ width: "100%" }}>
          {snack.message}
        </Alert>
      </Snackbar>
      <QRDialog open={adminQrOpen} onClose={() => setAdminQrOpen(false)}
        title="医生二维码" name={adminQrName} url={adminQrUrl}
        loading={adminQrLoading} error={adminQrError}
        onRegenerate={() => handleAdminQR(adminQrDoctorId, adminQrName)} />
    </Box>
  );
}
