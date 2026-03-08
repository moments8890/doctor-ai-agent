import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Container,
  MenuItem,
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
import BugReportOutlinedIcon from "@mui/icons-material/BugReportOutlined";
import SpeedOutlinedIcon from "@mui/icons-material/SpeedOutlined";
import ArticleOutlinedIcon from "@mui/icons-material/ArticleOutlined";
import StorageOutlinedIcon from "@mui/icons-material/StorageOutlined";
import {
  getDebugRoutingMetrics,
  resetDebugRoutingMetrics,
  getDebugLogs,
  getDebugObservability,
  clearDebugObservabilityTraces,
  seedDebugObservabilitySamples,
  setDebugToken,
  onDebugAuthError,
} from "../api";
import { t } from "../i18n";

const DEBUG_TOKEN_KEY = "debugToken";

const NAV_SECTIONS = [
  { key: "metrics", label: "路由指标", icon: <SpeedOutlinedIcon fontSize="small" /> },
  { key: "observability", label: "可观测性", icon: <StorageOutlinedIcon fontSize="small" /> },
  { key: "logs", label: "日志查看器", icon: <ArticleOutlinedIcon fontSize="small" /> },
];

function TokenGate({ onUnlock }) {
  const [input, setInput] = useState("");
  const [error, setError] = useState("");
  function handleSubmit(e) {
    e.preventDefault();
    const token = input.trim();
    if (!token) { setError("请输入 Token"); return; }
    localStorage.setItem(DEBUG_TOKEN_KEY, token);
    setDebugToken(token);
    onUnlock(token);
  }
  return (
    <Box sx={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", background: "#f3f7f8" }}>
      <Card sx={{ width: 360, borderRadius: 2 }}>
        <CardContent sx={{ p: 3 }}>
          <Typography variant="h6" sx={{ mb: 0.5, fontWeight: 700 }}>Debug 访问</Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2.5 }}>请输入 UI_DEBUG_TOKEN 以继续</Typography>
          <form onSubmit={handleSubmit}>
            <Stack spacing={2}>
              <TextField label="Debug Token" type="password" size="small" fullWidth autoFocus value={input} onChange={(e) => { setInput(e.target.value); setError(""); }} error={!!error} helperText={error} />
              <Button type="submit" variant="contained" fullWidth>进入</Button>
            </Stack>
          </form>
        </CardContent>
      </Card>
    </Box>
  );
}

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

// ─── Helpers ─────────────────────────────────────────────────────────────────

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

