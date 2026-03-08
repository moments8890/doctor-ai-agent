import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  Alert,
  AlertTitle,
  Badge,
  Box,
  Button,
  Card,
  CardActionArea,
  CardContent,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  IconButton,
  InputAdornment,
  MenuItem,
  Snackbar,
  Stack,
  TextField,
  Tooltip,
  Typography,
} from "@mui/material";
import useMediaQuery from "@mui/material/useMediaQuery";
import { useTheme } from "@mui/material/styles";
import BottomNavigation from "@mui/material/BottomNavigation";
import BottomNavigationAction from "@mui/material/BottomNavigationAction";
import HomeOutlinedIcon from "@mui/icons-material/HomeOutlined";
import PeopleOutlineIcon from "@mui/icons-material/PeopleOutline";
import AssignmentOutlinedIcon from "@mui/icons-material/AssignmentOutlined";
import SearchIcon from "@mui/icons-material/Search";
import EditOutlinedIcon from "@mui/icons-material/EditOutlined";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import ExpandLessIcon from "@mui/icons-material/ExpandLess";
import ChatOutlinedIcon from "@mui/icons-material/ChatOutlined";
import SendOutlinedIcon from "@mui/icons-material/SendOutlined";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import LogoutIcon from "@mui/icons-material/Logout";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import { Paper } from "@mui/material";
import { getPatients, getRecords, getTasks, patchTask, updateRecord, sendChat, getPendingRecord, confirmPendingRecord, abandonPendingRecord, getDoctorProfile, updateDoctorProfile } from "../api";
import RecordFields from "../components/RecordFields";
import { useDoctorStore } from "../store/doctorStore";
import { t } from "../i18n";

// ─── Constants ─────────────────────────────────────────────────────────────

const RISK_COLOR = { critical: "#ef4444", high: "#f97316", medium: "#eab308", low: "#22c55e" };
const RISK_LABEL = { critical: "危重", high: "高风险", medium: "中风险", low: "低风险" };
const FOLLOWUP_LABEL = {
  not_needed: "无需随访", scheduled: "已安排", due_soon: "即将到期", overdue: "已逾期",
};
const FOLLOWUP_COLOR = { not_needed: "default", scheduled: "info", due_soon: "warning", overdue: "error" };

const RECORD_FIELDS = [
  { key: "content", label: "临床笔记" },
  { key: "record_type", label: "类型" },
];

const RECORD_TYPE_COLOR = {
  visit: "default",
  referral: "info",
  surgery: "error",
  lab: "success",
  imaging: "warning",
  dictation: "secondary",
  import: "default",
  interview_summary: "info",
};

const RECORD_TYPE_LABEL = {
  visit: "门诊",
  referral: "转诊",
  surgery: "手术",
  lab: "检验",
  imaging: "影像",
  dictation: "语音录入",
  import: "导入",
  interview_summary: "问诊总结",
};

const NAV = [
  { key: "chat", label: "AI 助手", icon: <ChatOutlinedIcon fontSize="small" /> },
  { key: "home", label: "首页", icon: <HomeOutlinedIcon fontSize="small" /> },
  { key: "patients", label: "患者", icon: <PeopleOutlineIcon fontSize="small" /> },
  { key: "tasks", label: "任务", icon: <AssignmentOutlinedIcon fontSize="small" /> },
];

// ─── Helpers ───────────────────────────────────────────────────────────────

function RiskBadge({ level }) {
  if (!level) return null;
  return (
    <Box component="span" sx={{
      display: "inline-block", px: 0.8, py: 0.1, borderRadius: 1,
      fontSize: 11, fontWeight: 700, color: "#fff",
      backgroundColor: RISK_COLOR[level] || "#94a3b8",
    }}>
      {RISK_LABEL[level] || level}
    </Box>
  );
}

function NavBtn({ active, icon, children, onClick, badgeCount }) {
  const content = (
    <Button
      onClick={onClick}
      startIcon={icon}
      variant={active ? "contained" : "text"}
      sx={{
        justifyContent: "flex-start", width: "100%", borderRadius: 1.5,
        fontWeight: active ? 700 : 400, color: active ? undefined : "text.secondary",
        py: 1,
      }}
    >
      {children}
    </Button>
  );
  if (badgeCount > 0) {
    return (
      <Badge badgeContent={badgeCount} color="error" sx={{ width: "100%", "& .MuiBadge-badge": { right: 8, top: 8 } }}>
        {content}
      </Badge>
    );
  }
  return content;
}

// ─── Record edit dialog ────────────────────────────────────────────────────

