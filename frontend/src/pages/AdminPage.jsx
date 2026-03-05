import { useEffect, useMemo, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Container,
  Divider,
  IconButton,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
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
import { clearAdminObservabilityTraces, getAdminObservability, getAdminTableRows, getAdminTables, seedAdminObservabilitySamples } from "../api";
import { t } from "../i18n";

const TABLES = [
  { key: "patients", icon: <PeopleOutlineOutlinedIcon fontSize="small" /> },
  { key: "medical_records", icon: <DescriptionOutlinedIcon fontSize="small" /> },
  { key: "doctor_tasks", icon: <AssignmentOutlinedIcon fontSize="small" /> },
  { key: "neuro_cases", icon: <PsychologyAltOutlinedIcon fontSize="small" /> },
  { key: "patient_labels", icon: <LabelOutlinedIcon fontSize="small" /> },
  { key: "patient_label_assignments", icon: <LinkOutlinedIcon fontSize="small" /> },
  { key: "system_prompts", icon: <TextSnippetOutlinedIcon fontSize="small" /> },
  { key: "doctor_contexts", icon: <AccountTreeOutlinedIcon fontSize="small" /> },
];
const NAV_TABS = [...TABLES, { key: "observability", icon: <StorageOutlinedIcon fontSize="small" /> }];

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

function toCell(value) {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function formatMs(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return "-";
  return `${n.toFixed(1)} ms`;
}

function percentile(values, ratio) {
  if (!values.length) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const idx = Math.floor((sorted.length - 1) * ratio);
  return sorted[idx];
}

function ScopeButton({ active, onClick, children }) {
  return (
    <Button variant={active ? "contained" : "outlined"} size="small" onClick={onClick} sx={{ minWidth: 86 }}>
      {children}
    </Button>
  );
}

function LatencyTrendChart({ traces }) {
  const points = (traces || []).slice().reverse().map((row, i) => ({ x: i, y: Number(row.latency_ms) || 0 }));
  const width = 420;
  const height = 140;
  const padding = 14;
  const maxY = Math.max(1, ...points.map((p) => p.y));
  const toX = (x) => padding + (points.length <= 1 ? 0 : (x / (points.length - 1)) * (width - padding * 2));
  const toY = (y) => height - padding - (y / maxY) * (height - padding * 2);
  const polyline = points.map((p) => `${toX(p.x)},${toY(p.y)}`).join(" ");
  return (
    <Box>
      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.6 }}>{t("admin.obs.latencyTrendTitle")}</Typography>
      <Box sx={{ border: "1px solid #d8e3e8", borderRadius: 1, background: "#fff", p: 0.6 }}>
        <svg viewBox={`0 0 ${width} ${height}`} width="100%" height="140" role="img" aria-label="latency-trend">
          <line x1={padding} y1={height - padding} x2={width - padding} y2={height - padding} stroke="#c6d7de" strokeWidth="1" />
          <line x1={padding} y1={padding} x2={padding} y2={height - padding} stroke="#c6d7de" strokeWidth="1" />
          {polyline ? <polyline fill="none" stroke="#0f766e" strokeWidth="2" points={polyline} /> : null}
        </svg>
      </Box>
    </Box>
  );
}

function PerPathBarChart({ perPath }) {
  const items = Object.entries(perPath || {})
    .map(([path, val]) => ({ path, avg: Number(val.avg_ms) || 0 }))
    .sort((a, b) => b.avg - a.avg)
    .slice(0, 6);
  const max = Math.max(1, ...items.map((i) => i.avg));
  return (
    <Box>
      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.6 }}>{t("admin.obs.perPathTitle")}</Typography>
      <Box sx={{ border: "1px solid #d8e3e8", borderRadius: 1, background: "#fff", p: 1 }}>
        <Stack spacing={0.6}>
          {items.map((item) => (
            <Box key={`path-bar-${item.path}`}>
              <Stack direction="row" justifyContent="space-between" sx={{ mb: 0.2 }}>
                <Typography variant="caption" sx={{ maxWidth: "75%", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{item.path}</Typography>
                <Typography variant="caption">{formatMs(item.avg)}</Typography>
              </Stack>
              <Box sx={{ height: 8, borderRadius: 8, backgroundColor: "#e7f1f4", overflow: "hidden" }}>
                <Box sx={{ width: `${(item.avg / max) * 100}%`, height: "100%", backgroundColor: "#0f766e" }} />
              </Box>
            </Box>
          ))}
          {!items.length ? <Typography color="text.secondary" variant="body2">{t("admin.obs.empty")}</Typography> : null}
        </Stack>
      </Box>
    </Box>
  );
}