function toCell(value) {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
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
  const width = 420; const height = 140; const padding = 14;
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
  const items = Object.entries(perPath || {}).map(([path, val]) => ({ path, avg: Number(val.avg_ms) || 0 })).sort((a, b) => b.avg - a.avg).slice(0, 6);
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

// ─── Sections ─────────────────────────────────────────────────────────────────

function MetricsSection() {
  const [metrics, setMetrics] = useState(null);
  const [status, setStatus] = useState({ type: "info", text: "" });
  const [loading, setLoading] = useState(false);

  async function load() {
    setLoading(true);
    try {
      setMetrics(await getDebugRoutingMetrics());
      setStatus({ type: "info", text: "" });
    } catch (err) {
      setStatus({ type: "error", text: `加载失败：${err.message}` });
    } finally {
      setLoading(false);
    }
  }

  async function handleReset() {
    try {
      await resetDebugRoutingMetrics();
      await load();
      setStatus({ type: "success", text: "路由指标已重置。" });
    } catch (err) {
      setStatus({ type: "error", text: `重置失败：${err.message}` });
    }
  }

  useEffect(() => { load(); }, []);

  const total = metrics ? (Number(metrics.fast_route || 0) + Number(metrics.llm_route || 0)) : 0;
  const fastPct = total ? ((Number(metrics.fast_route || 0) / total) * 100).toFixed(1) : "-";

  return (
    <Box>
      <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 1.2 }}>
        <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>路由指标</Typography>
        <Stack direction="row" spacing={0.8}>
          <Button size="small" variant="outlined" onClick={load} disabled={loading}>{loading ? "加载中..." : "刷新"}</Button>
          <Button size="small" variant="outlined" color="error" onClick={handleReset} disabled={loading}>重置</Button>
        </Stack>
      </Stack>
      {!!status.text && <Alert severity={status.type} sx={{ mb: 1.5 }}>{status.text}</Alert>}
      {metrics ? (
        <Box sx={{ display: "grid", gap: 1, gridTemplateColumns: { xs: "1fr 1fr", md: "repeat(4, minmax(0,1fr))" } }}>
          {[
            { label: "快速路由命中", value: metrics.fast_route ?? "-", color: "#d1fae5" },
            { label: "LLM路由命中", value: metrics.llm_route ?? "-", color: "#dbeafe" },
            { label: "总计", value: total || "-", color: "#f3f4f6" },
            { label: "快速路由占比", value: total ? `${fastPct}%` : "-", color: "#fef3c7" },
          ].map((item) => (
            <Box key={item.label} sx={{ p: 1.2, borderRadius: 1, backgroundColor: item.color, border: "1px solid #e5e7eb" }}>
              <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>{item.label}</Typography>
              <Typography variant="h5" sx={{ fontWeight: 700, lineHeight: 1.3 }}>{String(item.value)}</Typography>
            </Box>
          ))}
        </Box>
      ) : (
        <Typography variant="body2" color="text.secondary">暂无数据</Typography>
      )}
      {metrics && (
        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1 }}>
          进程启动后累计计数。重置仅影响内存计数器，不影响日志文件。
        </Typography>
      )}
    </Box>
  );
}

