/**
 * 任务列表面板：按状态分组展示医疗任务，支持新建、完成、推迟和取消操作。
 */
import { useCallback, useEffect, useState } from "react";
import {
  Alert, Box, Button, CircularProgress, Dialog, DialogActions,
  DialogContent, DialogTitle, MenuItem, Stack, TextField, Typography,
} from "@mui/material";
import useMediaQuery from "@mui/material/useMediaQuery";
import { useTheme } from "@mui/material/styles";
import AssignmentOutlinedIcon from "@mui/icons-material/AssignmentOutlined";
import EventRepeatOutlinedIcon from "@mui/icons-material/EventRepeatOutlined";
import MedicationOutlinedIcon from "@mui/icons-material/MedicationOutlined";
import BiotechOutlinedIcon from "@mui/icons-material/BiotechOutlined";
import TransferWithinAStationOutlinedIcon from "@mui/icons-material/TransferWithinAStationOutlined";
import MonitorHeartOutlinedIcon from "@mui/icons-material/MonitorHeartOutlined";
import EventAvailableOutlinedIcon from "@mui/icons-material/EventAvailableOutlined";
import CalendarTodayOutlinedIcon from "@mui/icons-material/CalendarTodayOutlined";
import CheckCircleOutlinedIcon from "@mui/icons-material/CheckCircleOutlined";
import CancelOutlinedIcon from "@mui/icons-material/CancelOutlined";
import { getTasks, patchTask, postponeTask, createTask, getPatients } from "../../api";
import { TASK_TYPE_LABEL, TASK_STATUS_OPTS } from "./constants";

const TASK_TYPE_ICON_COLOR = {
  follow_up: "#07C160", medication: "#5b9bd5", lab_review: "#e8833a",
  referral: "#9b59b6", imaging: "#1890ff", appointment: "#16a085", general: "#8e44ad",
};

const TASK_TYPE_ICON = {
  follow_up: EventRepeatOutlinedIcon, medication: MedicationOutlinedIcon,
  lab_review: BiotechOutlinedIcon, referral: TransferWithinAStationOutlinedIcon,
  imaging: MonitorHeartOutlinedIcon, appointment: EventAvailableOutlinedIcon,
  general: AssignmentOutlinedIcon,
};

function tomorrowStr() {
  const d = new Date();
  d.setDate(d.getDate() + 1);
  return d.toISOString().slice(0, 10);
}

function taskDateGroup(task, today, tomorrow, weekEnd) {
  if (!task.due_at) return "无截止日期";
  const d = new Date(task.due_at); d.setHours(0, 0, 0, 0);
  if (d < today) return "已逾期";
  if (d.getTime() === today.getTime()) return "今天";
  if (d.getTime() === tomorrow.getTime()) return "明天";
  if (d < weekEnd) return "本周";
  return "之后";
}

function TaskActions({ task, onComplete, onPostpone, onCancel }) {
  if (task.status !== "pending") return null;
  return (
    <Box sx={{ display: "flex", gap: 2, mt: 0.8, alignItems: "center" }}>
      <Box onClick={() => onComplete(task.id, "completed")}
        sx={{ display: "flex", alignItems: "center", gap: 0.4, cursor: "pointer", "&:active": { opacity: 0.6 } }}>
        <CheckCircleOutlinedIcon sx={{ fontSize: 14, color: "#07C160" }} />
        <Typography sx={{ fontSize: 12, color: "#07C160" }}>完成</Typography>
      </Box>
      <Box onClick={(e) => onPostpone(e, task.id)}
        sx={{ display: "flex", alignItems: "center", gap: 0.4, cursor: "pointer", "&:active": { opacity: 0.6 } }}>
        <CalendarTodayOutlinedIcon sx={{ fontSize: 14, color: "#999" }} />
        <Typography sx={{ fontSize: 12, color: "#999" }}>推迟</Typography>
      </Box>
      <Box onClick={() => onCancel(task.id)}
        sx={{ display: "flex", alignItems: "center", gap: 0.4, cursor: "pointer", "&:active": { opacity: 0.6 } }}>
        <CancelOutlinedIcon sx={{ fontSize: 14, color: "#ccc" }} />
        <Typography sx={{ fontSize: 12, color: "#ccc" }}>取消</Typography>
      </Box>
    </Box>
  );
}