function StatusBarChart({ statusCounts }) {
  const items = Object.entries(statusCounts || {}).sort((a, b) => Number(a[0]) - Number(b[0]));
  const total = Math.max(1, items.reduce((n, [, c]) => n + (Number(c) || 0), 0));
  return (
    <Box>
      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.6 }}>{t("admin.obs.statusTitle")}</Typography>
      <Box sx={{ border: "1px solid #d8e3e8", borderRadius: 1, background: "#fff", p: 1 }}>
        <Stack spacing={0.6}>
          {items.map(([code, count]) => (
            <Box key={`status-bar-${code}`}>
              <Stack direction="row" justifyContent="space-between" sx={{ mb: 0.2 }}>
                <Typography variant="caption">{code}</Typography>
                <Typography variant="caption">{count}</Typography>
              </Stack>
              <Box sx={{ height: 8, borderRadius: 8, backgroundColor: "#eef4f6", overflow: "hidden" }}>
                <Box sx={{ width: `${(Number(count) / total) * 100}%`, height: "100%", backgroundColor: Number(code) >= 500 ? "#dc2626" : Number(code) >= 400 ? "#f59e0b" : "#0891b2" }} />
              </Box>
            </Box>
          ))}
          {!items.length ? <Typography color="text.secondary" variant="body2">{t("admin.obs.empty")}</Typography> : null}
        </Stack>
      </Box>
    </Box>
  );
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
  const [doctorId, setDoctorId] = useState("");
  const [patientName, setPatientName] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [activeTable, setActiveTable] = useState("patients");
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState({ type: "info", text: "" });
  const [tableCounts, setTableCounts] = useState({});
  const [rows, setRows] = useState([]);
  const [traceIdQuery, setTraceIdQuery] = useState("");
  const [traceScope, setTraceScope] = useState("public");
  const [observability, setObservability] = useState({
    summary: {},
    recent_traces: [],
    recent_spans: [],
    slow_spans: [],
    trace_timeline: [],
  });
  const chatTraceRows = (observability.recent_traces || []).filter((row) => row.path === "/api/records/chat");
  const chatLatencies = chatTraceRows.map((row) => Number(row.latency_ms) || 0);
  const chatTraceIds = new Set(chatTraceRows.map((row) => row.trace_id));
  const chatSlowSpans = (observability.slow_spans || [])
    .filter((row) => chatTraceIds.has(row.trace_id))
    .slice(0, 5);
  const chatQuickStats = {
    count: chatLatencies.length,
    avg: chatLatencies.length ? chatLatencies.reduce((a, b) => a + b, 0) / chatLatencies.length : 0,
    p50: percentile(chatLatencies, 0.5),
    p95: percentile(chatLatencies, 0.95),
    p99: percentile(chatLatencies, 0.99),
    max: chatLatencies.length ? Math.max(...chatLatencies) : 0,
  };
  const traceHotspots = (() => {
    const map = new Map();
    for (const row of observability.trace_timeline || []) {
      const key = `${row.layer || "unknown"}::${row.name || "unknown"}`;
      const prev = map.get(key) || { layer: row.layer, name: row.name, count: 0, total: 0, max: 0 };
      const lat = Number(row.latency_ms) || 0;
      prev.count += 1;
      prev.total += lat;
      prev.max = Math.max(prev.max, lat);
      map.set(key, prev);
    }
    return [...map.values()]
      .map((v) => ({ ...v, avg: v.count ? v.total / v.count : 0 }))
      .sort((a, b) => b.total - a.total)
      .slice(0, 8);
  })();

  async function inspectTrace(traceId) {
    if (!traceId) return;
    setTraceIdQuery(traceId);
    await loadObservability(traceId);
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
  const colCount = columns.length + 1;

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

  async function loadTableList() {
    const data = await getAdminTables({
      doctorId: doctorId.trim(),
      patientName: patientName.trim(),
      dateFrom,
      dateTo,
    });
    const next = {};
    for (const item of data.items || []) {
      next[item.key] = item.count;
    }
    setTableCounts(next);
  }

  async function loadTableData(tableKey = activeTable) {
    if (tableKey === "observability") {
      setRows([]);
      return;
    }
    const data = await getAdminTableRows({
      tableKey,
      doctorId: doctorId.trim(),
      patientName: patientName.trim(),
      dateFrom,
      dateTo,
      limit: 300,
    });
    setRows(data.items || []);
  }

  async function loadObservability(overrideTraceId = null) {
    const effectiveTraceId = overrideTraceId !== null ? overrideTraceId : traceIdQuery.trim();
    const data = await getAdminObservability({
      traceLimit: 80,
      summaryLimit: 500,
      spanLimit: 300,
      slowSpanLimit: 30,
      scope: traceScope,
      traceId: effectiveTraceId,
    });
    setObservability({
      summary: data.summary || {},
      recent_traces: data.recent_traces || [],
      recent_spans: data.recent_spans || [],
      slow_spans: data.slow_spans || [],
      trace_timeline: data.trace_timeline || [],
    });
  }

  async function clearObservability() {
    try {
      await clearAdminObservabilityTraces();
      await loadObservability();
      setStatus({ type: "success", text: t("admin.obs.clearSuccess") });
    } catch (error) {
      setStatus({ type: "error", text: t("admin.obs.clearFailed", { message: error.message }) });
    }
  }

  async function seedObservabilitySamples(count = 6) {
    try {
      const payload = await seedAdminObservabilitySamples(count);
      await loadObservability();
      setStatus({ type: "success", text: t("admin.obs.seedSuccess", { count: payload.count || count }) });
    } catch (error) {
      setStatus({ type: "error", text: t("admin.obs.seedFailed", { message: error.message }) });
    }
  }


  async function loadAll(tableKey = activeTable) {
    setLoading(true);
    setStatus({ type: "info", text: "" });
    try {
      if (tableKey === "observability") {
        await Promise.all([loadTableList(), loadObservability()]);
      } else {
        await Promise.all([loadTableList(), loadTableData(tableKey)]);
      }
    } catch (error) {
      setStatus({ type: "error", text: t("admin.loadFailed", { message: error.message }) });
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadAll("patients");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (activeTable === "observability") {
      loadObservability();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [traceScope]);

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
                <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>{t("admin.pageTitle")}</Typography>
                <Typography variant="caption" color="text.secondary" sx={{ mt: 0.2, display: "block" }}>
                  {t("admin.pageSubtitle")}
                </Typography>
                <TextField size="small" label={t("admin.filters.doctorName")} value={doctorId} onChange={(e) => setDoctorId(e.target.value)} sx={{ mt: 1 }} fullWidth />
                <TextField size="small" label={t("admin.filters.patientName")} value={patientName} onChange={(e) => setPatientName(e.target.value)} sx={{ mt: 1 }} fullWidth />
                <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
                  <TextField size="small" type="date" label={t("admin.filters.dateFrom")} InputLabelProps={{ shrink: true }} value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} fullWidth />
                  <TextField size="small" type="date" label={t("admin.filters.dateTo")} InputLabelProps={{ shrink: true }} value={dateTo} onChange={(e) => setDateTo(e.target.value)} fullWidth />
                </Stack>
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
                      onClick={() => {
                        setActiveTable(item.key);
                        loadAll(item.key);
                      }}
                    >
                      {t(`admin.tables.${item.key}`)}
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
                {activeTable === "observability" ? (
                  <Button variant="contained" size="small" onClick={loadObservability} disabled={loading}>
                    {loading ? t("common.loading") : t("admin.obs.reload")}
                  </Button>
                ) : (
                  <Stack direction="row" spacing={0.8}>
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

              {activeTable === "observability" ? (
                <Box sx={{ border: "1px solid #d8e3e8", borderRadius: 1.5, backgroundColor: "#f8fbfc", p: 1.2, mb: 1.2 }}>
                <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
                  <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>{t("admin.obs.title")}</Typography>
                  <Stack direction="row" spacing={0.8}>
                    <Button variant="outlined" size="small" onClick={() => seedObservabilitySamples(6)}>{t("admin.obs.seed")}</Button>
                    <Button variant="outlined" size="small" onClick={loadObservability}>{t("admin.obs.reload")}</Button>
                    <Button variant="outlined" color="error" size="small" onClick={clearObservability}>{t("admin.obs.clear")}</Button>
                  </Stack>
                </Stack>
                <Stack direction="row" spacing={0.8} sx={{ mb: 1 }}>
                  <ScopeButton active={traceScope === "public"} onClick={() => { setTraceScope("public"); }}>{t("admin.obs.scopePublic")}</ScopeButton>
                  <ScopeButton active={traceScope === "internal"} onClick={() => { setTraceScope("internal"); }}>{t("admin.obs.scopeInternal")}</ScopeButton>
                  <ScopeButton active={traceScope === "all"} onClick={() => { setTraceScope("all"); }}>{t("admin.obs.scopeAll")}</ScopeButton>
                </Stack>
                <Stack direction="row" spacing={1} sx={{ mb: 1.2 }}>
                  <TextField
                    size="small"
                    fullWidth
                    label={t("admin.obs.traceId")}
                    value={traceIdQuery}
                    onChange={(e) => setTraceIdQuery(e.target.value)}
                  />
                  <Button variant="outlined" size="small" onClick={loadObservability}>{t("admin.obs.filter")}</Button>
                </Stack>
                <Box sx={{ border: "1px solid #d8e3e8", borderRadius: 1, backgroundColor: "#fff", p: 1, mb: 1 }}>
                  <Box sx={{ display: "grid", gap: 0.8, gridTemplateColumns: { xs: "repeat(2, minmax(0,1fr))", md: "repeat(6, minmax(0,1fr))" } }}>
                    <Box sx={{ p: 0.8, borderRadius: 1, backgroundColor: "#eef4f6" }}>
                      <Typography variant="caption" color="text.secondary">{t("admin.obs.count")}</Typography>
                      <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>{toCell(observability.summary.count)}</Typography>
                    </Box>
                    <Box sx={{ p: 0.8, borderRadius: 1, backgroundColor: "#eef4f6" }}>
                      <Typography variant="caption" color="text.secondary">{t("admin.obs.avg")}</Typography>
                      <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>{formatMs(observability.summary.avg_ms)}</Typography>
                    </Box>
                    <Box sx={{ p: 0.8, borderRadius: 1, backgroundColor: "#eef4f6" }}>
                      <Typography variant="caption" color="text.secondary">{t("admin.obs.p95")}</Typography>
                      <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>{formatMs(observability.summary.p95_ms)}</Typography>
                    </Box>
                    <Box sx={{ p: 0.8, borderRadius: 1, backgroundColor: "#eef4f6" }}>
                      <Typography variant="caption" color="text.secondary">{t("admin.obs.p99")}</Typography>
                      <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>{formatMs(observability.summary.p99_ms)}</Typography>
                    </Box>
                    <Box sx={{ p: 0.8, borderRadius: 1, backgroundColor: "#eef4f6" }}>
                      <Typography variant="caption" color="text.secondary">{t("admin.obs.max")}</Typography>
                      <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>{formatMs(observability.summary.max_ms)}</Typography>
                    </Box>
                    <Box sx={{ p: 0.8, borderRadius: 1, backgroundColor: "#eef4f6" }}>
                      <Typography variant="caption" color="text.secondary">{t("admin.obs.traces")}</Typography>
                      <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>{toCell((observability.recent_traces || []).length)}</Typography>
                    </Box>
                  </Box>
                </Box>
                <Box sx={{ display: "grid", gap: 1, gridTemplateColumns: { xs: "1fr", lg: "minmax(0,1.2fr) minmax(0,1fr) minmax(0,1fr)" }, mb: 1 }}>
                  <LatencyTrendChart traces={observability.recent_traces} />
                  <PerPathBarChart perPath={observability.summary.per_path || {}} />
                  <StatusBarChart statusCounts={observability.summary.status_counts || {}} />
                </Box>
                <Box sx={{ border: "1px solid #d8e3e8", borderRadius: 1, backgroundColor: "#fff", p: 1, mb: 1 }}>
                  <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.8 }}>{t("admin.obs.publicQuickTitle")}</Typography>
                  <Box sx={{ display: "grid", gap: 0.8, gridTemplateColumns: { xs: "repeat(2, minmax(0,1fr))", md: "repeat(6, minmax(0,1fr))" }, mb: 0.9 }}>
                    <Box sx={{ p: 0.8, borderRadius: 1, backgroundColor: "#eef4f6" }}>
                      <Typography variant="caption" color="text.secondary">{t("admin.obs.count")}</Typography>
                      <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>{chatQuickStats.count}</Typography>
                    </Box>
                    <Box sx={{ p: 0.8, borderRadius: 1, backgroundColor: "#eef4f6" }}>
                      <Typography variant="caption" color="text.secondary">{t("admin.obs.avg")}</Typography>
                      <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>{formatMs(chatQuickStats.avg)}</Typography>
                    </Box>
                    <Box sx={{ p: 0.8, borderRadius: 1, backgroundColor: "#eef4f6" }}>
                      <Typography variant="caption" color="text.secondary">P50</Typography>
                      <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>{formatMs(chatQuickStats.p50)}</Typography>
                    </Box>
                    <Box sx={{ p: 0.8, borderRadius: 1, backgroundColor: "#eef4f6" }}>
                      <Typography variant="caption" color="text.secondary">{t("admin.obs.p95")}</Typography>
                      <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>{formatMs(chatQuickStats.p95)}</Typography>
                    </Box>
                    <Box sx={{ p: 0.8, borderRadius: 1, backgroundColor: "#eef4f6" }}>
                      <Typography variant="caption" color="text.secondary">{t("admin.obs.p99")}</Typography>
                      <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>{formatMs(chatQuickStats.p99)}</Typography>
                    </Box>
                    <Box sx={{ p: 0.8, borderRadius: 1, backgroundColor: "#eef4f6" }}>
                      <Typography variant="caption" color="text.secondary">{t("admin.obs.max")}</Typography>
                      <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>{formatMs(chatQuickStats.max)}</Typography>
                    </Box>
                  </Box>
                  <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>{t("admin.obs.publicSlowSpansTitle")}</Typography>
                  <TableContainer sx={{ border: "1px solid #d8e3e8", borderRadius: 1, backgroundColor: "#fff", maxHeight: 180 }}>
                    <Table size="small" stickyHeader>
                      <TableHead>
                        <TableRow>
                          {["layer", "name", "latency_ms", "trace_id"].map((key) => (
                            <TableCell key={`quick-head-${key}`} sx={{ backgroundColor: "#eef4f6", py: 0.45, fontSize: 11, fontWeight: 700 }}>
                              {t(`admin.cols.${key}`)}
                            </TableCell>
                          ))}
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {chatSlowSpans.map((row, idx) => (
                          <TableRow key={`quick-row-${row.span_id || idx}`} hover>
                            <TableCell sx={{ py: 0.35, fontSize: 11 }}>{toCell(row.layer)}</TableCell>
                            <TableCell sx={{ py: 0.35, fontSize: 11 }}>{toCell(row.name)}</TableCell>
                            <TableCell sx={{ py: 0.35, fontSize: 11 }}>{formatMs(row.latency_ms)}</TableCell>
                            <TableCell sx={{ py: 0.35, fontSize: 11, fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, Liberation Mono, monospace", maxWidth: 130, wordBreak: "break-all" }}>{toCell(row.trace_id)}</TableCell>
                          </TableRow>
                        ))}
                        {!chatSlowSpans.length ? (
                          <TableRow>
                            <TableCell colSpan={4} sx={{ py: 0.9 }}>
                              <Typography color="text.secondary" variant="body2">{t("admin.obs.publicHint")}</Typography>
                            </TableCell>
                          </TableRow>
                        ) : null}
                      </TableBody>
                    </Table>
                  </TableContainer>
                </Box>
                <Box sx={{ border: "1px solid #d8e3e8", borderRadius: 1, backgroundColor: "#fff", p: 1, mb: 1 }}>
                  <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.8 }}>{t("admin.obs.recentTracesTitle")}</Typography>
                  <TableContainer sx={{ border: "1px solid #d8e3e8", borderRadius: 1, backgroundColor: "#fff", maxHeight: 220 }}>
                    <Table size="small" stickyHeader>
                      <TableHead>
                        <TableRow>
                          {["started_at", "trace_id", "method", "path", "status_code", "latency_ms"].map((key) => (
                            <TableCell key={`obs-head-${key}`} sx={{ backgroundColor: "#eef4f6", py: 0.55, fontSize: 11, fontWeight: 700 }}>
                              {t(`admin.cols.${key}`)}
                            </TableCell>
                          ))}
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {(observability.recent_traces || []).map((row, idx) => (
                          <TableRow key={`obs-row-${row.trace_id || idx}`} hover>
                            <TableCell sx={{ py: 0.4, fontSize: 11 }}>{toCell(row.started_at)}</TableCell>
                            <TableCell sx={{ py: 0.4, fontSize: 11, fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, Liberation Mono, monospace" }}>
                              <Button size="small" variant="text" sx={{ textTransform: "none", p: 0, minWidth: 0 }} onClick={() => inspectTrace(row.trace_id)}>
                                {toCell(row.trace_id)}
                              </Button>
                            </TableCell>
                            <TableCell sx={{ py: 0.4, fontSize: 11 }}>{toCell(row.method)}</TableCell>
                            <TableCell sx={{ py: 0.4, fontSize: 11, maxWidth: 260, wordBreak: "break-all" }}>{toCell(row.path)}</TableCell>
                            <TableCell sx={{ py: 0.4, fontSize: 11 }}>{toCell(row.status_code)}</TableCell>
                            <TableCell sx={{ py: 0.4, fontSize: 11 }}>{formatMs(row.latency_ms)}</TableCell>
                          </TableRow>
                        ))}
                        {!(observability.recent_traces || []).length ? (
                          <TableRow>
                            <TableCell colSpan={6} sx={{ py: 0.9 }}>
                              <Typography color="text.secondary" variant="body2">{t("admin.obs.empty")}</Typography>
                            </TableCell>
                          </TableRow>
                        ) : null}
                      </TableBody>
                    </Table>
                  </TableContainer>
                </Box>
                <Box sx={{ border: "1px solid #d8e3e8", borderRadius: 1, backgroundColor: "#fff", p: 1, mb: 1 }}>
                  <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.8 }}>{t("admin.obs.slowSpansTitle")}</Typography>
                  <TableContainer sx={{ border: "1px solid #d8e3e8", borderRadius: 1, backgroundColor: "#fff", maxHeight: 320 }}>
                    <Table size="small" stickyHeader>
                      <TableHead>
                        <TableRow>
                          {["layer", "name", "latency_ms", "status", "trace_id"].map((key) => (
                            <TableCell key={`slow-head-${key}`} sx={{ backgroundColor: "#eef4f6", py: 0.55, fontSize: 11, fontWeight: 700 }}>
                              {t(`admin.cols.${key}`)}
                            </TableCell>
                          ))}
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {(observability.slow_spans || []).map((row, idx) => (
                          <TableRow key={`slow-row-${row.span_id || idx}`} hover>
                            <TableCell sx={{ py: 0.4, fontSize: 11 }}>{toCell(row.layer)}</TableCell>
                            <TableCell sx={{ py: 0.4, fontSize: 11 }}>{toCell(row.name)}</TableCell>
                            <TableCell sx={{ py: 0.4, fontSize: 11 }}>{formatMs(row.latency_ms)}</TableCell>
                            <TableCell sx={{ py: 0.4, fontSize: 11 }}>{toCell(row.status)}</TableCell>
                            <TableCell sx={{ py: 0.4, fontSize: 11, fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, Liberation Mono, monospace", maxWidth: 140, wordBreak: "break-all" }}>
                              <Button size="small" variant="text" sx={{ textTransform: "none", p: 0, minWidth: 0 }} onClick={() => inspectTrace(row.trace_id)}>
                                {toCell(row.trace_id)}
                              </Button>
                            </TableCell>
                          </TableRow>
                        ))}
                        {!(observability.slow_spans || []).length ? (
                          <TableRow>
                            <TableCell colSpan={5} sx={{ py: 0.9 }}>
                              <Typography color="text.secondary" variant="body2">{t("admin.obs.empty")}</Typography>
                            </TableCell>
                          </TableRow>
                        ) : null}
                      </TableBody>
                    </Table>
                  </TableContainer>
                </Box>
                <Box sx={{ border: "1px solid #d8e3e8", borderRadius: 1, backgroundColor: "#fff", p: 1, mb: 1 }}>
                  <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.8 }}>{t("admin.obs.timelineTitle")}</Typography>
                  {!!(observability.trace_timeline || []).length ? (
                    <TableContainer sx={{ border: "1px solid #d8e3e8", borderRadius: 1, backgroundColor: "#fff", maxHeight: 210, mb: 0.8 }}>
                      <Table size="small" stickyHeader>
                        <TableHead>
                          <TableRow>
                            {["layer", "name", "latency_ms", "count"].map((key) => (
                              <TableCell key={`hotspot-head-${key}`} sx={{ backgroundColor: "#eef4f6", py: 0.45, fontSize: 11, fontWeight: 700 }}>
                                {t(`admin.cols.${key}`)}
                              </TableCell>
                            ))}
                          </TableRow>
                        </TableHead>
                        <TableBody>
                          {traceHotspots.map((row, idx) => (
                            <TableRow key={`hotspot-row-${idx}`} hover>
                              <TableCell sx={{ py: 0.35, fontSize: 11 }}>{toCell(row.layer)}</TableCell>
                              <TableCell sx={{ py: 0.35, fontSize: 11 }}>{toCell(row.name)}</TableCell>
                              <TableCell sx={{ py: 0.35, fontSize: 11 }}>{formatMs(row.total)}</TableCell>
                              <TableCell sx={{ py: 0.35, fontSize: 11 }}>{toCell(row.count)}</TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </TableContainer>
                  ) : null}
                  <TableContainer sx={{ border: "1px solid #d8e3e8", borderRadius: 1, backgroundColor: "#fff", maxHeight: 460 }}>
                    <Table size="small" stickyHeader>
                      <TableHead>
                        <TableRow>
                          {["started_at", "layer", "name", "latency_ms", "status", "parent_span_id"].map((key) => (
                            <TableCell key={`timeline-head-${key}`} sx={{ backgroundColor: "#eef4f6", py: 0.55, fontSize: 11, fontWeight: 700 }}>
                              {t(`admin.cols.${key}`)}
                            </TableCell>
                          ))}
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {(observability.trace_timeline || []).map((row, idx) => (
                          <TableRow key={`timeline-row-${row.span_id || idx}`} hover>
                            <TableCell sx={{ py: 0.4, fontSize: 11 }}>{toCell(row.started_at)}</TableCell>
                            <TableCell sx={{ py: 0.4, fontSize: 11 }}>{toCell(row.layer)}</TableCell>
                            <TableCell sx={{ py: 0.4, fontSize: 11 }}>{toCell(row.name)}</TableCell>
                            <TableCell sx={{ py: 0.4, fontSize: 11 }}>{formatMs(row.latency_ms)}</TableCell>
                            <TableCell sx={{ py: 0.4, fontSize: 11 }}>{toCell(row.status)}</TableCell>
                            <TableCell sx={{ py: 0.4, fontSize: 11, fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, Liberation Mono, monospace", maxWidth: 120, wordBreak: "break-all" }}>{toCell(row.parent_span_id)}</TableCell>
                          </TableRow>
                        ))}
                        {!(observability.trace_timeline || []).length ? (
                          <TableRow>
                            <TableCell colSpan={6} sx={{ py: 0.9 }}>
                              <Typography color="text.secondary" variant="body2">{t("admin.obs.timelineHint")}</Typography>
                            </TableCell>
                          </TableRow>
                        ) : null}
                      </TableBody>
                    </Table>
                  </TableContainer>
                </Box>
                </Box>
              ) : (
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
                            }}
                          >
                            {t(`admin.cols.${key}`)}
                          </TableCell>
                        ))}
                        <TableCell sx={{ width: 56, maxWidth: 56, backgroundColor: "#eef4f6", px: 0.5, py: 0.75 }} />
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {rows.map((row, rowIdx) => (
                        <TableRow key={`row-${row.id ?? row.key ?? rowIdx}`} hover>
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
                                whiteSpace: "pre-wrap",
                                wordBreak: "break-word",
                              }}
                            >
                              {toCell(row[key])}
                            </TableCell>
                          ))}
                          <TableCell sx={{ py: 0.2, px: 0.2, borderBottom: "1px solid #e4edf0", verticalAlign: "top" }}>
                            <IconButton size="small" onClick={() => copyRow(row)} title={t("admin.copyRow")}>
                              <ContentCopyOutlinedIcon sx={{ fontSize: 15 }} />
                            </IconButton>
                          </TableCell>
                        </TableRow>
                      ))}
                      {!rows.length ? (
                        <TableRow>
                          <TableCell colSpan={colCount} sx={{ py: 1.2 }}>
                            <Typography color="text.secondary">{t("admin.empty")}</Typography>
                          </TableCell>
                        </TableRow>
                      ) : null}
                    </TableBody>
                  </Table>
                </TableContainer>
              )}
            </CardContent>
          </Card>
        </Box>
      </Container>
    </Box>
  );
}
