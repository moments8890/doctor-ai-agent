/** AdminRawData — raw table browser (GitHub Dark theme, sidebar-driven) */
import { useEffect, useMemo, useRef, useState } from "react";
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
import UnfoldMoreIcon from "@mui/icons-material/UnfoldMore";
import ArrowUpwardIcon from "@mui/icons-material/ArrowUpward";
import ArrowDownwardIcon from "@mui/icons-material/ArrowDownward";
import EditOutlinedIcon from "@mui/icons-material/EditOutlined";
import QrCode2OutlinedIcon from "@mui/icons-material/QrCode2Outlined";
import QRDialog from "./components/QRDialog";
import AdminRelatedDialog from "./AdminRelatedDialog";
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
import { GH } from "./adminTheme";

// ── Table groups (exported for sidebar navigation) ────────────────────────────
export const TABLE_GROUPS = {
  "\u6838\u5fc3": [
    "doctors", "patients", "medical_records",
    "doctor_tasks",
  ],
  "\u8bbe\u7f6e": [
    "doctor_knowledge_items",
    "interview_sessions", "doctor_chat_log",
  ],
  "\u7cfb\u7edf": [
    "audit_log", "invite_codes", "system_prompts",
    "system_prompt_versions", "runtime_config",
    "routing_keywords",
  ],
};

// All browsable table keys (flat list)
const ALL_TABLE_KEYS = Object.values(TABLE_GROUPS).flat();

// System table keys (for filter visibility)
const SYSTEM_KEYS = [
  "audit_log", "invite_codes", "system_prompts",
  "system_prompt_versions", "runtime_config", "routing_keywords",
];

const RECORD_EDIT_FIELDS = [
  { key: "record_type", label: "\u8bb0\u5f55\u7c7b\u578b" },
  { key: "content", label: "\u4e34\u5e8a\u7b14\u8bb0" },
  { key: "tags", label: "\u5173\u952e\u8bcd\u6807\u7b7e" },
];

const ENUM_ZH = {
  follow_up: "\u968f\u8bbf", review: "\u590d\u67e5", call: "\u7535\u8bdd\u8054\u7cfb", message: "\u53d1\u9001\u6d88\u606f",
  prescription: "\u5904\u65b9\u7eed\u5f00", referral: "\u8f6c\u8bca", education: "\u60a3\u8005\u6559\u80b2",
  pending: "\u5f85\u5904\u7406", done: "\u5df2\u5b8c\u6210", cancelled: "\u5df2\u53d6\u6d88", snoozed: "\u5df2\u63a8\u8fdf",
  active: "\u6709\u6548", expired: "\u5df2\u8fc7\u671f", confirmed: "\u5df2\u786e\u8ba4", abandoned: "\u5df2\u64a4\u9500",
  system: "\u7cfb\u7edf", doctor: "\u533b\u751f", patient: "\u60a3\u8005", ai: "AI",
  inpatient: "\u4f4f\u9662", outpatient: "\u95e8\u8bca", unknown: "\u672a\u77e5",
  first_visit: "\u521d\u8bca", follow_up_visit: "\u590d\u8bca",
  visit: "\u95e8\u8bca\u8bb0\u5f55", dictation: "\u8bed\u97f3\u5f55\u5165", import: "\u5bfc\u5165", interview_summary: "\u95ee\u8bca\u603b\u7ed3",
  overdue: "\u5df2\u903e\u671f", due_soon: "\u5373\u5c06\u5230\u671f", ok: "\u6b63\u5e38", not_needed: "\u65e0\u9700\u968f\u8bbf",
  scheduled: "\u5df2\u5b89\u6392",
  critical: "\u5371\u91cd", high: "\u9ad8\u98ce\u9669", medium: "\u4e2d\u98ce\u9669", low: "\u4f4e\u98ce\u9669",
  male: "\u7537", female: "\u5973",
  app: "\u9080\u8bf7\u7801\u767b\u5f55", wechat_mini: "\u5fae\u4fe1\u5c0f\u7a0b\u5e8f",
  stroke: "\u8111\u5352\u4e2d", parkinson: "\u5e15\u91d1\u68ee", dementia: "\u75f4\u5446", epilepsy: "\u764b\u75eb",
  headache: "\u5934\u75db", heart_failure: "\u5fc3\u529b\u8870\u7aed", arrhythmia: "\u5fc3\u5f8b\u5931\u5e38",
  hypertension: "\u9ad8\u8840\u538b", coronary: "\u51a0\u5fc3\u75c5", diabetes: "\u7cd6\u5c3f\u75c5",
  chat: "\u5bf9\u8bdd",
};