function TaskRow({ task, isOverdue, onComplete, onPostpone, onCancel }) {
  const iconColor = TASK_TYPE_ICON_COLOR[task.task_type] || "#999";
  const TaskIcon = TASK_TYPE_ICON[task.task_type] || AssignmentOutlinedIcon;
  return (
    <Box sx={{ display: "flex", alignItems: "flex-start", px: 2, py: 1.4 }}>
      <Box sx={{ width: 40, height: 40, borderRadius: "10px", bgcolor: iconColor,
        display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, mr: 1.5, mt: 0.3 }}>
        <TaskIcon sx={{ color: "#fff", fontSize: 22 }} />
      </Box>
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Box sx={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 1 }}>
          <Typography variant="body2" sx={{ fontWeight: 600, color: isOverdue ? "#e74c3c" : "text.primary", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: 1 }}>
            {task.title || TASK_TYPE_LABEL[task.task_type] || task.task_type}
          </Typography>
          {task.due_at && (
            <Typography variant="caption" sx={{ color: isOverdue ? "#e74c3c" : "#bbb", flexShrink: 0, fontSize: 11 }}>
              {task.due_at.slice(5, 10)}
            </Typography>
          )}
        </Box>
        {task.content && (
          <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.2, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {task.content}
          </Typography>
        )}
        {task.patient_name && (
          <Typography variant="caption" sx={{ color: "#999", display: "block", mt: 0.2 }}>
            {task.patient_name}
          </Typography>
        )}
        <TaskActions task={task} onComplete={onComplete} onPostpone={onPostpone} onCancel={onCancel} />
      </Box>
    </Box>
  );
}

function PostponeDialog({ open, isMobile, postponeDate, onChange, onClose, onConfirm }) {
  return (
    <Dialog open={open} onClose={onClose}
      PaperProps={{ sx: isMobile
        ? { position: "fixed", bottom: 0, left: 0, right: 0, m: 0, borderRadius: "16px 16px 0 0", width: "100%" }
        : { borderRadius: 2, minWidth: 240 }
      }}
      sx={isMobile ? { "& .MuiDialog-container": { alignItems: "flex-end" } } : {}}>
      <Box sx={{ p: 2.5 }}>
        <Typography sx={{ fontWeight: 600, fontSize: 15, mb: 1.5, color: "#333" }}>选择新到期日</Typography>
        <TextField type="date" size="small" fullWidth InputLabelProps={{ shrink: true }}
          value={postponeDate} onChange={(e) => onChange(e.target.value)} sx={{ mb: 2 }} />
        <Box sx={{ display: "flex", gap: 1.5 }}>
          <Box onClick={onClose}
            sx={{ flex: 1, textAlign: "center", py: 1.2, borderRadius: 1.5, bgcolor: "#f5f5f5", cursor: "pointer", fontSize: 14, color: "#666", "&:active": { opacity: 0.7 } }}>
            取消
          </Box>
          <Box onClick={postponeDate ? onConfirm : undefined}
            sx={{ flex: 1, textAlign: "center", py: 1.2, borderRadius: 1.5, bgcolor: postponeDate ? "#07C160" : "#e0e0e0", cursor: postponeDate ? "pointer" : "default", fontSize: 14, color: "#fff", fontWeight: 600, "&:active": postponeDate ? { opacity: 0.7 } : {} }}>
            确认
          </Box>
        </Box>
      </Box>
    </Dialog>
  );
}