function RecordEditDialog({ record, doctorId, open, onClose, onSaved }) {
  const [form, setForm] = useState({});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (record) {
      const init = {};
      RECORD_FIELDS.forEach(({ key }) => { init[key] = record[key] || ""; });
      init.tags = Array.isArray(record.tags) ? [...record.tags] : [];
      setForm(init);
      setError("");
    }
  }, [record]);

  async function handleSave() {
    setSaving(true);
    setError("");
    try {
      const saved = await updateRecord(doctorId, record.id, { ...form, tags: form.tags });
      onSaved(saved);
      onClose();
    } catch (e) {
      setError(e.message || "保存失败");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth>
      <DialogTitle sx={{ fontWeight: 700 }}>编辑病历 <Typography component="span" variant="body2" color="text.secondary">#{record?.id}</Typography></DialogTitle>
      <DialogContent dividers>
        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
        <Stack spacing={2}>
          {RECORD_FIELDS.map(({ key, label }) => (
            <TextField
              key={key}
              label={label}
              multiline={key === "content"}
              minRows={key === "content" ? 5 : 1}
              maxRows={key === "content" ? 16 : 1}
              size="small"
              fullWidth
              value={form[key] || ""}
              onChange={(e) => setForm((f) => ({ ...f, [key]: e.target.value }))}
            />
          ))}
          <Box>
            <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>标签</Typography>
            <Stack direction="row" flexWrap="wrap" spacing={0.5} sx={{ mb: 0.5 }}>
              {(form.tags || []).map((tag, i) => (
                <Chip key={i} label={tag} size="small" onDelete={() => setForm(f => ({ ...f, tags: f.tags.filter((_, j) => j !== i) }))} />
              ))}
            </Stack>
            <TextField
              size="small"
              placeholder="输入标签后按 Enter 添加"
              onKeyDown={(e) => {
                if (e.key === "Enter" && e.target.value.trim()) {
                  e.preventDefault();
                  const newTag = e.target.value.trim();
                  setForm(f => ({ ...f, tags: [...(f.tags || []), newTag] }));
                  e.target.value = "";
                }
              }}
            />
          </Box>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={saving}>取消</Button>
        <Button variant="contained" onClick={handleSave} disabled={saving}>
          {saving ? "保存中…" : "保存"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

// ─── Single record card ────────────────────────────────────────────────────

function RecordCard({ record, doctorId, onUpdated }) {
  const [expanded, setExpanded] = useState(false);
  const [editing, setEditing] = useState(false);
  const [current, setCurrent] = useState(record);

  function handleSaved(updated) {
    setCurrent(updated);
    onUpdated?.(updated);
  }

  const date = current.created_at ? current.created_at.slice(0, 10) : "—";

  return (
    <Card variant="outlined" sx={{ borderRadius: 1.5, mb: 1.2 }}>
      <CardActionArea onClick={() => setExpanded((v) => !v)} sx={{ px: 2, py: 1.2 }}>
        <Stack direction="row" alignItems="flex-start" spacing={1.5}>
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
              <Typography variant="caption" color="text.secondary" sx={{ fontFamily: "monospace" }}>{date}</Typography>
              {current.record_type && (
                <Chip
                  label={RECORD_TYPE_LABEL[current.record_type] || current.record_type}
                  size="small"
                  color={RECORD_TYPE_COLOR[current.record_type] || "default"}
                  sx={{ fontSize: 11, height: 18 }}
                />
              )}
              {(Array.isArray(current.tags) ? current.tags : []).map((tag, i) => (
                <Chip key={i} label={tag} size="small" sx={{ fontSize: 11, maxWidth: 160 }} />
              ))}
            </Stack>
            <Typography variant="body2" sx={{ mt: 0.4, color: "text.primary", fontWeight: 500 }} noWrap={!expanded}>
              {current.content || <span style={{ color: "#94a3b8" }}>（无记录内容）</span>}
            </Typography>
          </Box>
          <Stack direction="row" spacing={0.5} alignItems="center" onClick={(e) => e.stopPropagation()}>
            <Tooltip title="编辑">
              <IconButton size="small" onClick={() => setEditing(true)}>
                <EditOutlinedIcon fontSize="small" />
              </IconButton>
            </Tooltip>
            {expanded ? <ExpandLessIcon fontSize="small" sx={{ color: "text.secondary" }} /> : <ExpandMoreIcon fontSize="small" sx={{ color: "text.secondary" }} />}
          </Stack>
        </Stack>
      </CardActionArea>

      {expanded && (
        <Box sx={{ px: 2, pb: 2, pt: 0.5 }}>
          <Divider sx={{ mb: 1.5 }} />
          <Stack spacing={1.2}>
            {RECORD_FIELDS.map(({ key, label }) => current[key] ? (
              <Box key={key}>
                <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 700, display: "block" }}>{label}</Typography>
                <Typography variant="body2" sx={{ whiteSpace: "pre-wrap" }}>{current[key]}</Typography>
              </Box>
            ) : null)}
          </Stack>
        </Box>
      )}

      <RecordEditDialog
        record={current}
        doctorId={doctorId}
        open={editing}
        onClose={() => setEditing(false)}
        onSaved={handleSaved}
      />
    </Card>
  );
}

// ─── Patient detail panel ──────────────────────────────────────────────────

function PatientDetail({ patient, doctorId }) {
  const [records, setRecords] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(() => {
    if (!patient) return;
    setLoading(true);
    setError("");
    getRecords({ doctorId, patientId: patient.id, limit: 100 })
      .then((d) => setRecords(d.items || []))
      .catch((e) => setError(e.message || "加载失败"))
      .finally(() => setLoading(false));
  }, [patient?.id, doctorId]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { load(); }, [load]);

  if (!patient) {
    return (
      <Box sx={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: "100%", color: "text.secondary", gap: 1.5 }}>
        <PeopleOutlineIcon sx={{ fontSize: 64, opacity: 0.3 }} />
        <Typography color="text.secondary">← 请在左侧选择患者</Typography>
      </Box>
    );
  }

  const age = patient.year_of_birth ? new Date().getFullYear() - patient.year_of_birth : null;

  function handleRecordUpdated(updated) {
    setRecords((prev) => prev.map((r) => (r.id === updated.id ? { ...r, ...updated } : r)));
  }

  return (
    <Box sx={{ p: 2.5, overflowY: "auto", height: "100%" }}>
      {/* Patient header */}
      <Card variant="outlined" sx={{ borderRadius: 2, mb: 2.5, p: 2 }}>
        <Stack direction="row" alignItems="flex-start" justifyContent="space-between" flexWrap="wrap" spacing={1}>
          <Box>
            <Typography variant="h6" sx={{ fontWeight: 700 }}>{patient.name}</Typography>
            <Stack direction="row" spacing={1} alignItems="center" sx={{ mt: 0.5 }} flexWrap="wrap">
              {patient.gender && <Typography variant="caption" color="text.secondary">{patient.gender}</Typography>}
              {age && <Typography variant="caption" color="text.secondary">{age} 岁</Typography>}
              <RiskBadge level={patient.primary_risk_level} />
              {patient.follow_up_state && (
                <Chip
                  label={FOLLOWUP_LABEL[patient.follow_up_state] || patient.follow_up_state}
                  size="small"
                  color={FOLLOWUP_COLOR[patient.follow_up_state] || "default"}
                />
              )}
            </Stack>
            {patient.labels?.length > 0 && (
              <Stack direction="row" spacing={0.5} sx={{ mt: 0.8 }} flexWrap="wrap">
                {patient.labels.map((l) => (
                  <Chip key={l.id} label={l.name} size="small" sx={{ backgroundColor: l.color || "#e2e8f0", fontSize: 11 }} />
                ))}
              </Stack>
            )}
          </Box>
          <Typography variant="caption" color="text.secondary">{patient.record_count} 份病历</Typography>
        </Stack>
      </Card>

      {/* Records */}
      <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 1.5 }}>
        <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>病历记录</Typography>
        {loading && <CircularProgress size={16} />}
      </Stack>

      {error && (
        <Alert severity="error" sx={{ mb: 1.5 }} action={<Button size="small" onClick={load}>重试</Button>}>{error}</Alert>
      )}

      {!loading && !error && records.length === 0 && (
        <Typography variant="body2" color="text.secondary">暂无病历。</Typography>
      )}

      {records.map((r) => (
        <RecordCard key={r.id} record={r} doctorId={doctorId} onUpdated={handleRecordUpdated} />
      ))}
    </Box>
  );
}