function toCell(value) {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function renderCellContent(value) {
  if (value === null || value === undefined || value === "") {
    return <span style={{ color: GH.textMuted }}>&mdash;</span>;
  }
  if (typeof value === "boolean") return value ? "\u662f" : "\u5426";
  const str = typeof value === "object" ? JSON.stringify(value, null, 0) : String(value);
  if (ENUM_ZH[str]) return ENUM_ZH[str];
  if (/^\d{4}-\d{2}-\d{2}T/.test(str)) {
    return <span style={{ whiteSpace: "nowrap" }}>{str.slice(0, 16).replace("T", " ")}</span>;
  }
  const MAX = 60;
  if (str.length > MAX) {
    return (
      <Tooltip title={<span style={{ whiteSpace: "pre-wrap", maxWidth: 400, display: "block", fontSize: 11 }}>{str.slice(0, 500)}{str.length > 500 ? "\u2026" : ""}</span>} placement="top" arrow>
        <span style={{ cursor: "pointer" }}>
          {str.slice(0, MAX)}<span style={{ color: GH.textMuted }}>&hellip;</span>
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

// ── Dark theme MUI sx helpers ─────────────────────────────────────────────────
const darkTextField = {
  "& .MuiOutlinedInput-root": {
    color: GH.text,
    "& fieldset": { borderColor: GH.border },
    "&:hover fieldset": { borderColor: GH.textMuted },
    "&.Mui-focused fieldset": { borderColor: GH.blue },
  },
  "& .MuiInputLabel-root": { color: GH.textMuted },
  "& .MuiInputLabel-root.Mui-focused": { color: GH.blue },
  "& .MuiAutocomplete-clearIndicator": { color: GH.textMuted },
  "& .MuiAutocomplete-popupIndicator": { color: GH.textMuted },
};

const darkBtn = {
  borderColor: GH.border,
  color: GH.text,
  "&:hover": { borderColor: GH.textMuted, background: GH.hoverBg },
};
const darkBtnContained = {
  background: GH.blue,
  color: "#fff",
  "&:hover": { background: "#4090e0" },
};
const darkBtnSecondary = {
  background: GH.orange,
  color: "#fff",
  "&:hover": { background: "#e06c50" },
};

// ── Main component ─────────────────────────────────────────────────────────────
export default function AdminRawData({ forcedTable }) {
  const [doctorId, setDoctorId] = useState("");
  const [patientName, setPatientName] = useState("");
  const [doctorInput, setDoctorInput] = useState("");
  const [patientInput, setPatientInput] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  // Table is driven by sidebar via forcedTable prop
  const activeTable = ALL_TABLE_KEYS.includes(forcedTable) ? forcedTable : TABLE_GROUPS["\u6838\u5fc3"][0];

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

  // Related data dialog (for doctors/patients tables)
  const [relatedOpen, setRelatedOpen] = useState(false);
  const [relatedType, setRelatedType] = useState(""); // "doctors" or "patients"
  const [relatedId, setRelatedId] = useState(null);

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
      setAdminQrError(e.message || "\u751f\u6210\u5931\u8d25");
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
  const isSystemTab = SYSTEM_KEYS.includes(activeTable);

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
      showSnack("\u8bb0\u5f55\u5df2\u4fdd\u5b58");
    } catch (e) {
      setStatus({ type: "error", text: e.message || "\u4fdd\u5b58\u5931\u8d25" });
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
      setStatus({ type: "success", text: `\u63d0\u793a\u8bcd "${key}" \u5df2\u4fdd\u5b58` });
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
      showSnack("\u5df2\u590d\u5236\u5230\u526a\u8d34\u677f");
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
    const PAGE = 25;
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
    const PAGE = 25;
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
      setStatus({ type: "success", text: "\u914d\u7f6e\u5df2\u4fdd\u5b58\uff08\u672a\u5e94\u7528\uff09\u3002\u8bf7\u5148\u9a8c\u8bc1\uff0c\u518d\u624b\u52a8\u5e94\u7528\u3002" });
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
      if (!payload.ok) { setStatus({ type: "error", text: `\u914d\u7f6e\u6821\u9a8c\u5931\u8d25\uff1a${errors.join("\uff1b") || "\u672a\u77e5\u9519\u8bef"}` }); return; }
      if (warnings.length) { setStatus({ type: "warning", text: `\u914d\u7f6e\u6821\u9a8c\u901a\u8fc7\uff08\u542b\u8b66\u544a\uff09\uff1a${warnings.join("\uff1b")}` }); return; }
      setStatus({ type: "success", text: "\u914d\u7f6e\u6821\u9a8c\u901a\u8fc7\u3002" });
    } catch (error) {
      setStatus({ type: "error", text: `\u914d\u7f6e\u6821\u9a8c\u5931\u8d25\uff1a${error.message}` });
    }
  }

  async function applyRuntimeConfigNow() {
    try {
      const payload = await applyAdminRuntimeConfig();
      setRuntimeConfigSource(payload.source || "");
      setRuntimeConfigMap(payload.config || {});
      setRuntimeCategories(payload.categories || []);
      setStatus({ type: "success", text: "\u914d\u7f6e\u5df2\u5e94\u7528\u5e76\u70ed\u66f4\u65b0\u3002" });
    } catch (error) {
      setStatus({ type: "error", text: `\u914d\u7f6e\u5e94\u7528\u5931\u8d25\uff1a${error.message}` });
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
      showSnack("\u9080\u8bf7\u7801\u5df2\u751f\u6210");
    } catch (error) {
      setStatus({ type: "error", text: error.message });
    }
  }

  async function onRevokeInviteCode(code) {
    try {
      await revokeAdminInviteCode(code);
      await loadInviteCodes();
      showSnack("\u9080\u8bf7\u7801\u5df2\u540a\u9500");
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

  // ── Dark-themed table header / cell sx ──────────────────────────────────────
  const thSx = {
    fontWeight: 700,
    color: GH.textMuted,
    whiteSpace: "nowrap",
    backgroundColor: GH.hoverBg,
    borderBottom: `1px solid ${GH.border}`,
    px: 1, py: 0.75,
    fontSize: TYPE.caption.fontSize,
    cursor: "pointer",
    userSelect: "none",
    "&:hover": { backgroundColor: GH.border },
  };

  const tdSx = {
    verticalAlign: "top",
    borderBottom: `1px solid ${GH.border}`,
    py: 0.45, px: 1,
    fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, Liberation Mono, monospace",
    fontSize: TYPE.caption.fontSize,
    lineHeight: 1.35,
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
    color: GH.text,
  };

  return (
    <Box sx={{ p: "10px 16px" }}>
      {/* Single panel — no GroupedTabBar, table selected from sidebar */}
      <Box sx={{ background: GH.card, border: `1px solid ${GH.border}`, borderRadius: 1.5, overflow: "hidden" }}>

        <Box sx={{ p: 1.5 }}>
          {!!status.text && (
            <Alert
              severity={status.type}
              sx={{
                mb: 1.5, fontSize: 12,
                background: status.type === "error" ? "rgba(248,81,73,0.12)" : status.type === "success" ? "rgba(63,185,80,0.12)" : "rgba(88,166,255,0.12)",
                color: status.type === "error" ? GH.red : status.type === "success" ? GH.green : GH.blue,
                "& .MuiAlert-icon": { color: "inherit" },
              }}
            >
              {status.text}
            </Alert>
          )}

          {/* Toolbar row */}
          <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 1, position: "sticky", top: 0, zIndex: 2, background: GH.card, pb: 0.5 }}>
            <Stack direction="row" spacing={0.8} alignItems="center">
              <StorageOutlinedIcon sx={{ fontSize: 16, color: GH.textMuted }} />
              <Typography sx={{ fontWeight: 700, fontSize: 13, color: "#fff" }}>{activeLabel}</Typography>
            </Stack>
            {activeTable === "runtime_config" ? (
              <Stack direction="row" spacing={0.8}>
                <Button variant="outlined" size="small" onClick={loadRuntimeConfig} disabled={loading} sx={darkBtn}>{"\u52a0\u8f7d\u914d\u7f6e"}</Button>
                <Button variant="outlined" size="small" onClick={verifyRuntimeConfig} disabled={loading} sx={darkBtn}>{"\u9a8c\u8bc1\u914d\u7f6e"}</Button>
                <Button variant="contained" size="small" onClick={saveRuntimeConfig} disabled={loading} sx={darkBtnContained}>{"\u4fdd\u5b58\u914d\u7f6e"}</Button>
                <Button variant="contained" size="small" onClick={applyRuntimeConfigNow} disabled={loading} sx={darkBtnSecondary}>{"\u5e94\u7528\u914d\u7f6e"}</Button>
              </Stack>
            ) : activeTable === "routing_keywords" ? (
              <Stack direction="row" spacing={0.8}>
                <Button variant="outlined" size="small" onClick={loadRoutingKeywords} disabled={loading} sx={darkBtn}>{"\u52a0\u8f7d"}</Button>
                <Button variant="contained" size="small" disabled={loading} sx={darkBtnContained}
                  onClick={async () => {
                    try { await putAdminRoutingKeywords(null, routingKeywords); showSnack("\u8def\u7531\u5173\u952e\u8bcd\u5df2\u4fdd\u5b58\u3002"); }
                    catch (error) { setStatus({ type: "error", text: `\u4fdd\u5b58\u5931\u8d25\uff1a${error.message}` }); }
                  }}>{"\u4fdd\u5b58"}</Button>
                <Button variant="contained" size="small" disabled={loading} sx={darkBtnSecondary}
                  onClick={async () => {
                    try { const payload = await reloadAdminRoutingKeywords(); setStatus({ type: "success", text: `${payload.loaded ?? ""} \u4e2a\u5173\u952e\u8bcd\u5df2\u52a0\u8f7d` }); }
                    catch (error) { setStatus({ type: "error", text: `\u70ed\u52a0\u8f7d\u5931\u8d25\uff1a${error.message}` }); }
                  }}>{"\u70ed\u52a0\u8f7d"}</Button>
              </Stack>
            ) : activeTable === "system_prompts" ? (
              <Stack direction="row" spacing={0.8}>
                <Button variant="outlined" size="small" onClick={loadPrompts} disabled={loading} sx={darkBtn}>{"\u5237\u65b0"}</Button>
                <Typography variant="caption" sx={{ alignSelf: "center", color: GH.textMuted }}>{prompts.length} {"\u4e2a\u63d0\u793a\u8bcd"}</Typography>
              </Stack>
            ) : (
              <Stack direction="row" spacing={0.8}>
                <Typography variant="caption" sx={{ alignSelf: "center", mr: 1, color: GH.textMuted }}>{rows.length} {"\u884c"}</Typography>
                {rowsHasMore && (
                  <Chip label={rowsLoadingMore ? "\u52a0\u8f7d\u4e2d\u2026" : "\u52a0\u8f7d\u66f4\u591a"} size="small" variant="outlined"
                    onClick={loadMoreRows} disabled={rowsLoadingMore}
                    sx={{ fontSize: TYPE.micro.fontSize, cursor: "pointer", color: GH.blue, borderColor: GH.border }} />
                )}
                <Button variant="outlined" size="small" startIcon={<DownloadOutlinedIcon fontSize="small" />} onClick={exportCsv} disabled={!rows.length} sx={darkBtn}>CSV</Button>
                <Button variant="outlined" size="small" startIcon={<DownloadOutlinedIcon fontSize="small" />} onClick={exportJson} disabled={!rows.length} sx={darkBtn}>JSON</Button>
                <Button variant="contained" size="small" onClick={() => loadAll(activeTable)} disabled={loading} sx={darkBtnContained}>
                  {loading ? "\u52a0\u8f7d\u4e2d\u2026" : t("admin.reload")}
                </Button>
              </Stack>
            )}
          </Box>

          {/* Filters — shown for non-system, non-invite tables */}
          {!isSystemTab && activeTable !== "invite_codes" && (
            <Box sx={{ border: `1px solid ${GH.border}`, borderRadius: 1.5, backgroundColor: GH.hoverBg, p: 1.2, mb: 1.2 }}>
              <Stack direction={{ xs: "column", md: "row" }} spacing={1} sx={{ alignItems: { md: "center" } }}>
                <Autocomplete options={doctorOptions} value={doctorId || null} inputValue={doctorInput}
                  openOnFocus sx={{ minWidth: { md: 220 }, flex: 1, ...darkTextField }}
                  slotProps={{ listbox: { sx: { maxHeight: 260, background: GH.card, color: GH.text, "& .MuiAutocomplete-option": { "&:hover": { background: GH.hoverBg } } } } }}
                  onInputChange={(_, value) => setDoctorInput(value)}
                  onChange={async (_, value) => {
                    const nextDoctor = (value || "").trim();
                    setDoctorId(nextDoctor); setDoctorInput(nextDoctor);
                    setPatientName(""); setPatientInput("");
                    await loadAll(activeTable, { doctorId: nextDoctor, patientName: "" });
                  }}
                  filterOptions={prefixFilter} clearOnEscape
                  renderInput={(params) => <TextField {...params} size="small" label={t("admin.filters.doctorName")} placeholder={t("common.all")} sx={darkTextField} />}
                />
                <Autocomplete options={patientOptions} value={patientName || null} inputValue={patientInput}
                  openOnFocus sx={{ minWidth: { md: 220 }, flex: 1, ...darkTextField }}
                  slotProps={{ listbox: { sx: { maxHeight: 260, background: GH.card, color: GH.text, "& .MuiAutocomplete-option": { "&:hover": { background: GH.hoverBg } } } } }}
                  onInputChange={(_, value) => setPatientInput(value)}
                  onChange={async (_, value) => {
                    const nextPatient = (value || "").trim();
                    setPatientName(nextPatient); setPatientInput(nextPatient);
                    await loadAll(activeTable, { patientName: nextPatient });
                  }}
                  filterOptions={prefixFilter} clearOnEscape
                  renderInput={(params) => <TextField {...params} size="small" label={t("admin.filters.patientName")} placeholder={t("common.all")} sx={darkTextField} />}
                />
                <TextField size="small" type="date" label={t("admin.filters.dateFrom")}
                  InputLabelProps={{ shrink: true }} value={dateFrom}
                  onChange={(e) => setDateFrom(e.target.value)} sx={{ minWidth: { md: 160 }, ...darkTextField }} />
                <TextField size="small" type="date" label={t("admin.filters.dateTo")}
                  InputLabelProps={{ shrink: true }} value={dateTo}
                  onChange={(e) => setDateTo(e.target.value)} sx={{ minWidth: { md: 160 }, ...darkTextField }} />
                <Button variant="outlined" size="small" onClick={() => loadAll(activeTable)} disabled={loading} sx={{ whiteSpace: "nowrap", minWidth: 92, ...darkBtn }}>
                  {loading ? "\u52a0\u8f7d\u4e2d\u2026" : t("admin.reload")}
                </Button>
                <Button size="small" variant="text" sx={{ whiteSpace: "nowrap", color: GH.textMuted }}
                  disabled={!doctorId && !patientName && !dateFrom && !dateTo}
                  onClick={() => {
                    setDoctorId(""); setDoctorInput(""); setPatientName(""); setPatientInput("");
                    setDateFrom(""); setDateTo("");
                    loadAll(activeTable, { doctorId: "", patientName: "", dateFrom: "", dateTo: "" });
                  }}>{"\u6e05\u9664\u7b5b\u9009"}</Button>
              </Stack>
            </Box>
          )}

          {/* Content: runtime_config */}
          {activeTable === "runtime_config" ? (
            <Box sx={{ border: `1px solid ${GH.border}`, borderRadius: 1.5, backgroundColor: GH.hoverBg, p: 1.2, mb: 1.2 }}>
              <Stack direction={{ xs: "column", md: "row" }} justifyContent="space-between" alignItems={{ xs: "flex-start", md: "center" }} spacing={1} sx={{ mb: 1 }}>
                <Typography variant="subtitle2" sx={{ fontWeight: 700, color: "#fff" }}>{t("admin.config.title")}</Typography>
                <Chip size="small" variant="outlined" label={`${t("admin.config.source")}\uff1a${runtimeConfigSource || "-"}`} sx={{ color: GH.textMuted, borderColor: GH.border }} />
              </Stack>
              <Box sx={{ border: `1px solid ${GH.border}`, borderRadius: 1.2, backgroundColor: GH.card, p: 1, mb: 1 }}>
                <Stack direction={{ xs: "column", md: "row" }} spacing={1} alignItems={{ md: "center" }} justifyContent="space-between">
                  <Box sx={{ minWidth: 0 }}>
                    <Typography variant="caption" sx={{ fontWeight: 700, display: "block", color: GH.textMuted }}>Cloudflared Dev URL</Typography>
                    <Typography variant="body2" sx={{ fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, Liberation Mono, monospace", wordBreak: "break-all", color: GH.text }}>
                      {tunnelInfo.url || "-"}
                    </Typography>
                    <Typography variant="caption" sx={{ color: GH.textMuted }}>
                      {"\u6765\u6e90"}: {tunnelInfo.source || "-"} {tunnelInfo.updated_at ? `\u00b7 \u66f4\u65b0\u65f6\u95f4: ${tunnelInfo.updated_at}` : ""}
                    </Typography>
                    {!tunnelInfo.ok && tunnelInfo.detail ? (
                      <Typography variant="caption" sx={{ display: "block", color: GH.orange }}>{tunnelInfo.detail}</Typography>
                    ) : null}
                  </Box>
                  <Stack direction="row" spacing={0.8}>
                    <Button variant="outlined" size="small" onClick={loadTunnelUrl} disabled={loading} sx={darkBtn}>{"\u5237\u65b0\u5730\u5740"}</Button>
                    <Button variant="outlined" size="small" disabled={!tunnelInfo.url} sx={darkBtn}
                      onClick={async () => {
                        try { await navigator.clipboard.writeText(tunnelInfo.url); setStatus({ type: "success", text: "Cloudflared \u5730\u5740\u5df2\u590d\u5236\u3002" }); }
                        catch (error) { setStatus({ type: "error", text: t("admin.copyFailed", { message: error.message }) }); }
                      }}>{"\u590d\u5236\u5730\u5740"}</Button>
                    <Button variant="contained" size="small" disabled={!tunnelInfo.url} sx={darkBtnContained}
                      onClick={() => window.open(tunnelInfo.url, "_blank", "noopener,noreferrer")}>{"\u6253\u5f00\u5730\u5740"}</Button>
                  </Stack>
                </Stack>
              </Box>
              <Stack spacing={1}>
                {(runtimeCategories || []).map((cat) => (
                  <Box key={`cfg-cat-${cat.key}`} sx={{ border: `1px solid ${GH.border}`, borderRadius: 1.2, backgroundColor: GH.card, overflow: "hidden" }}>
                    <Box sx={{ px: 1.2, py: 0.9, borderBottom: `1px solid ${GH.border}`, backgroundColor: GH.hoverBg }}>
                      <Stack direction="row" justifyContent="space-between" alignItems="center">
                        <Typography variant="subtitle2" sx={{ fontWeight: 700, color: "#fff" }}>{cat.key}</Typography>
                        <Chip size="small" label={`${(cat.items || []).length} \u9879`} sx={{ height: 22, color: GH.textMuted, borderColor: GH.border }} />
                      </Stack>
                      <Typography variant="caption" sx={{ color: GH.textMuted }}>{cat.description_zh || cat.description || "-"}</Typography>
                    </Box>
                    <Box sx={{ px: 1, py: 0.7, display: { xs: "none", md: "grid" }, gridTemplateColumns: "210px minmax(240px,0.85fr) minmax(340px,1.15fr)", gap: 1, backgroundColor: GH.hoverBg, borderBottom: `1px solid ${GH.border}` }}>
                      <Typography variant="caption" sx={{ fontWeight: 700, color: GH.textMuted }}>{"\u914d\u7f6e\u9879"}</Typography>
                      <Typography variant="caption" sx={{ fontWeight: 700, color: GH.textMuted }}>{"\u8bf4\u660e"}</Typography>
                      <Typography variant="caption" sx={{ fontWeight: 700, color: GH.textMuted }}>{t("admin.config.value")}</Typography>
                    </Box>
                    <Box>
                      {(cat.items || []).map((item, idx) => (
                        <Box key={`cfg-item-${item.key}`}
                          sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "210px minmax(240px,0.85fr) minmax(340px,1.15fr)" }, gap: 1, px: 1, py: 0.9, borderBottom: idx < (cat.items || []).length - 1 ? `1px solid ${GH.border}` : "none", alignItems: "center", backgroundColor: idx % 2 ? GH.card : GH.bg }}>
                          <Box>
                            <Typography sx={{ fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, Liberation Mono, monospace", fontSize: TYPE.caption.fontSize, fontWeight: 600, overflowWrap: "anywhere", wordBreak: "break-word", lineHeight: 1.3, color: GH.text }}>
                              {item.key}
                            </Typography>
                          </Box>
                          <Typography variant="caption" sx={{ lineHeight: 1.45, color: GH.textMuted }}>
                            {item.description_zh || item.description || "-"}
                          </Typography>
                          {item.input_type === "boolean" ? (
                            <Box sx={{ display: "flex", alignItems: "center", justifyContent: { xs: "flex-start", md: "center" }, minHeight: 40 }}>
                              <Switch size="small" checked={isTruthyValue(runtimeConfigMap[item.key] ?? item.value ?? "")}
                                onChange={(e) => updateRuntimeValue(item.key, e.target.checked ? "true" : "false")} />
                              <Typography variant="caption" sx={{ color: GH.textMuted }}>
                                {isTruthyValue(runtimeConfigMap[item.key] ?? item.value ?? "") ? "\u5f00\u542f" : "\u5173\u95ed"}
                              </Typography>
                            </Box>
                          ) : (item.options || []).length ? (
                            <TextField size="small" select value={runtimeConfigMap[item.key] ?? item.value ?? ""}
                              onChange={(e) => updateRuntimeValue(item.key, e.target.value)}
                              label={t("admin.config.value")} fullWidth sx={darkTextField}>
                              {(item.options || []).map((opt) => (
                                <MenuItem key={`cfg-opt-${item.key}-${opt}`} value={opt}>{opt}</MenuItem>
                              ))}
                            </TextField>
                          ) : (
                            <TextField size="small" type={item.input_type === "number" ? "number" : "text"}
                              value={runtimeConfigMap[item.key] ?? item.value ?? ""}
                              onChange={(e) => updateRuntimeValue(item.key, e.target.value)}
                              label={t("admin.config.value")} fullWidth sx={darkTextField} />
                          )}
                        </Box>
                      ))}
                    </Box>
                  </Box>
                ))}
              </Stack>
              <Typography variant="caption" sx={{ display: "block", mt: 0.8, color: GH.textMuted }}>
                {t("admin.config.hint")}
              </Typography>
            </Box>
          ) : activeTable === "routing_keywords" ? (
            <Box sx={{ border: `1px solid ${GH.border}`, borderRadius: 1.5, backgroundColor: GH.hoverBg, p: 1.2, mb: 1.2 }}>
              <Stack spacing={1.2}>
                {Object.entries(routingKeywords).filter(([sectionKey]) => sectionKey !== "tier3").map(([sectionKey, section]) => (
                  <Box key={`kw-section-${sectionKey}`} sx={{ border: `1px solid ${GH.border}`, borderRadius: 1.2, backgroundColor: GH.card, overflow: "hidden" }}>
                    <Box sx={{ px: 1.2, py: 0.9, borderBottom: `1px solid ${GH.border}`, backgroundColor: GH.hoverBg }}>
                      <Typography variant="subtitle2" sx={{ fontWeight: 700, color: "#fff" }}>{sectionKey}</Typography>
                      <Typography variant="caption" sx={{ color: GH.textMuted }}>{section.description_zh || section.description || ""}</Typography>
                    </Box>
                    <Box sx={{ px: 1.2, py: 1 }}>
                      <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.5, mb: 1 }}>
                        {(section.keywords || []).map((kw, kwIdx) => (
                          <Chip key={`kw-chip-${sectionKey}-${kwIdx}`} label={kw} size="small"
                            sx={{ color: GH.text, borderColor: GH.border, "& .MuiChip-deleteIcon": { color: GH.textMuted } }}
                            onDelete={() => {
                              setRoutingKeywords((prev) => ({ ...prev, [sectionKey]: { ...prev[sectionKey], keywords: (prev[sectionKey].keywords || []).filter((_, i) => i !== kwIdx) } }));
                            }} />
                        ))}
                      </Box>
                      <Stack direction="row" spacing={1} alignItems="center">
                        <TextField size="small" placeholder={"\u65b0\u5173\u952e\u8bcd"} value={newKwInputs[sectionKey] || ""}
                          onChange={(e) => setNewKwInputs((prev) => ({ ...prev, [sectionKey]: e.target.value }))}
                          onKeyDown={(e) => {
                            if (e.key === "Enter") {
                              const val = (newKwInputs[sectionKey] || "").trim();
                              if (!val) return;
                              setRoutingKeywords((prev) => ({ ...prev, [sectionKey]: { ...prev[sectionKey], keywords: [...(prev[sectionKey].keywords || []), val] } }));
                              setNewKwInputs((prev) => ({ ...prev, [sectionKey]: "" }));
                            }
                          }}
                          sx={{ flex: 1, maxWidth: 280, ...darkTextField }} />
                        <Button size="small" variant="outlined" sx={darkBtn}
                          onClick={() => {
                            const val = (newKwInputs[sectionKey] || "").trim();
                            if (!val) return;
                            setRoutingKeywords((prev) => ({ ...prev, [sectionKey]: { ...prev[sectionKey], keywords: [...(prev[sectionKey].keywords || []), val] } }));
                            setNewKwInputs((prev) => ({ ...prev, [sectionKey]: "" }));
                          }}>{"\u6dfb\u52a0"}</Button>
                      </Stack>
                    </Box>
                  </Box>
                ))}
                {routingKeywords.tier3 && (
                  <Box sx={{ border: `1px solid ${GH.border}`, borderRadius: 1.2, backgroundColor: GH.card, overflow: "hidden" }}>
                    <Box sx={{ px: 1.2, py: 0.9, borderBottom: `1px solid ${GH.border}`, backgroundColor: GH.hoverBg }}>
                      <Typography variant="subtitle2" sx={{ fontWeight: 700, color: "#fff" }}>tier3</Typography>
                      <Typography variant="caption" sx={{ color: GH.textMuted }}>Tier-3 {"\u4e34\u5e8a\u5173\u952e\u8bcd"}</Typography>
                    </Box>
                    <Box sx={{ px: 1.2, py: 1 }}>
                      <Stack spacing={1}>
                        {Object.entries(routingKeywords.tier3).map(([catKey, catSection]) => (
                          <Box key={`kw-tier3-${catKey}`} sx={{ border: `1px solid ${GH.border}`, borderRadius: 1, overflow: "hidden" }}>
                            <Box sx={{ px: 1, py: 0.6, borderBottom: `1px solid ${GH.border}`, backgroundColor: GH.hoverBg }}>
                              <Typography variant="caption" sx={{ fontWeight: 700, color: GH.text }}>{catKey}</Typography>
                              <Typography variant="caption" sx={{ ml: 1, color: GH.textMuted }}>{catSection.description_zh || catSection.description || ""}</Typography>
                            </Box>
                            <Box sx={{ px: 1, py: 0.8 }}>
                              <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.5, mb: 1 }}>
                                {(catSection.keywords || []).map((kw, kwIdx) => (
                                  <Chip key={`kw-tier3-chip-${catKey}-${kwIdx}`} label={kw} size="small"
                                    sx={{ color: GH.text, borderColor: GH.border, "& .MuiChip-deleteIcon": { color: GH.textMuted } }}
                                    onDelete={() => {
                                      setRoutingKeywords((prev) => ({ ...prev, tier3: { ...prev.tier3, [catKey]: { ...prev.tier3[catKey], keywords: (prev.tier3[catKey].keywords || []).filter((_, i) => i !== kwIdx) } } }));
                                    }} />
                                ))}
                              </Box>
                              <Stack direction="row" spacing={1} alignItems="center">
                                <TextField size="small" placeholder={"\u65b0\u5173\u952e\u8bcd"} value={(newKwInputs[`tier3__${catKey}`]) || ""}
                                  onChange={(e) => setNewKwInputs((prev) => ({ ...prev, [`tier3__${catKey}`]: e.target.value }))}
                                  onKeyDown={(e) => {
                                    if (e.key === "Enter") {
                                      const val = (newKwInputs[`tier3__${catKey}`] || "").trim();
                                      if (!val) return;
                                      setRoutingKeywords((prev) => ({ ...prev, tier3: { ...prev.tier3, [catKey]: { ...prev.tier3[catKey], keywords: [...(prev.tier3[catKey].keywords || []), val] } } }));
                                      setNewKwInputs((prev) => ({ ...prev, [`tier3__${catKey}`]: "" }));
                                    }
                                  }}
                                  sx={{ flex: 1, maxWidth: 280, ...darkTextField }} />
                                <Button size="small" variant="outlined" sx={darkBtn}
                                  onClick={() => {
                                    const val = (newKwInputs[`tier3__${catKey}`] || "").trim();
                                    if (!val) return;
                                    setRoutingKeywords((prev) => ({ ...prev, tier3: { ...prev.tier3, [catKey]: { ...prev.tier3[catKey], keywords: [...(prev.tier3[catKey].keywords || []), val] } } }));
                                    setNewKwInputs((prev) => ({ ...prev, [`tier3__${catKey}`]: "" }));
                                  }}>{"\u6dfb\u52a0"}</Button>
                              </Stack>
                            </Box>
                          </Box>
                        ))}
                      </Stack>
                    </Box>
                  </Box>
                )}
                {!Object.keys(routingKeywords).length ? (
                  <Typography sx={{ color: GH.textMuted }} variant="body2">{"\u6682\u65e0\u5173\u952e\u8bcd\u914d\u7f6e\uff0c\u8bf7\u70b9\u51fb\u201c\u52a0\u8f7d\u201d\u3002"}</Typography>
                ) : null}
              </Stack>
            </Box>
          ) : activeTable === "invite_codes" ? (
            <Box>
              <Stack direction={{ xs: "column", sm: "row" }} spacing={1} sx={{ mb: 2 }}>
                <TextField size="small" label={"\u663e\u793a\u59d3\u540d\uff08\u53ef\u9009\uff09"} value={newInviteName}
                  onChange={(e) => setNewInviteName(e.target.value)} sx={{ minWidth: 160, ...darkTextField }} />
                <TextField size="small" label={"\u81ea\u5b9a\u4e49\u9080\u8bf7\u7801\uff08\u53ef\u9009\uff09"} value={newInviteCode}
                  onChange={(e) => setNewInviteCode(e.target.value)} placeholder={"\u7559\u7a7a\u5219\u81ea\u52a8\u751f\u6210"}
                  inputProps={{ maxLength: 32 }} sx={{ minWidth: 180, ...darkTextField }} />
                <Button variant="contained" size="small" onClick={onCreateInviteCode} sx={darkBtnContained}>{"\u751f\u6210\u9080\u8bf7\u7801"}</Button>
              </Stack>
              <TableContainer sx={{ border: `1px solid ${GH.border}`, borderRadius: 1.5, backgroundColor: GH.card }}>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      {["\u9080\u8bf7\u7801", "\u533b\u751f\u8d26\u53f7", "\u59d3\u540d", "\u72b6\u6001", "\u521b\u5efa\u65f6\u95f4", "\u64cd\u4f5c"].map((h) => (
                        <TableCell key={h} sx={{ fontWeight: 700, fontSize: TYPE.caption.fontSize, backgroundColor: GH.hoverBg, color: GH.textMuted, borderBottom: `1px solid ${GH.border}` }}>{h}</TableCell>
                      ))}
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {inviteCodes.length === 0 ? (
                      <TableRow><TableCell colSpan={6} sx={{ color: GH.textMuted, borderBottom: `1px solid ${GH.border}` }}><Typography variant="body2">{"\u6682\u65e0\u9080\u8bf7\u7801"}</Typography></TableCell></TableRow>
                    ) : inviteCodes.map((row) => (
                      <TableRow key={row.code}>
                        <TableCell sx={{ fontFamily: "monospace", fontWeight: 700, color: GH.text, borderBottom: `1px solid ${GH.border}` }}>{row.code}</TableCell>
                        <TableCell sx={{ color: row.doctor_id ? GH.text : GH.textMuted, fontStyle: row.doctor_id ? "normal" : "italic", borderBottom: `1px solid ${GH.border}` }}>
                          {row.doctor_id || "\u5f85\u9996\u6b21\u767b\u5f55"}
                        </TableCell>
                        <TableCell sx={{ color: GH.text, borderBottom: `1px solid ${GH.border}` }}>{row.doctor_name || "-"}</TableCell>
                        <TableCell sx={{ borderBottom: `1px solid ${GH.border}` }}>
                          <Chip size="small" label={row.active ? "\u6709\u6548" : "\u5df2\u540a\u9500"}
                            sx={{ color: row.active ? GH.green : GH.textMuted, borderColor: row.active ? GH.green : GH.border, background: row.active ? "rgba(63,185,80,0.12)" : "rgba(139,148,158,0.12)" }} />
                        </TableCell>
                        <TableCell sx={{ color: GH.text, borderBottom: `1px solid ${GH.border}` }}>{row.created_at}</TableCell>
                        <TableCell sx={{ borderBottom: `1px solid ${GH.border}` }}>
                          {row.active && <Button size="small" sx={{ color: GH.red }} onClick={() => setRevokeTarget(row.code)}>{"\u540a\u9500"}</Button>}
                          <IconButton size="small" onClick={() => handleAdminQR(row.doctor_id, row.doctor_name)} sx={{ color: GH.textMuted }}>
                            <QrCode2OutlinedIcon sx={{ fontSize: ICON.xs }} />
                          </IconButton>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
              <Dialog open={!!revokeTarget} onClose={() => setRevokeTarget(null)}
                PaperProps={{ sx: { background: GH.card, color: GH.text, border: `1px solid ${GH.border}` } }}>
                <DialogTitle sx={{ color: "#fff" }}>{"\u786e\u8ba4\u540a\u9500\u9080\u8bf7\u7801"}</DialogTitle>
                <DialogContent>
                  <Typography sx={{ color: GH.text }}>{"\u786e\u8ba4\u540a\u9500\u9080\u8bf7\u7801"} <strong>{revokeTarget}</strong>{"\uff1f\u6b64\u64cd\u4f5c\u4e0d\u53ef\u64a4\u9500\u3002"}</Typography>
                </DialogContent>
                <DialogActions>
                  <Button onClick={() => setRevokeTarget(null)} sx={{ color: GH.textMuted }}>{"\u53d6\u6d88"}</Button>
                  <Button variant="contained" sx={{ background: GH.red, "&:hover": { background: "#d63a35" } }}
                    onClick={async () => { await onRevokeInviteCode(revokeTarget); setRevokeTarget(null); }}>{"\u540a\u9500"}</Button>
                </DialogActions>
              </Dialog>
            </Box>
          ) : activeTable === "system_prompts" ? (
            <Stack spacing={2}>
              {prompts.length === 0 && !loading && (
                <Typography sx={{ color: GH.textMuted }} variant="body2">{"\u6682\u65e0\u63d0\u793a\u8bcd\uff0c\u8bf7\u70b9\u51fb\u201c\u5237\u65b0\u201d\u3002"}</Typography>
              )}
              {prompts.map((p) => {
                const isDirty = (promptEdits[p.key] ?? p.content) !== p.content;
                const isSaving = !!promptSaving[p.key];
                return (
                  <Box key={p.key} sx={{ border: `1px solid ${GH.border}`, borderRadius: 1.5, overflow: "hidden" }}>
                    <Stack direction="row" alignItems="center" justifyContent="space-between"
                      sx={{ px: 1.5, py: 1, backgroundColor: GH.hoverBg, borderBottom: `1px solid ${GH.border}` }}>
                      <Stack direction="row" spacing={1} alignItems="center">
                        <Chip label={p.key} size="small" sx={{ fontFamily: "ui-monospace, monospace", fontWeight: 700, fontSize: TYPE.caption.fontSize, color: GH.text, borderColor: GH.border }} />
                        {isDirty && <Chip label={"\u672a\u4fdd\u5b58"} size="small" sx={{ height: 18, fontSize: TYPE.micro.fontSize, color: GH.orange, borderColor: GH.orange, background: "rgba(247,129,102,0.12)" }} />}
                      </Stack>
                      <Stack direction="row" spacing={1} alignItems="center">
                        <Typography variant="caption" sx={{ color: GH.textMuted }}>{p.updated_at ? `\u66f4\u65b0\uff1a${p.updated_at}` : ""}</Typography>
                        <Button size="small" variant={isDirty ? "contained" : "outlined"} disabled={isSaving || !isDirty} onClick={() => savePrompt(p.key)}
                          sx={isDirty ? darkBtnContained : darkBtn}>
                          {isSaving ? "\u4fdd\u5b58\u4e2d\u2026" : "\u4fdd\u5b58"}
                        </Button>
                      </Stack>
                    </Stack>
                    <TextField multiline fullWidth minRows={6} maxRows={30}
                      value={promptEdits[p.key] ?? p.content}
                      onChange={(e) => setPromptEdits((prev) => ({ ...prev, [p.key]: e.target.value }))}
                      sx={{
                        "& .MuiOutlinedInput-root": { borderRadius: 0, border: "none", color: GH.text },
                        "& .MuiOutlinedInput-notchedOutline": { border: "none" },
                        "& textarea": { fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace", fontSize: TYPE.secondary.fontSize, lineHeight: 1.6, backgroundColor: GH.card, color: GH.text },
                      }} />
                  </Box>
                );
              })}
            </Stack>
          ) : (
            <>
              <TableContainer sx={{ border: `1px solid ${GH.border}`, borderRadius: 1.5, backgroundColor: GH.card, maxHeight: "65vh" }}>
                <Table size="small" stickyHeader sx={{ tableLayout: "fixed", minWidth: 980 }}>
                  <TableHead>
                    <TableRow>
                      {columns.map((key) => (
                        <TableCell key={`head-${key}`} onClick={() => handleSort(key)}
                          sx={{ ...thSx, width: COL_WIDTH[key] || 140, maxWidth: COL_WIDTH[key] || 140 }}>
                          <Stack direction="row" alignItems="center" spacing={0.3}>
                            <span>{t(`admin.cols.${key}`)}</span>
                            {sortCol === key ? (
                              sortDir === "asc"
                                ? <ArrowUpwardIcon sx={{ fontSize: ICON.xs, color: GH.blue }} />
                                : <ArrowDownwardIcon sx={{ fontSize: ICON.xs, color: GH.blue }} />
                            ) : (
                              <UnfoldMoreIcon sx={{ fontSize: ICON.xs, color: GH.border }} />
                            )}
                          </Stack>
                        </TableCell>
                      ))}
                      <TableCell sx={{ width: 56, maxWidth: 56, backgroundColor: GH.hoverBg, borderBottom: `1px solid ${GH.border}`, px: 0.5, py: 0.75 }} />
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {sortedRows.map((row, rowIdx) => (
                      <TableRow key={`row-${row.id ?? row.key ?? rowIdx}`}
                        onClick={() => {
                          if (activeTable === "doctors" && row.doctor_id) {
                            setRelatedType("doctors");
                            setRelatedId(row.doctor_id);
                            setRelatedOpen(true);
                          } else if (activeTable === "patients" && row.id) {
                            setRelatedType("patients");
                            setRelatedId(row.id);
                            setRelatedOpen(true);
                          } else {
                            setSelectedRow(row);
                            setRowEditMode(false);
                          }
                        }}
                        sx={{ cursor: "pointer", "&:hover": { backgroundColor: GH.hoverBg } }}>
                        {columns.map((key) => (
                          <TableCell key={`cell-${rowIdx}-${key}`}
                            sx={{ ...tdSx, width: COL_WIDTH[key] || 140, maxWidth: COL_WIDTH[key] || 140 }}>
                            {renderCellContent(row[key])}
                          </TableCell>
                        ))}
                        <TableCell sx={{ py: 0.45, px: 0.5, borderBottom: `1px solid ${GH.border}` }}>
                          <IconButton size="small" onClick={(e) => { e.stopPropagation(); copyRow(row); }}
                            sx={{ opacity: 0.4, color: GH.textMuted, "&:hover": { opacity: 1 } }}>
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
                PaperProps={{ sx: { borderRadius: 2, background: GH.card, color: GH.text, border: `1px solid ${GH.border}` } }}>
                <DialogTitle sx={{ fontWeight: 700, pb: 1, color: "#fff" }}>
                  <Stack direction="row" alignItems="center" justifyContent="space-between">
                    <span>
                      {t(`admin.tables.${activeTable}`)}
                      <Typography component="span" variant="body2" sx={{ ml: 1, color: GH.textMuted }}>
                        #{selectedRow?.id}
                      </Typography>
                    </span>
                    {activeTable === "medical_records" && !rowEditMode && (
                      <Button size="small" startIcon={<EditOutlinedIcon fontSize="small" />} sx={{ color: GH.blue }}
                        onClick={() => {
                          const init = {};
                          RECORD_EDIT_FIELDS.forEach(({ key }) => { init[key] = selectedRow?.[key] || ""; });
                          setRowEditForm(init);
                          setRowEditMode(true);
                        }}>{"\u7f16\u8f91"}</Button>
                    )}
                  </Stack>
                </DialogTitle>
                <DialogContent dividers sx={{ borderColor: GH.border }}>
                  {rowEditMode ? (
                    <Stack spacing={2}>
                      {RECORD_EDIT_FIELDS.map(({ key, label }) => (
                        <TextField key={key} label={label} multiline minRows={2} maxRows={8} size="small" fullWidth
                          value={rowEditForm[key] || ""}
                          onChange={(e) => setRowEditForm((f) => ({ ...f, [key]: e.target.value }))}
                          sx={darkTextField} />
                      ))}
                    </Stack>
                  ) : (
                    <Stack spacing={0}>
                      {selectedRow && Object.entries(selectedRow).map(([key, value]) => (
                        <Box key={key} sx={{ display: "flex", borderBottom: `1px solid ${GH.border}`, py: 0.8 }}>
                          <Typography variant="caption" sx={{ fontWeight: 700, color: GH.textMuted, width: 180, flexShrink: 0, pt: 0.1 }}>
                            {t(`admin.cols.${key}`)}
                          </Typography>
                          <Typography variant="body2" sx={{ fontFamily: "ui-monospace, monospace", fontSize: TYPE.caption.fontSize, whiteSpace: "pre-wrap", wordBreak: "break-all", flex: 1, color: GH.text }}>
                            {toCell(value)}
                          </Typography>
                        </Box>
                      ))}
                    </Stack>
                  )}
                </DialogContent>
                <DialogActions sx={{ borderTop: `1px solid ${GH.border}` }}>
                  {rowEditMode ? (
                    <>
                      <Button onClick={() => setRowEditMode(false)} disabled={rowSaving} sx={{ color: GH.textMuted }}>{"\u53d6\u6d88"}</Button>
                      <Button variant="contained" onClick={saveRowEdit} disabled={rowSaving} sx={darkBtnContained}>
                        {rowSaving ? "\u4fdd\u5b58\u4e2d\u2026" : "\u4fdd\u5b58"}
                      </Button>
                    </>
                  ) : (
                    <Button onClick={() => setSelectedRow(null)} sx={{ color: GH.textMuted }}>{"\u5173\u95ed"}</Button>
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
      <AdminRelatedDialog
        type={relatedType}
        id={relatedId}
        open={relatedOpen}
        onClose={() => setRelatedOpen(false)}
      />
      <QRDialog open={adminQrOpen} onClose={() => setAdminQrOpen(false)}
        title={"\u533b\u751f\u4e8c\u7ef4\u7801"} name={adminQrName} url={adminQrUrl}
        loading={adminQrLoading} error={adminQrError}
        onRegenerate={() => handleAdminQR(adminQrDoctorId, adminQrName)} />
    </Box>
  );
}