function CancelDialog({ open, isMobile, onClose, onConfirm }) {
  return (
    <Dialog open={open} onClose={onClose}
      PaperProps={{ sx: isMobile
        ? { position: "fixed", bottom: 0, left: 0, right: 0, m: 0, borderRadius: "16px 16px 0 0", width: "100%" }
        : { borderRadius: 2, minWidth: 240 }
      }}
      sx={isMobile ? { "& .MuiDialog-container": { alignItems: "flex-end" } } : {}}>
      <Box sx={{ p: 2.5 }}>
        <Typography sx={{ fontWeight: 600, fontSize: 15, mb: 0.5, textAlign: "center", color: "#333" }}>取消任务</Typography>
        <Typography sx={{ fontSize: 13, color: "#999", mb: 2.5, textAlign: "center" }}>此任务将被标记为已取消</Typography>
        <Box sx={{ display: "flex", gap: 1.5 }}>
          <Box onClick={onClose}
            sx={{ flex: 1, textAlign: "center", py: 1.2, borderRadius: 1.5, bgcolor: "#f5f5f5", cursor: "pointer", fontSize: 14, color: "#666", "&:active": { opacity: 0.7 } }}>
            保留
          </Box>
          <Box onClick={onConfirm}
            sx={{ flex: 1, textAlign: "center", py: 1.2, borderRadius: 1.5, bgcolor: "#e74c3c", cursor: "pointer", fontSize: 14, color: "#fff", fontWeight: 600, "&:active": { opacity: 0.7 } }}>
            确认取消
          </Box>
        </Box>
      </Box>
    </Dialog>
  );
}