function ObservabilitySection() {
  const [traceIdQuery, setTraceIdQuery] = useState("");
  const [traceScope, setTraceScope] = useState("public");
  const [observability, setObservability] = useState({ summary: {}, recent_traces: [], recent_spans: [], slow_spans: [], trace_timeline: [] });
  const [status, setStatus] = useState({ type: "info", text: "" });
  const [loading, setLoading] = useState(false);

  const chatTraceRows = (observability.recent_traces || []).filter((row) => row.path === "/api/records/chat");
  const chatLatencies = chatTraceRows.map((row) => Number(row.latency_ms) || 0);
  const chatTraceIds = new Set(chatTraceRows.map((row) => row.trace_id));
  const chatSlowSpans = (observability.slow_spans || []).filter((row) => chatTraceIds.has(row.trace_id)).slice(0, 5);
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
      prev.count += 1; prev.total += lat; prev.max = Math.max(prev.max, lat);
      map.set(key, prev);
    }
    return [...map.values()].map((v) => ({ ...v, avg: v.count ? v.total / v.count : 0 })).sort((a, b) => b.total - a.total).slice(0, 8);
  })();

  async function load(overrideTraceId = null) {
    setLoading(true);
    try {
      const effectiveTraceId = overrideTraceId !== null ? overrideTraceId : traceIdQuery.trim();
      const data = await getDebugObservability({ traceLimit: 80, summaryLimit: 500, spanLimit: 300, slowSpanLimit: 30, scope: traceScope, traceId: effectiveTraceId });
      setObservability({ summary: data.summary || {}, recent_traces: data.recent_traces || [], recent_spans: data.recent_spans || [], slow_spans: data.slow_spans || [], trace_timeline: data.trace_timeline || [] });
      setStatus({ type: "info", text: "" });
    } catch (err) {
      setStatus({ type: "error", text: `加载失败：${err.message}` });
    } finally {
      setLoading(false);
    }
  }

  async function handleClear() {
    try {
      await clearDebugObservabilityTraces();
      await load();
      setStatus({ type: "success", text: t("admin.obs.clearSuccess") });
    } catch (err) {
      setStatus({ type: "error", text: t("admin.obs.clearFailed", { message: err.message }) });
    }
  }

  async function handleSeed() {
    try {
      const payload = await seedDebugObservabilitySamples(6);
      await load();
      setStatus({ type: "success", text: t("admin.obs.seedSuccess", { count: payload.count || 6 }) });
    } catch (err) {
      setStatus({ type: "error", text: t("admin.obs.seedFailed", { message: err.message }) });
    }
  }

  async function inspectTrace(traceId) {
    if (!traceId) return;
    setTraceIdQuery(traceId);
    await load(traceId);
  }

  useEffect(() => { load(); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, [traceScope]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <Box>
      <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1.2 }}>
        <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>{t("admin.obs.title")}</Typography>
        <Stack direction="row" spacing={0.8}>
          <Button variant="outlined" size="small" onClick={handleSeed}>{t("admin.obs.seed")}</Button>
          <Button variant="outlined" size="small" onClick={() => load()} disabled={loading}>{loading ? "加载中..." : t("admin.obs.reload")}</Button>
          <Button variant="outlined" color="error" size="small" onClick={handleClear}>{t("admin.obs.clear")}</Button>
        </Stack>
      </Stack>
      {!!status.text && <Alert severity={status.type} sx={{ mb: 1.5 }}>{status.text}</Alert>}
      <Stack direction="row" spacing={0.8} sx={{ mb: 1 }}>
        <ScopeButton active={traceScope === "public"} onClick={() => setTraceScope("public")}>{t("admin.obs.scopePublic")}</ScopeButton>
        <ScopeButton active={traceScope === "internal"} onClick={() => setTraceScope("internal")}>{t("admin.obs.scopeInternal")}</ScopeButton>
        <ScopeButton active={traceScope === "all"} onClick={() => setTraceScope("all")}>{t("admin.obs.scopeAll")}</ScopeButton>
      </Stack>
      <Stack direction="row" spacing={1} sx={{ mb: 1.2 }}>
        <TextField size="small" fullWidth label={t("admin.obs.traceId")} value={traceIdQuery} onChange={(e) => setTraceIdQuery(e.target.value)} />
        <Button variant="outlined" size="small" onClick={() => load()}>{t("admin.obs.filter")}</Button>
      </Stack>
      <Box sx={{ border: "1px solid #d8e3e8", borderRadius: 1, backgroundColor: "#fff", p: 1, mb: 1 }}>
        <Box sx={{ display: "grid", gap: 0.8, gridTemplateColumns: { xs: "repeat(2, minmax(0,1fr))", md: "repeat(6, minmax(0,1fr))" } }}>
          {[
            { label: t("admin.obs.count"), value: toCell(observability.summary.count) },
            { label: t("admin.obs.avg"), value: formatMs(observability.summary.avg_ms) },
            { label: t("admin.obs.p95"), value: formatMs(observability.summary.p95_ms) },
            { label: t("admin.obs.p99"), value: formatMs(observability.summary.p99_ms) },
            { label: t("admin.obs.max"), value: formatMs(observability.summary.max_ms) },
            { label: t("admin.obs.traces"), value: toCell((observability.recent_traces || []).length) },
          ].map((item) => (
            <Box key={item.label} sx={{ p: 0.8, borderRadius: 1, backgroundColor: "#eef4f6" }}>
              <Typography variant="caption" color="text.secondary">{item.label}</Typography>
              <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>{item.value}</Typography>
            </Box>
          ))}
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
          {[
            { label: t("admin.obs.count"), value: chatQuickStats.count },
            { label: t("admin.obs.avg"), value: formatMs(chatQuickStats.avg) },
            { label: "P50", value: formatMs(chatQuickStats.p50) },
            { label: t("admin.obs.p95"), value: formatMs(chatQuickStats.p95) },
            { label: t("admin.obs.p99"), value: formatMs(chatQuickStats.p99) },
            { label: t("admin.obs.max"), value: formatMs(chatQuickStats.max) },
          ].map((item) => (
            <Box key={item.label} sx={{ p: 0.8, borderRadius: 1, backgroundColor: "#eef4f6" }}>
              <Typography variant="caption" color="text.secondary">{item.label}</Typography>
              <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>{item.value}</Typography>
            </Box>
          ))}
        </Box>
        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>{t("admin.obs.publicSlowSpansTitle")}</Typography>
        <TableContainer sx={{ border: "1px solid #d8e3e8", borderRadius: 1, backgroundColor: "#fff", maxHeight: 180 }}>
          <Table size="small" stickyHeader>
            <TableHead><TableRow>{["layer", "name", "latency_ms", "trace_id"].map((key) => <TableCell key={`qh-${key}`} sx={{ backgroundColor: "#eef4f6", py: 0.45, fontSize: 11, fontWeight: 700 }}>{t(`admin.cols.${key}`)}</TableCell>)}</TableRow></TableHead>
            <TableBody>
              {chatSlowSpans.map((row, idx) => (
                <TableRow key={`qr-${row.span_id || idx}`} hover>
                  <TableCell sx={{ py: 0.35, fontSize: 11 }}>{toCell(row.layer)}</TableCell>
                  <TableCell sx={{ py: 0.35, fontSize: 11 }}>{toCell(row.name)}</TableCell>
                  <TableCell sx={{ py: 0.35, fontSize: 11 }}>{formatMs(row.latency_ms)}</TableCell>
                  <TableCell sx={{ py: 0.35, fontSize: 11, fontFamily: "ui-monospace,monospace", maxWidth: 130, wordBreak: "break-all" }}>{toCell(row.trace_id)}</TableCell>
                </TableRow>
              ))}
              {!chatSlowSpans.length ? <TableRow><TableCell colSpan={4} sx={{ py: 0.9 }}><Typography color="text.secondary" variant="body2">{t("admin.obs.publicHint")}</Typography></TableCell></TableRow> : null}
            </TableBody>
          </Table>
        </TableContainer>
      </Box>
      <Box sx={{ border: "1px solid #d8e3e8", borderRadius: 1, backgroundColor: "#fff", p: 1, mb: 1 }}>
        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.8 }}>{t("admin.obs.recentTracesTitle")}</Typography>
        <TableContainer sx={{ border: "1px solid #d8e3e8", borderRadius: 1, backgroundColor: "#fff", maxHeight: 220 }}>
          <Table size="small" stickyHeader>
            <TableHead><TableRow>{["started_at", "trace_id", "method", "path", "status_code", "latency_ms"].map((key) => <TableCell key={`oh-${key}`} sx={{ backgroundColor: "#eef4f6", py: 0.55, fontSize: 11, fontWeight: 700 }}>{t(`admin.cols.${key}`)}</TableCell>)}</TableRow></TableHead>
            <TableBody>
              {(observability.recent_traces || []).map((row, idx) => (
                <TableRow key={`or-${row.trace_id || idx}`} hover>
                  <TableCell sx={{ py: 0.4, fontSize: 11 }}>{toCell(row.started_at)}</TableCell>
                  <TableCell sx={{ py: 0.4, fontSize: 11, fontFamily: "ui-monospace,monospace" }}>
                    <Button size="small" variant="text" sx={{ textTransform: "none", p: 0, minWidth: 0 }} onClick={() => inspectTrace(row.trace_id)}>{toCell(row.trace_id)}</Button>
                  </TableCell>
                  <TableCell sx={{ py: 0.4, fontSize: 11 }}>{toCell(row.method)}</TableCell>
                  <TableCell sx={{ py: 0.4, fontSize: 11, maxWidth: 260, wordBreak: "break-all" }}>{toCell(row.path)}</TableCell>
                  <TableCell sx={{ py: 0.4, fontSize: 11 }}>{toCell(row.status_code)}</TableCell>
                  <TableCell sx={{ py: 0.4, fontSize: 11 }}>{formatMs(row.latency_ms)}</TableCell>
                </TableRow>
              ))}
              {!(observability.recent_traces || []).length ? <TableRow><TableCell colSpan={6} sx={{ py: 0.9 }}><Typography color="text.secondary" variant="body2">{t("admin.obs.empty")}</Typography></TableCell></TableRow> : null}
            </TableBody>
          </Table>
        </TableContainer>
      </Box>
      <Box sx={{ border: "1px solid #d8e3e8", borderRadius: 1, backgroundColor: "#fff", p: 1, mb: 1 }}>
        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.8 }}>{t("admin.obs.slowSpansTitle")}</Typography>
        <TableContainer sx={{ border: "1px solid #d8e3e8", borderRadius: 1, backgroundColor: "#fff", maxHeight: 320 }}>
          <Table size="small" stickyHeader>
            <TableHead><TableRow>{["layer", "name", "latency_ms", "status", "trace_id"].map((key) => <TableCell key={`sh-${key}`} sx={{ backgroundColor: "#eef4f6", py: 0.55, fontSize: 11, fontWeight: 700 }}>{t(`admin.cols.${key}`)}</TableCell>)}</TableRow></TableHead>
            <TableBody>
              {(observability.slow_spans || []).map((row, idx) => (
                <TableRow key={`sr-${row.span_id || idx}`} hover>
                  <TableCell sx={{ py: 0.4, fontSize: 11 }}>{toCell(row.layer)}</TableCell>
                  <TableCell sx={{ py: 0.4, fontSize: 11 }}>{toCell(row.name)}</TableCell>
                  <TableCell sx={{ py: 0.4, fontSize: 11 }}>{formatMs(row.latency_ms)}</TableCell>
                  <TableCell sx={{ py: 0.4, fontSize: 11 }}>{toCell(row.status)}</TableCell>
                  <TableCell sx={{ py: 0.4, fontSize: 11, fontFamily: "ui-monospace,monospace", maxWidth: 140, wordBreak: "break-all" }}>
                    <Button size="small" variant="text" sx={{ textTransform: "none", p: 0, minWidth: 0 }} onClick={() => inspectTrace(row.trace_id)}>{toCell(row.trace_id)}</Button>
                  </TableCell>
                </TableRow>
              ))}
              {!(observability.slow_spans || []).length ? <TableRow><TableCell colSpan={5} sx={{ py: 0.9 }}><Typography color="text.secondary" variant="body2">{t("admin.obs.empty")}</Typography></TableCell></TableRow> : null}
            </TableBody>
          </Table>
        </TableContainer>
      </Box>
      <Box sx={{ border: "1px solid #d8e3e8", borderRadius: 1, backgroundColor: "#fff", p: 1 }}>
        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.8 }}>{t("admin.obs.timelineTitle")}</Typography>
        {!!(observability.trace_timeline || []).length && (
          <TableContainer sx={{ border: "1px solid #d8e3e8", borderRadius: 1, backgroundColor: "#fff", maxHeight: 210, mb: 0.8 }}>
            <Table size="small" stickyHeader>
              <TableHead><TableRow>{["layer", "name", "latency_ms", "count"].map((key) => <TableCell key={`hh-${key}`} sx={{ backgroundColor: "#eef4f6", py: 0.45, fontSize: 11, fontWeight: 700 }}>{t(`admin.cols.${key}`)}</TableCell>)}</TableRow></TableHead>
              <TableBody>
                {traceHotspots.map((row, idx) => (
                  <TableRow key={`hr-${idx}`} hover>
                    <TableCell sx={{ py: 0.35, fontSize: 11 }}>{toCell(row.layer)}</TableCell>
                    <TableCell sx={{ py: 0.35, fontSize: 11 }}>{toCell(row.name)}</TableCell>
                    <TableCell sx={{ py: 0.35, fontSize: 11 }}>{formatMs(row.total)}</TableCell>
                    <TableCell sx={{ py: 0.35, fontSize: 11 }}>{toCell(row.count)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        )}
        <TableContainer sx={{ border: "1px solid #d8e3e8", borderRadius: 1, backgroundColor: "#fff", maxHeight: 460 }}>
          <Table size="small" stickyHeader>
            <TableHead><TableRow>{["started_at", "layer", "name", "latency_ms", "status", "parent_span_id"].map((key) => <TableCell key={`th-${key}`} sx={{ backgroundColor: "#eef4f6", py: 0.55, fontSize: 11, fontWeight: 700 }}>{t(`admin.cols.${key}`)}</TableCell>)}</TableRow></TableHead>
            <TableBody>
              {(observability.trace_timeline || []).map((row, idx) => (
                <TableRow key={`tr-${row.span_id || idx}`} hover>
                  <TableCell sx={{ py: 0.4, fontSize: 11 }}>{toCell(row.started_at)}</TableCell>
                  <TableCell sx={{ py: 0.4, fontSize: 11 }}>{toCell(row.layer)}</TableCell>
                  <TableCell sx={{ py: 0.4, fontSize: 11 }}>{toCell(row.name)}</TableCell>
                  <TableCell sx={{ py: 0.4, fontSize: 11 }}>{formatMs(row.latency_ms)}</TableCell>
                  <TableCell sx={{ py: 0.4, fontSize: 11 }}>{toCell(row.status)}</TableCell>
                  <TableCell sx={{ py: 0.4, fontSize: 11, fontFamily: "ui-monospace,monospace", maxWidth: 120, wordBreak: "break-all" }}>{toCell(row.parent_span_id)}</TableCell>
                </TableRow>
              ))}
              {!(observability.trace_timeline || []).length ? <TableRow><TableCell colSpan={6} sx={{ py: 0.9 }}><Typography color="text.secondary" variant="body2">{t("admin.obs.timelineHint")}</Typography></TableCell></TableRow> : null}
            </TableBody>
          </Table>
        </TableContainer>
      </Box>
    </Box>
  );
}

const LOG_LEVELS = ["ALL", "WARNING", "ERROR", "INFO", "DEBUG", "CRITICAL"];
const LOG_SOURCES = [
  { value: "app", label: "app.log" },
  { value: "tasks", label: "tasks.log" },
  { value: "scheduler", label: "scheduler.log" },
];

function LogsSection() {
  const [level, setLevel] = useState("ALL");
  const [source, setSource] = useState("app");
  const [limit, setLimit] = useState("200");
  const [lines, setLines] = useState([]);
  const [total, setTotal] = useState(0);
  const [status, setStatus] = useState({ type: "info", text: "" });
  const [loading, setLoading] = useState(false);

  async function load() {
    setLoading(true);
    try {
      const data = await getDebugLogs({ level, source, limit: Number(limit) || 200 });
      setLines(data.lines || []);
      setTotal(data.total || 0);
      setStatus({ type: "info", text: "" });
    } catch (err) {
      setStatus({ type: "error", text: `加载日志失败：${err.message}` });
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <Box>
      <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 1.2 }}>
        <Stack direction="row" spacing={0.8} alignItems="center">
          <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>日志查看器</Typography>
          {total > 0 && <Chip size="small" label={`共 ${total} 条`} />}
        </Stack>
        <Button size="small" variant="contained" onClick={load} disabled={loading}>{loading ? "加载中..." : "刷新"}</Button>
      </Stack>
      <Stack direction={{ xs: "column", sm: "row" }} spacing={1} sx={{ mb: 1 }}>
        <TextField select size="small" label="日志级别" value={level} onChange={(e) => setLevel(e.target.value)} sx={{ minWidth: 130 }}>
          {LOG_LEVELS.map((lv) => <MenuItem key={lv} value={lv}>{lv}</MenuItem>)}
        </TextField>
        <TextField select size="small" label="日志来源" value={source} onChange={(e) => setSource(e.target.value)} sx={{ minWidth: 140 }}>
          {LOG_SOURCES.map((s) => <MenuItem key={s.value} value={s.value}>{s.label}</MenuItem>)}
        </TextField>
        <TextField size="small" label="最多显示行数" type="number" value={limit} onChange={(e) => setLimit(e.target.value)} sx={{ maxWidth: 130 }} inputProps={{ min: 1, max: 500 }} />
        <Button size="small" variant="outlined" onClick={load} disabled={loading} sx={{ whiteSpace: "nowrap" }}>应用过滤</Button>
      </Stack>
      {!!status.text && <Alert severity={status.type} sx={{ mb: 1 }}>{status.text}</Alert>}
      <Box
        sx={{
          border: "1px solid #d8e3e8",
          borderRadius: 1,
          backgroundColor: "#0f172a",
          p: 1,
          maxHeight: 560,
          overflowY: "auto",
          fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, Liberation Mono, monospace",
          fontSize: 11,
        }}
      >
        {lines.length === 0 ? (
          <Typography variant="body2" sx={{ color: "#94a3b8", p: 0.5 }}>
            {loading ? "加载中..." : `暂无 ${level} 级别日志（来源：${source}）`}
          </Typography>
        ) : (
          lines.map((line, idx) => (
            <Box
              key={`log-${idx}`}
              sx={{
                px: 0.5, py: 0.15, borderRadius: 0.5,
                color: line.includes("[ERROR]") ? "#fca5a5" : line.includes("[WARNING]") ? "#fde68a" : "#94a3b8",
                whiteSpace: "pre-wrap", wordBreak: "break-all", lineHeight: 1.55,
                "&:hover": { backgroundColor: "rgba(255,255,255,0.04)" },
              }}
            >
              {line}
            </Box>
          ))
        )}
      </Box>
      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.5 }}>
        显示最新 {lines.length} 条 · 来源：logs/{source}.log
      </Typography>
    </Box>
  );
}