// ─── Patient list panel ─────────────────────────────────────────────────────

const RISK_OPTS = [
  { value: "", label: "全部风险" },
  { value: "critical", label: "危重" },
  { value: "high", label: "高风险" },
  { value: "medium", label: "中风险" },
  { value: "low", label: "低风险" },
];

function PatientsSection({ doctorId }) {
  const { patientId } = useParams();
  const navigate = useNavigate();
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down("sm"));
  const [patients, setPatients] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [risk, setRisk] = useState("");

  const selectedId = patientId ? Number(patientId) : null;
  const selectedPatient = patients.find((p) => p.id === selectedId) || null;

  const load = useCallback(() => {
    setLoading(true);
    setError("");
    getPatients(doctorId, risk ? { risk } : {}, 200)
      .then((d) => setPatients(d.items || []))
      .catch((e) => setError(e.message || "加载失败"))
      .finally(() => setLoading(false));
  }, [doctorId, risk]);

  useEffect(() => { load(); }, [load]);

  const filtered = search.trim()
    ? patients.filter((p) => p.name.includes(search.trim()))
    : patients;

  // Mobile: show only detail when a patient is selected
  if (isMobile && selectedId) {
    return (
      <Box sx={{ display: "flex", flexDirection: "column", height: "100%" }}>
        <Box sx={{ px: 1.5, py: 1, borderBottom: "1px solid #e2e8f0", backgroundColor: "#fff" }}>
          <Button startIcon={<ArrowBackIcon />} onClick={() => navigate("/doctor/patients")} size="small">
            返回列表
          </Button>
        </Box>
        <Box sx={{ flex: 1, overflow: "hidden" }}>
          <PatientDetail patient={selectedPatient} doctorId={doctorId} />
        </Box>
      </Box>
    );
  }

  // Mobile: full-width patient list (no split layout)
  if (isMobile) {
    return (
      <Box sx={{ display: "flex", flexDirection: "column", height: "100%" }}>
        <Box sx={{ p: 1.5, borderBottom: "1px solid #e2e8f0" }}>
          <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1 }}>
            患者管理{patients.length > 0 ? ` (${patients.length})` : ""}
          </Typography>
          <TextField
            size="small" fullWidth placeholder="搜索患者姓名"
            value={search} onChange={(e) => setSearch(e.target.value)}
            InputProps={{ startAdornment: <InputAdornment position="start"><SearchIcon fontSize="small" /></InputAdornment> }}
            sx={{ mb: 1 }}
          />
          <TextField select size="small" fullWidth value={risk} onChange={(e) => setRisk(e.target.value)} label="风险筛选">
            {RISK_OPTS.map((o) => <MenuItem key={o.value} value={o.value}>{o.label}</MenuItem>)}
          </TextField>
        </Box>
        {error && <Alert severity="error" action={<Button size="small" onClick={load}>重试</Button>}>{error}</Alert>}
        <Box sx={{ flex: 1, overflowY: "auto", p: 1 }}>
          {loading && <Box sx={{ p: 2, textAlign: "center" }}><CircularProgress size={20} /></Box>}
          {!loading && filtered.length === 0 && !error && (
            <Typography variant="body2" color="text.secondary" sx={{ p: 2 }}>暂无患者</Typography>
          )}
          {filtered.map((p) => {
            const age = p.year_of_birth ? new Date().getFullYear() - p.year_of_birth : null;
            const isSelected = p.id === selectedId;
            return (
              <Card
                key={p.id}
                variant="outlined"
                onClick={() => navigate(`/doctor/patients/${p.id}`)}
                sx={{
                  mb: 0.8, borderRadius: 1.5, cursor: "pointer",
                  borderColor: isSelected ? "primary.main" : "divider",
                  backgroundColor: isSelected ? "primary.50" : "background.paper",
                  "&:hover": { borderColor: "primary.main", backgroundColor: "primary.50" },
                }}
              >
                <CardContent sx={{ py: 1.2, px: 1.5, "&:last-child": { pb: 1.2 } }}>
                  <Stack direction="row" alignItems="center" justifyContent="space-between">
                    <Typography variant="body2" sx={{ fontWeight: 600 }}>{p.name}</Typography>
                    <RiskBadge level={p.primary_risk_level} />
                  </Stack>
                  <Stack direction="row" spacing={1} sx={{ mt: 0.4 }} flexWrap="wrap">
                    {p.gender && <Typography variant="caption" color="text.secondary">{p.gender}</Typography>}
                    {age && <Typography variant="caption" color="text.secondary">{age} 岁</Typography>}
                    <Typography variant="caption" color="text.secondary">{p.record_count} 份病历</Typography>
                  </Stack>
                  {p.follow_up_state && p.follow_up_state !== "not_needed" && (
                    <Chip
                      label={FOLLOWUP_LABEL[p.follow_up_state] || p.follow_up_state}
                      size="small"
                      color={FOLLOWUP_COLOR[p.follow_up_state] || "default"}
                      sx={{ mt: 0.5, fontSize: 10, height: 18 }}
                    />
                  )}
                </CardContent>
              </Card>
            );
          })}
        </Box>
      </Box>
    );
  }

  // Desktop: split layout
  return (
    <Box sx={{ display: "flex", height: "100%", overflow: "hidden" }}>
      {/* Left: patient list */}
      <Box sx={{ width: 320, flexShrink: 0, borderRight: "1px solid #e2e8f0", display: "flex", flexDirection: "column" }}>
        <Box sx={{ p: 1.5, borderBottom: "1px solid #e2e8f0" }}>
          <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1 }}>
            患者管理{patients.length > 0 ? ` (${patients.length})` : ""}
          </Typography>
          <TextField
            size="small" fullWidth placeholder="搜索患者姓名"
            value={search} onChange={(e) => setSearch(e.target.value)}
            InputProps={{ startAdornment: <InputAdornment position="start"><SearchIcon fontSize="small" /></InputAdornment> }}
            sx={{ mb: 1 }}
          />
          <TextField select size="small" fullWidth value={risk} onChange={(e) => setRisk(e.target.value)} label="风险筛选">
            {RISK_OPTS.map((o) => <MenuItem key={o.value} value={o.value}>{o.label}</MenuItem>)}
          </TextField>
        </Box>

        {error && <Alert severity="error" action={<Button size="small" onClick={load}>重试</Button>}>{error}</Alert>}

        <Box sx={{ flex: 1, overflowY: "auto", p: 1 }}>
          {loading && <Box sx={{ p: 2, textAlign: "center" }}><CircularProgress size={20} /></Box>}
          {!loading && filtered.length === 0 && !error && (
            <Typography variant="body2" color="text.secondary" sx={{ p: 2 }}>暂无患者</Typography>
          )}
          {filtered.map((p) => {
            const age = p.year_of_birth ? new Date().getFullYear() - p.year_of_birth : null;
            const isSelected = p.id === selectedId;
            return (
              <Card
                key={p.id}
                variant="outlined"
                onClick={() => navigate(`/doctor/patients/${p.id}`)}
                sx={{
                  mb: 0.8, borderRadius: 1.5, cursor: "pointer",
                  borderColor: isSelected ? "primary.main" : "divider",
                  backgroundColor: isSelected ? "primary.50" : "background.paper",
                  "&:hover": { borderColor: "primary.main", backgroundColor: "primary.50" },
                }}
              >
                <CardContent sx={{ py: 1.2, px: 1.5, "&:last-child": { pb: 1.2 } }}>
                  <Stack direction="row" alignItems="center" justifyContent="space-between">
                    <Typography variant="body2" sx={{ fontWeight: 600 }}>{p.name}</Typography>
                    <RiskBadge level={p.primary_risk_level} />
                  </Stack>
                  <Stack direction="row" spacing={1} sx={{ mt: 0.4 }} flexWrap="wrap">
                    {p.gender && <Typography variant="caption" color="text.secondary">{p.gender}</Typography>}
                    {age && <Typography variant="caption" color="text.secondary">{age} 岁</Typography>}
                    <Typography variant="caption" color="text.secondary">{p.record_count} 份病历</Typography>
                  </Stack>
                  {p.follow_up_state && p.follow_up_state !== "not_needed" && (
                    <Chip
                      label={FOLLOWUP_LABEL[p.follow_up_state] || p.follow_up_state}
                      size="small"
                      color={FOLLOWUP_COLOR[p.follow_up_state] || "default"}
                      sx={{ mt: 0.5, fontSize: 10, height: 18 }}
                    />
                  )}
                </CardContent>
              </Card>
            );
          })}
        </Box>
      </Box>

      {/* Right: patient detail */}
      <Box sx={{ flex: 1, overflow: "hidden" }}>
        <PatientDetail patient={selectedPatient} doctorId={doctorId} />
      </Box>
    </Box>
  );
}