function CreateTaskDialog({ open, isMobile, createForm, creating, createError, patientOptions, onFieldChange, onCreate, onClose }) {
  return (
    <Dialog open={open} onClose={onClose} maxWidth="xs" fullWidth fullScreen={isMobile}>
      <DialogTitle sx={{ fontWeight: 700 }}>新建任务</DialogTitle>
      <DialogContent dividers>
        {createError && <Alert severity="error" sx={{ mb: 2 }}>{createError}</Alert>}
        <Stack spacing={2.5} sx={{ mt: 0.5 }}>
          <TextField select label="任务类型" size="small" fullWidth
            value={createForm.taskType}
            onChange={(e) => onFieldChange("taskType", e.target.value)}>
            {Object.entries(TASK_TYPE_LABEL).map(([k, v]) => {
              const ItemIcon = TASK_TYPE_ICON[k] || AssignmentOutlinedIcon;
              const ic = TASK_TYPE_ICON_COLOR[k] || "#999";
              return (
                <MenuItem key={k} value={k} sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                  <ItemIcon sx={{ fontSize: 18, color: ic }} />
                  {v}
                </MenuItem>
              );
            })}
          </TextField>
          <TextField label="标题（可选）" size="small" fullWidth
            value={createForm.title} onChange={(e) => onFieldChange("title", e.target.value)} />
          <TextField label="到期日期" size="small" fullWidth type="date"
            InputLabelProps={{ shrink: true }}
            value={createForm.dueAt} onChange={(e) => onFieldChange("dueAt", e.target.value)} />
          <TextField select size="small" fullWidth label="关联患者（可选）"
            value={createForm.patientId} onChange={(e) => onFieldChange("patientId", e.target.value)}>
            <MenuItem value=""><em>不关联患者</em></MenuItem>
            {patientOptions.filter((p) => !createForm.patientSearch || p.name.includes(createForm.patientSearch)).map((p) => (
              <MenuItem key={p.id} value={String(p.id)}>{p.name}</MenuItem>
            ))}
          </TextField>
          <TextField label="备注/说明（可选）" size="small" fullWidth multiline minRows={2}
            value={createForm.content} onChange={(e) => onFieldChange("content", e.target.value)} />
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} color="inherit">取消</Button>
        <Button onClick={onCreate} variant="contained" disabled={creating}>
          {creating ? <CircularProgress size={16} /> : "创建"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

const GROUP_ORDER = ["已逾期", "今天", "明天", "本周", "之后", "无截止日期"];

function useTasksState(doctorId) {
  const [tasks, setTasks] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [statusFilter, setStatusFilter] = useState("pending");
  const [createOpen, setCreateOpen] = useState(false);
  const [createForm, setCreateForm] = useState({ taskType: "follow_up", title: "", dueAt: tomorrowStr(), patientId: "", patientSearch: "", content: "" });
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState("");
  const [patientOptions, setPatientOptions] = useState([]);
  const [postponeOpen, setPostponeOpen] = useState(false);
  const [postponeTaskId, setPostponeTaskId] = useState(null);
  const [postponeDate, setPostponeDate] = useState("");
  const [cancelConfirmId, setCancelConfirmId] = useState(null);

  const load = useCallback(() => {
    setLoading(true); setError("");
    getTasks(doctorId, statusFilter || null).then((d) => setTasks(Array.isArray(d) ? d : (d.items || []))).catch((e) => setError(e.message || "任务加载失败")).finally(() => setLoading(false));
  }, [doctorId, statusFilter]);

  useEffect(() => { load(); }, [load]);

  async function handleStatus(taskId, status) {
    try { await patchTask(taskId, doctorId, status); load(); }
    catch (e) { setError(e.message || "任务状态更新失败"); }
  }
  async function handleCreate() {
    if (!createForm.taskType) return;
    setCreating(true); setCreateError("");
    try {
      await createTask(doctorId, { taskType: createForm.taskType, title: createForm.title || TASK_TYPE_LABEL[createForm.taskType] || createForm.taskType, dueAt: createForm.dueAt || undefined, patientId: createForm.patientId ? Number(createForm.patientId) : undefined, content: createForm.content || undefined });
      setCreateOpen(false); setCreateForm({ taskType: "follow_up", title: "", dueAt: tomorrowStr(), patientId: "", patientSearch: "", content: "" }); load();
    } catch (e) { setCreateError(e.message || "创建失败"); } finally { setCreating(false); }
  }
  async function handleConfirmPostpone() {
    if (!postponeDate || !postponeTaskId) return;
    try { await postponeTask(postponeTaskId, doctorId, postponeDate); setPostponeOpen(false); setPostponeTaskId(null); setPostponeDate(""); load(); }
    catch (e) { setError(e.message || "推迟失败"); setPostponeOpen(false); }
  }

  return { tasks, loading, error, setError, statusFilter, setStatusFilter, createOpen, setCreateOpen, createForm, setCreateForm, creating, createError, setCreateError, patientOptions, setPatientOptions, postponeOpen, setPostponeOpen, postponeTaskId, setPostponeTaskId, postponeDate, setPostponeDate, cancelConfirmId, setCancelConfirmId, load, handleStatus, handleCreate, handleConfirmPostpone };
}

function TasksHeader({ statusFilter, loading, onFilterChange, onOpenCreate }) {
  return (
    <Box sx={{ display: "flex", alignItems: "center", px: 2, height: 48, bgcolor: "#fff", borderBottom: "1px solid #e5e5e5", flexShrink: 0 }}>
      <Box sx={{ display: "flex", gap: 0.6, flex: 1, overflowX: "auto", WebkitOverflowScrolling: "touch", "&::-webkit-scrollbar": { display: "none" } }}>
        {TASK_STATUS_OPTS.map((o) => (
          <Box key={o.value} onClick={() => onFilterChange(o.value)}
            sx={{ px: 1.4, py: 0.4, borderRadius: "12px", cursor: "pointer", flexShrink: 0, fontSize: 13,
              bgcolor: statusFilter === o.value ? "#07C160" : "transparent",
              color: statusFilter === o.value ? "#fff" : "#555",
              fontWeight: statusFilter === o.value ? 600 : 400,
              "&:active": { opacity: 0.7 } }}>
            {o.label}
          </Box>
        ))}
      </Box>
      {loading && <CircularProgress size={14} sx={{ mr: 1, color: "#07C160" }} />}
      <Box onClick={onOpenCreate}
        sx={{ width: 28, height: 28, borderRadius: "50%", bgcolor: "#07C160", display: "flex", alignItems: "center", justifyContent: "center", cursor: "pointer", flexShrink: 0, "&:active": { opacity: 0.8 } }}>
        <Typography sx={{ color: "#fff", fontSize: 20, lineHeight: 1, mt: "-2px" }}>+</Typography>
      </Box>
    </Box>
  );
}

function TaskGroupList({ tasks, loading, error, taskGroups, sortedGroups, onError, onComplete, onPostpone, onCancel }) {
  return (
    <Box sx={{ flex: 1, overflowY: "auto" }}>
      {error && <Box sx={{ px: 2, pt: 1.5 }}><Alert severity="error" onClose={() => onError("")}>{error}</Alert></Box>}
      {!loading && !error && tasks.length === 0 && (
        <Box sx={{ display: "flex", flexDirection: "column", alignItems: "center", py: 8, gap: 1, px: 2 }}>
          <AssignmentOutlinedIcon sx={{ fontSize: 48, color: "#ccc" }} />
          <Typography variant="body2" color="text.disabled" sx={{ fontWeight: 500 }}>暂无任务</Typography>
          <Typography variant="caption" color="text.disabled" sx={{ textAlign: "center", maxWidth: 200 }}>在聊天中说「今日任务」或点击 + 新建</Typography>
        </Box>
      )}
      {sortedGroups.map((group) => (
        <Box key={group}>
          <Box sx={{ px: 2, py: 0.6, pt: 1.2 }}>
            <Typography sx={{ fontSize: 12, color: group === "已逾期" ? "#e74c3c" : "#999", fontWeight: 500 }}>{group}</Typography>
          </Box>
          <Box sx={{ bgcolor: "#fff" }}>
            {taskGroups[group].map((task, idx) => (
              <Box key={task.id} sx={{ borderBottom: idx < taskGroups[group].length - 1 ? "1px solid #f2f2f2" : "none" }}>
                <TaskRow task={task} isOverdue={group === "已逾期"} onComplete={onComplete} onPostpone={onPostpone} onCancel={onCancel} />
              </Box>
            ))}
          </Box>
        </Box>
      ))}
      <Box sx={{ height: 24 }} />
    </Box>
  );
}

export default function TasksSection({ doctorId }) {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down("sm"));
  const { tasks, loading, error, setError, statusFilter, setStatusFilter, createOpen, setCreateOpen, createForm, setCreateForm, creating, createError, setCreateError, patientOptions, setPatientOptions, postponeOpen, setPostponeOpen, postponeTaskId, setPostponeTaskId, postponeDate, setPostponeDate, cancelConfirmId, setCancelConfirmId, handleStatus, handleCreate, handleConfirmPostpone } = useTasksState(doctorId);

  const today = new Date(); today.setHours(0, 0, 0, 0);
  const tomorrow = new Date(today); tomorrow.setDate(today.getDate() + 1);
  const weekEnd = new Date(today); weekEnd.setDate(today.getDate() + 7);
  const taskGroups = {};
  tasks.forEach((t) => { const g = taskDateGroup(t, today, tomorrow, weekEnd); (taskGroups[g] = taskGroups[g] || []).push(t); });
  const sortedGroups = GROUP_ORDER.filter((g) => taskGroups[g]);

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%", bgcolor: "#f7f7f7" }}>
      <TasksHeader statusFilter={statusFilter} loading={loading} onFilterChange={setStatusFilter}
        onOpenCreate={() => { setCreateOpen(true); setCreateError(""); getPatients(doctorId, {}, 200).then((d) => setPatientOptions(d.items || [])).catch(() => {}); }} />
      <TaskGroupList tasks={tasks} loading={loading} error={error} taskGroups={taskGroups} sortedGroups={sortedGroups}
        onError={setError} onComplete={handleStatus}
        onPostpone={(e, id) => { setPostponeOpen(true); setPostponeTaskId(id); setPostponeDate(""); }}
        onCancel={(id) => setCancelConfirmId(id)} />
      <PostponeDialog open={Boolean(postponeOpen)} isMobile={isMobile} postponeDate={postponeDate} onChange={setPostponeDate}
        onClose={() => { setPostponeOpen(false); setPostponeTaskId(null); setPostponeDate(""); }} onConfirm={handleConfirmPostpone} />
      <CancelDialog open={Boolean(cancelConfirmId)} isMobile={isMobile} onClose={() => setCancelConfirmId(null)}
        onConfirm={() => { handleStatus(cancelConfirmId, "cancelled"); setCancelConfirmId(null); }} />
      <CreateTaskDialog open={createOpen} isMobile={isMobile} createForm={createForm} creating={creating} createError={createError}
        patientOptions={patientOptions} onFieldChange={(k, v) => setCreateForm((f) => ({ ...f, [k]: v }))} onCreate={handleCreate} onClose={() => setCreateOpen(false)} />
    </Box>
  );
}