// ─── Dashboard ────────────────────────────────────────────────────────────────

function DebugDashboard({ onLockout }) {
  const { section } = useParams();
  const navigate = useNavigate();
  const activeSection = NAV_SECTIONS.some((s) => s.key === section) ? section : "metrics";
  function setActiveSection(key) { navigate(`/debug/${key}`); }

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
          {/* Sidebar */}
          <Stack spacing={1.4} sx={{ position: { lg: "sticky" }, top: { lg: 16 } }}>
            <Card sx={{ borderRadius: 1.5 }}>
              <CardContent>
                <Stack direction="row" alignItems="center" justifyContent="space-between">
                  <Stack direction="row" spacing={0.8} alignItems="center">
                    <BugReportOutlinedIcon fontSize="small" color="action" />
                    <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>Debug 控制台</Typography>
                  </Stack>
                  <Button size="small" color="inherit" onClick={onLockout} sx={{ fontSize: 12, color: "text.secondary" }}>退出</Button>
                </Stack>
                <Typography variant="caption" color="text.secondary" sx={{ mt: 0.2, display: "block" }}>
                  指标 · 可观测性 · 日志
                </Typography>
              </CardContent>
            </Card>

            <Card sx={{ borderRadius: 1.5 }}>
              <CardContent sx={{ p: 1.8 }}>
                <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1 }}>
                  导航
                </Typography>
                <Stack spacing={1}>
                  {NAV_SECTIONS.map((item) => (
                    <NavTab key={item.key} active={activeSection === item.key} icon={item.icon} onClick={() => setActiveSection(item.key)}>
                      {item.label}
                    </NavTab>
                  ))}
                </Stack>
              </CardContent>
            </Card>
          </Stack>

          {/* Main content */}
          <Card sx={{ borderRadius: 1.5 }}>
            <CardContent>
              {activeSection === "metrics" && <MetricsSection />}
              {activeSection === "observability" && <ObservabilitySection />}
              {activeSection === "logs" && <LogsSection />}
            </CardContent>
          </Card>
        </Box>
      </Container>
    </Box>
  );
}

export default function DebugPage() {
  const [debugToken, setDebugTokenState] = useState(() => {
    const stored = localStorage.getItem(DEBUG_TOKEN_KEY) || "";
    if (stored) setDebugToken(stored);
    return stored;
  });

  function handleUnlock(token) {
    setDebugTokenState(token);
  }

  function handleLockout() {
    localStorage.removeItem(DEBUG_TOKEN_KEY);
    setDebugToken("");
    setDebugTokenState("");
  }

  useEffect(() => {
    onDebugAuthError(handleLockout);
    return () => onDebugAuthError(null);
  }, []);

  if (!debugToken) return <TokenGate onUnlock={handleUnlock} />;
  return <DebugDashboard onLockout={handleLockout} />;
}