// ─── Tasks section ──────────────────────────────────────────────────────────

const TASK_STATUS_OPTS = [
  { value: "pending", label: "待处理" },
  { value: "completed", label: "已完成" },
  { value: "cancelled", label: "已取消" },
];

function TasksSection({ doctorId }) {
  const [tasks, setTasks] = useState([]);
  const [loading, setLoading] = useState(false);
  const [statusFilter, setStatusFilter] = useState("pending");

  const load = useCallback(() => {
    setLoading(true);
    getTasks(doctorId, statusFilter || null)
      .then((d) => setTasks(Array.isArray(d) ? d : (d.items || [])))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [doctorId, statusFilter]);

  useEffect(() => { load(); }, [load]);

  async function handleStatus(taskId, status) {
    try {
      await patchTask(taskId, doctorId, status);
      load();
    } catch { /* ignore */ }
  }

  return (
    <Box sx={{ p: 3, overflowY: "auto", height: "100%" }}>
      <Stack direction="row" alignItems="center" spacing={2} sx={{ mb: 2.5 }}>
        <Typography variant="h6" sx={{ fontWeight: 700 }}>任务列表</Typography>
        {loading && <CircularProgress size={18} />}
        <Box sx={{ flex: 1 }} />
        <Stack direction="row" spacing={0.5}>
          {TASK_STATUS_OPTS.map((o) => (
            <Chip
              key={o.value}
              label={o.label}
              size="small"
              onClick={() => setStatusFilter(o.value)}
              variant={statusFilter === o.value ? "filled" : "outlined"}
              color={statusFilter === o.value ? "primary" : "default"}
              clickable
            />
          ))}
        </Stack>
      </Stack>

      {!loading && tasks.length === 0 && (
        <Typography color="text.secondary" variant="body2">暂无{TASK_STATUS_OPTS.find(o => o.value === statusFilter)?.label}任务。</Typography>
      )}

      <Stack spacing={1.2}>
        {tasks.map((task) => {
          const isOverdue = task.due_at && new Date(task.due_at) < new Date() && task.status === "pending";
          return (
            <Card key={task.id} variant="outlined" sx={{ borderRadius: 1.5 }}>
              <CardContent sx={{ py: 1.5, px: 2, "&:last-child": { pb: 1.5 } }}>
                <Stack direction="row" alignItems="flex-start" justifyContent="space-between" spacing={1}>
                  <Box sx={{ flex: 1 }}>
                    <Typography variant="body2" sx={{ fontWeight: 600 }}>{task.title || task.task_type}</Typography>
                    {task.description && (
                      <Typography variant="caption" color="text.secondary">{task.description}</Typography>
                    )}
                    {task.due_at && (
                      <Typography variant="caption" sx={{ display: "block", mt: 0.3, color: isOverdue ? "error.main" : "text.secondary" }}>
                        {isOverdue ? "已逾期 · " : "到期 · "}{task.due_at.slice(0, 10)}
                      </Typography>
                    )}
                  </Box>
                  {task.status === "pending" && (
                    <Stack direction="row" spacing={0.5}>
                      <Button size="small" variant="contained" onClick={() => handleStatus(task.id, "completed")}>完成</Button>
                      <Button size="small" color="inherit" onClick={() => handleStatus(task.id, "cancelled")}>取消</Button>
                    </Stack>
                  )}
                </Stack>
              </CardContent>
            </Card>
          );
        })}
      </Stack>
    </Box>
  );
}

// ─── Chat section ───────────────────────────────────────────────────────────

function MsgBubble({ msg }) {
  const isUser = msg.role === "user";
  return (
    <Box sx={{ display: "flex", justifyContent: isUser ? "flex-end" : "flex-start", px: 1 }}>
      <Paper elevation={0} sx={{
        maxWidth: "min(85%, 720px)", p: 1.5, borderRadius: 2,
        bgcolor: isUser ? "#eaf4ff" : "#f0faf4",
        border: "1px solid", borderColor: isUser ? "#c8def6" : "#c9e8d4",
      }}>
        <Typography variant="body2" sx={{ whiteSpace: "pre-wrap", lineHeight: 1.6 }}>{msg.content}</Typography>
        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.5, textAlign: "right" }}>{msg.ts}</Typography>
        {!isUser && msg.record ? <RecordFields record={msg.record} /> : null}
      </Paper>
    </Box>
  );
}

function ChatSection({ doctorId, onMessageCountChange }) {
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [messages, setMessages] = useState([]);
  const [clearConfirmOpen, setClearConfirmOpen] = useState(false);
  const bottomRef = useRef(null);

  function nowTs() {
    const d = new Date();
    return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
  }
  const storageKey = `doctor_ai_chat_history:${(doctorId || "anon")}`;

  useEffect(() => {
    const raw = localStorage.getItem(storageKey);
    try {
      const parsed = raw ? JSON.parse(raw) : null;
      setMessages(Array.isArray(parsed) && parsed.length ? parsed : [{ role: "assistant", content: t("chat.welcome"), ts: nowTs() }]);
    } catch {
      setMessages([{ role: "assistant", content: t("chat.welcome"), ts: nowTs() }]);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [doctorId]);

  useEffect(() => {
    if (messages.length) localStorage.setItem(storageKey, JSON.stringify(messages));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [messages]);

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  useEffect(() => { onMessageCountChange?.(messages.length); }, [messages.length, onMessageCountChange]);

  const history = useMemo(() => messages.map((m) => ({ role: m.role, content: m.content })), [messages]);

  function onClear() {
    const fresh = [{ role: "assistant", content: t("chat.welcome"), ts: nowTs() }];
    setMessages(fresh);
    localStorage.setItem(storageKey, JSON.stringify(fresh));
  }

  async function onSend() {
    const text = input.trim();
    if (!text || loading) return;
    setMessages((prev) => [...prev, { role: "user", content: text, ts: nowTs() }]);
    setInput("");
    setLoading(true);
    try {
      const data = await sendChat({ text, doctor_id: doctorId, history });
      setMessages((prev) => [...prev, { role: "assistant", content: data.reply || t("chat.received"), record: data.record || null, ts: nowTs() }]);
    } catch (error) {
      setMessages((prev) => [...prev, { role: "assistant", content: t("chat.requestFailed", { message: error.message }), ts: nowTs() }]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%" }}>
      {/* Topbar */}
      <Box sx={{ px: 3, py: 1.2, borderBottom: "1px solid #e2e8f0", backgroundColor: "#fff", display: "flex", alignItems: "center" }}>
        <Typography variant="subtitle2" sx={{ fontWeight: 700, color: "text.secondary", flex: 1 }}>{t("chat.workspaceTitle")}</Typography>
        <Tooltip title="清空对话">
          <IconButton size="small" onClick={() => setClearConfirmOpen(true)} sx={{ color: "text.secondary" }}>
            <DeleteOutlineIcon fontSize="small" />
          </IconButton>
        </Tooltip>
      </Box>
      {/* Messages */}
      <Box sx={{ flex: 1, overflowY: "auto", py: 2, display: "flex", flexDirection: "column", gap: 1.4 }}>
        {messages.map((msg, idx) => <MsgBubble key={`${msg.role}-${idx}`} msg={msg} />)}
        {loading && <Box sx={{ px: 2 }}><Typography variant="caption" color="text.secondary">AI 正在回复…</Typography></Box>}
        <div ref={bottomRef} />
      </Box>
      {/* Input */}
      <Box sx={{ px: 2, py: 1.5, borderTop: "1px solid #e2e8f0", backgroundColor: "#fff" }}>
        <Stack direction="row" spacing={1} alignItems="flex-end">
          <Box sx={{ flex: 1 }}>
            <TextField
              multiline minRows={2} maxRows={6} fullWidth size="small"
              placeholder={t("chat.placeholder")}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); onSend(); } }}
              sx={{ "& .MuiOutlinedInput-root": { borderRadius: 1.5 } }}
            />
            {input.length > 0 && (
              <Typography variant="caption" color="text.secondary" sx={{ display: "block", textAlign: "right", mt: 0.3 }}>
                {input.length} 字
              </Typography>
            )}
          </Box>
          <Button variant="contained" onClick={onSend} disabled={loading || !input.trim()}
            sx={{ borderRadius: 1.5, minWidth: 48, height: 48, flexShrink: 0 }}>
            <SendOutlinedIcon fontSize="small" />
          </Button>
        </Stack>
      </Box>

      {/* Clear confirmation dialog */}
      <Dialog open={clearConfirmOpen} onClose={() => setClearConfirmOpen(false)}>
        <DialogTitle>清空对话记录</DialogTitle>
        <DialogContent>
          <Typography>确定清空所有对话记录？此操作无法撤销。</Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setClearConfirmOpen(false)}>取消</Button>
          <Button color="error" onClick={() => { onClear(); setClearConfirmOpen(false); }}>清空</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}

// ─── Home / dashboard ───────────────────────────────────────────────────────

function StatCard({ label, value, color = "primary.main" }) {
  return (
    <Card variant="outlined" sx={{ borderRadius: 2, flex: 1, minWidth: 120 }}>
      <CardContent>
        <Typography variant="h4" sx={{ fontWeight: 800, color }}>{value ?? "—"}</Typography>
        <Typography variant="caption" color="text.secondary">{label}</Typography>
      </CardContent>
    </Card>
  );
}

function HomeSection({ doctorId, navigate }) {
  const [stats, setStats] = useState(null);
  const [pendingTasks, setPendingTasks] = useState([]);
  const [recentRecords, setRecentRecords] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      getPatients(doctorId, {}, 200),
      getTasks(doctorId, "pending"),
      getRecords({ doctorId, limit: 5 }),
    ]).then(([pData, tData, rData]) => {
      const patients = pData.items || [];
      const tasks = Array.isArray(tData) ? tData : (tData.items || []);
      const records = rData.items || [];
      setStats({
        patients: patients.length,
        pendingTasks: tasks.length,
        highRisk: patients.filter((p) => p.primary_risk_level === "critical" || p.primary_risk_level === "high").length,
        overdue: patients.filter((p) => p.follow_up_state === "overdue").length,
      });
      setPendingTasks(tasks.slice(0, 5));
      setRecentRecords(records.slice(0, 5));
    }).catch(() => {}).finally(() => setLoading(false));
  }, [doctorId]);

  if (loading) return <Box sx={{ p: 4, textAlign: "center" }}><CircularProgress /></Box>;

  return (
    <Box sx={{ p: 3, overflowY: "auto", height: "100%" }}>
      {/* Stats */}
      <Typography variant="h6" sx={{ fontWeight: 700, mb: 2 }}>总览</Typography>
      <Stack direction="row" spacing={1.5} flexWrap="wrap" useFlexGap sx={{ mb: 2 }}>
        <StatCard label="患者总数" value={stats?.patients} />
        <StatCard label="待处理任务" value={stats?.pendingTasks} color={stats?.pendingTasks > 0 ? "warning.main" : "success.main"} />
        <StatCard label="高风险患者" value={stats?.highRisk} color={stats?.highRisk > 0 ? "error.main" : "success.main"} />
        <StatCard label="逾期随访" value={stats?.overdue} color={stats?.overdue > 0 ? "error.main" : "success.main"} />
      </Stack>

      {/* Quick actions */}
      <Stack direction="row" spacing={1} flexWrap="wrap" sx={{ mb: 3 }}>
        <Button size="small" variant="outlined" onClick={() => navigate("/doctor/chat")}>新建对话</Button>
        <Button size="small" variant="outlined" onClick={() => navigate("/doctor/patients")}>查看高风险患者</Button>
        <Button size="small" variant="outlined" onClick={() => navigate("/doctor/tasks")}>查看逾期任务</Button>
      </Stack>

      {/* Pending tasks */}
      {pendingTasks.length > 0 && (
        <>
          <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 1 }}>
            <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>待处理任务</Typography>
            <Button size="small" onClick={() => navigate("/doctor/tasks")}>查看全部</Button>
          </Stack>
          <Stack spacing={0.8} sx={{ mb: 3 }}>
            {pendingTasks.map((task) => {
              const isOverdue = task.due_at && new Date(task.due_at) < new Date();
              return (
                <Card key={task.id} variant="outlined" sx={{ borderRadius: 1.5 }}>
                  <CardContent sx={{ py: 1, px: 1.5, "&:last-child": { pb: 1 } }}>
                    <Stack direction="row" alignItems="center" spacing={1}>
                      <Box sx={{ flex: 1 }}>
                        <Typography variant="body2" sx={{ fontWeight: 500 }}>{task.title || task.task_type}</Typography>
                        {task.due_at && (
                          <Typography variant="caption" sx={{ color: isOverdue ? "error.main" : "text.secondary" }}>
                            {isOverdue ? "已逾期 · " : "到期 · "}{task.due_at.slice(0, 10)}
                          </Typography>
                        )}
                      </Box>
                    </Stack>
                  </CardContent>
                </Card>
              );
            })}
          </Stack>
        </>
      )}

      {/* Recent records */}
      {recentRecords.length > 0 && (
        <>
          <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 1 }}>
            <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>最近病历</Typography>
            <Button size="small" onClick={() => navigate("/doctor/patients")}>查看患者</Button>
          </Stack>
          <Stack spacing={0.8}>
            {recentRecords.map((r) => (
              <Card key={r.id} variant="outlined" sx={{ borderRadius: 1.5 }}>
                <CardContent sx={{ py: 1, px: 1.5, "&:last-child": { pb: 1 } }}>
                  <Stack direction="row" alignItems="center" spacing={1.5}>
                    <Box sx={{ flex: 1 }}>
                      <Typography variant="body2" sx={{ fontWeight: 500 }}>
                        {r.patient_name || "未知患者"}
                        {(Array.isArray(r.tags) ? r.tags : []).slice(0, 2).map((tag, i) => (
                          <Chip key={i} label={tag} size="small" sx={{ ml: 0.5, fontSize: 10, height: 18 }} />
                        ))}
                      </Typography>
                      <Typography variant="caption" color="text.secondary" noWrap>
                        {r.content ? (r.content.length > 40 ? r.content.slice(0, 40) + "…" : r.content) : "无记录"} · {r.created_at?.slice(0, 10)}
                      </Typography>
                    </Box>
                    {r.patient_id && (
                      <IconButton size="small" onClick={() => navigate(`/doctor/patients/${r.patient_id}`)}>
                        <PeopleOutlineIcon fontSize="small" />
                      </IconButton>
                    )}
                  </Stack>
                </CardContent>
              </Card>
            ))}
          </Stack>
        </>
      )}
    </Box>
  );
}

// ─── Main DoctorPage ────────────────────────────────────────────────────────

export default function DoctorPage() {
  const { section, patientId } = useParams();
  const navigate = useNavigate();
  const { doctorId, doctorName, accessToken, clearAuth, setAuth } = useDoctorStore();
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down("sm"));
  const [pendingTaskCount, setPendingTaskCount] = useState(0);
  const [pendingRecord, setPendingRecord] = useState(null);
  const [confirmSnackbar, setConfirmSnackbar] = useState(false);

  // Onboarding dialog state
  const [showOnboarding, setShowOnboarding] = useState(false);
  const [onboardName, setOnboardName] = useState("");
  const [onboardSaving, setOnboardSaving] = useState(false);

  const activeSection = patientId ? "patients" : (section || "home");

  // Check onboarding status on mount
  useEffect(() => {
    if (!doctorId) return;
    getDoctorProfile(doctorId)
      .then((profile) => {
        if (!profile.onboarded) {
          setOnboardName(profile.name || "");
          setShowOnboarding(true);
        }
      })
      .catch(() => {});
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [doctorId]);

  async function handleOnboardSubmit() {
    if (!onboardName.trim() || onboardSaving) return;
    setOnboardSaving(true);
    try {
      await updateDoctorProfile(doctorId, { name: onboardName.trim() });
      setAuth(doctorId, onboardName.trim(), accessToken);
      setShowOnboarding(false);
    } catch {
      // ignore — leave dialog open so user can retry
    } finally {
      setOnboardSaving(false);
    }
  }

  useEffect(() => {
    if (!doctorId) return;
    getTasks(doctorId, "pending")
      .then((d) => {
        const tasks = Array.isArray(d) ? d : (d.items || []);
        setPendingTaskCount(tasks.length);
      })
      .catch(() => {});
  }, [doctorId]);

  useEffect(() => {
    if (!doctorId) return;
    const fetchPending = () => {
      getPendingRecord(doctorId)
        .then((data) => setPendingRecord(data || null))
        .catch(() => {});
    };
    fetchPending();
    const id = setInterval(fetchPending, 30000);
    return () => clearInterval(id);
  }, [doctorId]);

  async function handleConfirmPending() {
    try {
      await confirmPendingRecord(doctorId);
      setPendingRecord(null);
      setConfirmSnackbar(true);
    } catch (_) {}
  }

  async function handleAbandonPending() {
    try {
      await abandonPendingRecord(doctorId);
      setPendingRecord(null);
    } catch (_) {}
  }

  function handleNav(key) {
    if (key === "chat") navigate("/doctor/chat");
    else navigate(`/doctor/${key}`);
  }

  function handleLogout() {
    clearAuth();
    // Notify WeChat Mini Program web-view to return to MP login page
    if (window.__wxjs_environment === "miniprogram") {
      wx.miniProgram?.postMessage?.({ data: { action: "logout" } }); // eslint-disable-line no-undef
    }
    navigate("/login");
  }

  const navBadge = { tasks: pendingTaskCount };

  return (
    <Box sx={{ display: "flex", height: "100vh", background: "#f8fafb" }}>
      {/* Sidebar — desktop only */}
      {!isMobile && (
        <Box sx={{
          width: 220, flexShrink: 0, borderRight: "1px solid #e2e8f0",
          backgroundColor: "#fff", display: "flex", flexDirection: "column", py: 2, px: 1.5,
        }}>
          {/* Header */}
          <Box sx={{ mb: 3, px: 0.5 }}>
            <Typography variant="subtitle1" sx={{ fontWeight: 800, color: "primary.main" }}>医生工作台</Typography>
            <Typography variant="caption" color="text.secondary">{doctorName || doctorId}</Typography>
          </Box>

          {/* Nav */}
          <Stack spacing={0.5} sx={{ flex: 1 }}>
            {NAV.map((item) => (
              <NavBtn key={item.key} active={activeSection === item.key} icon={item.icon} onClick={() => handleNav(item.key)} badgeCount={navBadge[item.key] || 0}>
                {item.label}
              </NavBtn>
            ))}
          </Stack>

          {/* Footer */}
          <Button
            startIcon={<LogoutIcon fontSize="small" />}
            onClick={handleLogout}
            size="small"
            sx={{ justifyContent: "flex-start", color: "text.secondary", mt: 1 }}
          >
            退出登录
          </Button>
        </Box>
      )}

      {/* Main content */}
      <Box sx={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden", pb: isMobile ? "56px" : 0 }}>
        {/* Topbar — hidden for chat (ChatSection has its own) */}
        {activeSection !== "chat" && (
          <Box sx={{ px: 3, py: 1.5, borderBottom: "1px solid #e2e8f0", backgroundColor: "#fff" }}>
            <Typography variant="subtitle2" sx={{ fontWeight: 700, color: "text.secondary" }}>
              {activeSection === "home" && "首页"}
              {activeSection === "patients" && "患者管理"}
              {activeSection === "tasks" && "任务列表"}
            </Typography>
          </Box>
        )}

        {/* Pending record confirmation banner */}
        {pendingRecord && (
          <Alert severity="warning" sx={{ mx: 2, mt: 1.5, borderRadius: 1.5 }}
            action={
              <Stack direction="row" spacing={1}>
                <Button size="small" color="success" variant="contained" onClick={handleConfirmPending}>确认保存</Button>
                <Button size="small" color="error" variant="outlined" onClick={handleAbandonPending}>撤销</Button>
              </Stack>
            }
          >
            <AlertTitle>待确认病历草稿</AlertTitle>
            患者：{pendingRecord.patient_name || "未关联"} · {pendingRecord.content_preview}
          </Alert>
        )}

        {/* Section content */}
        <Box sx={{ flex: 1, overflow: "hidden" }}>
          {activeSection === "chat" && <ChatSection doctorId={doctorId} onMessageCountChange={() => {}} />}
          {activeSection === "home" && <HomeSection doctorId={doctorId} navigate={navigate} />}
          {activeSection === "patients" && <PatientsSection doctorId={doctorId} />}
          {activeSection === "tasks" && <TasksSection doctorId={doctorId} />}
        </Box>
      </Box>

      {/* Bottom navigation — mobile only */}
      {isMobile && (
        <Box sx={{ position: "fixed", bottom: 0, left: 0, right: 0, zIndex: 10, borderTop: "1px solid #e2e8f0" }}>
          <BottomNavigation
            value={activeSection}
            onChange={(_, val) => handleNav(val)}
            sx={{ height: 56 }}
          >
            {NAV.map((item) => (
              <BottomNavigationAction
                key={item.key}
                label={item.label}
                value={item.key}
                icon={
                  item.key === "tasks" && pendingTaskCount > 0
                    ? <Badge badgeContent={pendingTaskCount} color="error">{item.icon}</Badge>
                    : item.icon
                }
                sx={{ minWidth: 0, fontSize: 10 }}
              />
            ))}
          </BottomNavigation>
        </Box>
      )}

      {/* Confirm success snackbar */}
      <Snackbar
        open={confirmSnackbar}
        autoHideDuration={3000}
        onClose={() => setConfirmSnackbar(false)}
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
      >
        <Alert onClose={() => setConfirmSnackbar(false)} severity="success" sx={{ width: "100%" }}>
          病历已保存
        </Alert>
      </Snackbar>

      {/* First-time onboarding dialog — not dismissable */}
      <Dialog open={showOnboarding} maxWidth="xs" fullWidth>
        <DialogTitle>欢迎，请完成初始设置</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label="您的姓名"
              value={onboardName}
              onChange={(e) => setOnboardName(e.target.value)}
              fullWidth
              autoFocus
              required
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button
            variant="contained"
            disabled={!onboardName.trim() || onboardSaving}
            onClick={handleOnboardSubmit}
          >
            {onboardSaving ? "保存中..." : "完成设置"}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
