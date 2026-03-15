/**
 * 任务列表面板：按状态分组展示医疗任务，支持新建、完成、推迟和取消操作。
 * 支持滑动操作、分段控制（今天/待办/已完成）和任务详情页。
 */
import { useCallback, useEffect, useRef, useState } from "react";
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
import CancelOutlinedIcon from "@mui/icons-material/CancelOutlined";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import { getTasks, patchTask, postponeTask, createTask, getPatients } from "../../api";
import { TASK_TYPE_LABEL, TASK_STATUS_LABEL, TASK_SEGMENT_OPTS } from "./constants";

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

function todayStr() {
  return new Date().toISOString().slice(0, 10);
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

function SwipeableTaskRow({ children, onSwipeComplete, onSwipeCancel }) {
  const startXRef = useRef(null);
  const [offsetX, setOffsetX] = useState(0);
  const [revealed, setRevealed] = useState(false);
  const THRESHOLD = 70;
  const ACTION_WIDTH = 140;

  function handleTouchStart(e) {
    startXRef.current = e.touches[0].clientX;
  }
  function handleTouchMove(e) {
    if (startXRef.current === null) return;
    const diff = startXRef.current - e.touches[0].clientX;
    if (diff > 0) {
      setOffsetX(Math.min(diff, ACTION_WIDTH));
    } else {
      setOffsetX(0);
    }
  }
  function handleTouchEnd() {
    if (offsetX >= THRESHOLD) {
      setOffsetX(ACTION_WIDTH);
      setRevealed(true);
    } else {
      setOffsetX(0);
      setRevealed(false);
    }
    startXRef.current = null;
  }
  function handleReset() {
    setOffsetX(0);
    setRevealed(false);
  }

  return (
    <Box sx={{ position: "relative", overflow: "hidden" }}>
      <Box sx={{
        position: "absolute", right: 0, top: 0, bottom: 0,
        display: "flex", width: ACTION_WIDTH,
      }}>
        <Box onClick={() => { onSwipeComplete(); handleReset(); }}
          sx={{ flex: 1, bgcolor: "#07C160", display: "flex",
            alignItems: "center", justifyContent: "center",
            color: "#fff", fontSize: 14, fontWeight: 600 }}>
          完成
        </Box>
        <Box onClick={() => { onSwipeCancel(); handleReset(); }}
          sx={{ flex: 1, bgcolor: "#b0b0b0", display: "flex",
            alignItems: "center", justifyContent: "center",
            color: "#fff", fontSize: 14, fontWeight: 600 }}>
          取消
        </Box>
      </Box>
      <Box
        onTouchStart={handleTouchStart}
        onTouchMove={handleTouchMove}
        onTouchEnd={handleTouchEnd}
        onClick={revealed ? handleReset : undefined}
        sx={{
          transform: `translateX(-${offsetX}px)`,
          transition: startXRef.current !== null ? "none" : "transform 0.2s ease",
          bgcolor: "#fff", position: "relative", zIndex: 1,
        }}
      >
        {children}
      </Box>
    </Box>
  );
}

function TaskActions({ task, isOverdue, onComplete, onPostpone, onCancel }) {
  if (task.status !== "pending") return null;
  return (
    <Box sx={{ display: "flex", gap: 2, mt: 0.8, alignItems: "center" }}>
      <Box onClick={(e) => { e.stopPropagation(); onComplete(task.id, "completed"); }}
        sx={{ display: "flex", alignItems: "center", gap: 0.6, cursor: "pointer", "&:active": { opacity: 0.6 } }}>
        <Box sx={{ width: 20, height: 20, borderRadius: "50%", border: isOverdue ? "2px solid #FA5151" : "2px solid #07C160", flexShrink: 0 }} />
        <Typography sx={{ fontSize: 12, color: "#07C160" }}>完成</Typography>
      </Box>
      <Box onClick={(e) => { e.stopPropagation(); onPostpone(e, task.id); }}
        sx={{ display: "flex", alignItems: "center", gap: 0.4, cursor: "pointer", "&:active": { opacity: 0.6 } }}>
        <CalendarTodayOutlinedIcon sx={{ fontSize: 14, color: "#999" }} />
        <Typography sx={{ fontSize: 12, color: "#999" }}>推迟</Typography>
      </Box>
      <Box onClick={(e) => { e.stopPropagation(); onCancel(task.id); }}
        sx={{ display: "flex", alignItems: "center", gap: 0.4, cursor: "pointer", "&:active": { opacity: 0.6 } }}>
        <CancelOutlinedIcon sx={{ fontSize: 14, color: "#ccc" }} />
        <Typography sx={{ fontSize: 12, color: "#ccc" }}>取消</Typography>
      </Box>
    </Box>
  );
}

function TaskRow({ task, isOverdue, onComplete, onPostpone, onCancel, onClick }) {
  const iconColor = TASK_TYPE_ICON_COLOR[task.task_type] || "#999";
  const TaskIcon = TASK_TYPE_ICON[task.task_type] || AssignmentOutlinedIcon;
  return (
    <Box onClick={onClick} sx={{ display: "flex", alignItems: "flex-start", px: 2, py: 1.4, cursor: "pointer", "&:active": { bgcolor: "#f9f9f9" } }}>
      <Box sx={{ width: 40, height: 40, borderRadius: "4px", bgcolor: iconColor,
        display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, mr: 1.5, mt: 0.3 }}>
        <TaskIcon sx={{ color: "#fff", fontSize: 22 }} />
      </Box>
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Box sx={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 1 }}>
          <Typography variant="body2" sx={{ fontSize: 15, fontWeight: 500, color: isOverdue ? "#FA5151" : "text.primary", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: 1 }}>
            {task.title || TASK_TYPE_LABEL[task.task_type] || task.task_type}
          </Typography>
          {task.due_at && (
            <Typography variant="caption" sx={{ color: isOverdue ? "#FA5151" : "#bbb", flexShrink: 0, fontSize: 11 }}>
              {task.due_at.slice(5, 10)}
            </Typography>
          )}
        </Box>
        {task.content && (
          <Typography variant="caption" sx={{ fontSize: 13, color: "#999", display: "block", mt: 0.2, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {task.content}
          </Typography>
        )}
        {task.patient_name && (
          <Typography variant="caption" sx={{ color: "#999", fontSize: 13, display: "block", mt: 0.2 }}>
            {task.patient_name}
          </Typography>
        )}
        <TaskActions task={task} isOverdue={isOverdue} onComplete={onComplete} onPostpone={onPostpone} onCancel={onCancel} />
      </Box>
    </Box>
  );
}

function DetailField({ label, value }) {
  return (
    <Box sx={{ display: "flex", py: 0.8, borderBottom: "1px solid #f8f8f8" }}>
      <Typography sx={{ fontSize: 14, color: "#999", width: 80, flexShrink: 0 }}>{label}</Typography>
      <Typography sx={{ fontSize: 14, color: "#333", flex: 1 }}>{value || "\u2014"}</Typography>
    </Box>
  );
}

function TaskDetailView({ task, onBack, onComplete, onCancel }) {
  const iconColor = TASK_TYPE_ICON_COLOR[task.task_type] || "#999";
  const TaskIcon = TASK_TYPE_ICON[task.task_type] || AssignmentOutlinedIcon;
  const statusLabel = TASK_STATUS_LABEL[task.status] || task.status;
  const isActionable = task.status === "pending";

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%", bgcolor: "#f7f7f7" }}>
      <Box sx={{ display: "flex", alignItems: "center", height: 48, px: 1,
        bgcolor: "#fff", borderBottom: "1px solid #e5e5e5", flexShrink: 0 }}>
        <Box onClick={onBack} sx={{ display: "flex", alignItems: "center",
          gap: 0.3, cursor: "pointer", color: "#07C160", pr: 2, py: 1 }}>
          <ArrowBackIcon sx={{ fontSize: 20 }} />
          <Typography sx={{ fontSize: 15, color: "#07C160" }}>任务</Typography>
        </Box>
        <Typography sx={{ flex: 1, textAlign: "center", fontWeight: 600,
          fontSize: 16, mr: 5 }}>任务详情</Typography>
      </Box>
      <Box sx={{ flex: 1, overflowY: "auto", p: 2 }}>
        <Box sx={{ bgcolor: "#fff", borderRadius: 2, p: 2.5, mb: 1.5 }}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, mb: 2 }}>
            <Box sx={{ width: 48, height: 48, borderRadius: "12px",
              bgcolor: iconColor, display: "flex", alignItems: "center",
              justifyContent: "center" }}>
              <TaskIcon sx={{ color: "#fff", fontSize: 26 }} />
            </Box>
            <Box>
              <Typography sx={{ fontWeight: 700, fontSize: 17 }}>
                {task.title || TASK_TYPE_LABEL[task.task_type]}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                {TASK_TYPE_LABEL[task.task_type]}
              </Typography>
            </Box>
          </Box>
          {task.patient_name && <DetailField label="关联患者" value={task.patient_name} />}
          <DetailField label="创建时间" value={task.created_at?.slice(0, 16).replace("T", " ")} />
          {task.due_at && <DetailField label="截止时间" value={task.due_at.slice(0, 16).replace("T", " ")} />}
          <DetailField label="状态" value={statusLabel} />
          {task.content && <DetailField label="备注" value={task.content} />}
        </Box>
      </Box>
      {isActionable && (
        <Box sx={{ p: 2, bgcolor: "#fff", borderTop: "1px solid #f2f2f2" }}>
          <Box onClick={() => onComplete(task.id, "completed")}
            sx={{ py: 1.3, borderRadius: 2, bgcolor: "#07C160", height: 44, display: "flex", alignItems: "center", justifyContent: "center",
              color: "#fff", fontWeight: 600, fontSize: 16, mb: 1, cursor: "pointer",
              "&:active": { opacity: 0.8 } }}>
            标记完成
          </Box>
          <Box sx={{ display: "flex", gap: 1 }}>
            <Box sx={{ flex: 1, py: 1.1, borderRadius: 2, border: "1px solid #e5e5e5",
              textAlign: "center", color: "#333", fontSize: 14, cursor: "pointer",
              "&:active": { bgcolor: "#f5f5f5" } }}>
              编辑
            </Box>
            <Box onClick={() => onCancel(task.id)}
              sx={{ flex: 1, py: 1.1, borderRadius: 2, textAlign: "center",
                color: "#e74c3c", fontSize: 14, cursor: "pointer",
                "&:active": { bgcolor: "#fef2f2" } }}>
              取消任务
            </Box>
          </Box>
        </Box>
      )}
    </Box>
  );
}

function PostponeDialog({ open, isMobile, postponeDate, onChange, onClose, onConfirm }) {
  return (
    <Dialog open={open} onClose={onClose}
      PaperProps={{ sx: isMobile
        ? { position: "fixed", bottom: 0, left: 0, right: 0, m: 0, borderRadius: "12px 12px 0 0", width: "100%" }
        : { borderRadius: 2, minWidth: 240 }
      }}
      sx={isMobile ? { "& .MuiDialog-container": { alignItems: "flex-end" } } : {}}>
      <Box sx={{ p: 2.5 }}>
        <Typography sx={{ fontWeight: 600, fontSize: 15, mb: 1.5, color: "#333" }}>选择新到期日</Typography>
        <TextField type="date" size="small" fullWidth InputLabelProps={{ shrink: true }}
          value={postponeDate} onChange={(e) => onChange(e.target.value)} sx={{ mb: 2 }} />
        <Box sx={{ display: "flex", gap: 1.5 }}>
          <Box onClick={onClose}
            sx={{ flex: 1, textAlign: "center", py: 1.2, borderRadius: "4px", bgcolor: "#f5f5f5", cursor: "pointer", fontSize: 14, color: "#666", "&:active": { opacity: 0.7 } }}>
            取消
          </Box>
          <Box onClick={postponeDate ? onConfirm : undefined}
            sx={{ flex: 1, textAlign: "center", py: 1.2, borderRadius: "4px", bgcolor: postponeDate ? "#07C160" : "#e0e0e0", cursor: postponeDate ? "pointer" : "default", fontSize: 14, color: "#fff", fontWeight: 600, "&:active": postponeDate ? { opacity: 0.7 } : {} }}>
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
        ? { position: "fixed", bottom: 0, left: 0, right: 0, m: 0, borderRadius: "12px 12px 0 0", width: "100%" }
        : { borderRadius: 2, minWidth: 240 }
      }}
      sx={isMobile ? { "& .MuiDialog-container": { alignItems: "flex-end" } } : {}}>
      <Box sx={{ p: 2.5 }}>
        <Typography sx={{ fontWeight: 600, fontSize: 15, mb: 0.5, textAlign: "center", color: "#333" }}>取消任务</Typography>
        <Typography sx={{ fontSize: 13, color: "#999", mb: 2.5, textAlign: "center" }}>此任务将被标记为已取消</Typography>
        <Box sx={{ display: "flex", gap: 1.5 }}>
          <Box onClick={onClose}
            sx={{ flex: 1, textAlign: "center", py: 1.2, borderRadius: "4px", bgcolor: "#f5f5f5", cursor: "pointer", fontSize: 14, color: "#666", "&:active": { opacity: 0.7 } }}>
            保留
          </Box>
          <Box onClick={onConfirm}
            sx={{ flex: 1, textAlign: "center", py: 1.2, borderRadius: "4px", bgcolor: "#FA5151", cursor: "pointer", fontSize: 14, color: "#fff", fontWeight: 600, "&:active": { opacity: 0.7 } }}>
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
  const [segment, setSegment] = useState("today");
  const [detailTask, setDetailTask] = useState(null);
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
    if (segment === "done") {
      Promise.all([
        getTasks(doctorId, "completed"),
        getTasks(doctorId, "cancelled"),
      ]).then(([c, x]) => {
        const completed = Array.isArray(c) ? c : (c.items || []);
        const cancelled = Array.isArray(x) ? x : (x.items || []);
        const merged = [...completed, ...cancelled].sort((a, b) =>
          (b.updated_at || b.created_at || "").localeCompare(a.updated_at || a.created_at || "")
        );
        setTasks(merged);
      }).catch((e) => setError(e.message || "任务加载失败")).finally(() => setLoading(false));
    } else {
      getTasks(doctorId, "pending").then((d) => {
        const all = Array.isArray(d) ? d : (d.items || []);
        const td = todayStr();
        if (segment === "today") {
          setTasks(all.filter((t) => {
            if (!t.due_at) return false;
            const dStr = t.due_at.slice(0, 10);
            return dStr <= td;
          }));
        } else {
          setTasks(all.filter((t) => {
            if (!t.due_at) return true;
            return t.due_at.slice(0, 10) > td;
          }));
        }
      }).catch((e) => setError(e.message || "任务加载失败")).finally(() => setLoading(false));
    }
  }, [doctorId, segment]);

  useEffect(() => { load(); }, [load]);

  async function handleStatus(taskId, status) {
    try { await patchTask(taskId, doctorId, status); setDetailTask(null); load(); }
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

  return { tasks, loading, error, setError, segment, setSegment, detailTask, setDetailTask, createOpen, setCreateOpen, createForm, setCreateForm, creating, createError, setCreateError, patientOptions, setPatientOptions, postponeOpen, setPostponeOpen, postponeTaskId, setPostponeTaskId, postponeDate, setPostponeDate, cancelConfirmId, setCancelConfirmId, load, handleStatus, handleCreate, handleConfirmPostpone };
}

function SegmentControl({ value, options, onChange }) {
  return (
    <Box sx={{
      display: "flex", bgcolor: "#f2f2f2", borderRadius: "8px",
      p: "3px", flex: 1,
    }}>
      {options.map((opt) => (
        <Box key={opt.value} onClick={() => onChange(opt.value)}
          sx={{
            flex: 1, textAlign: "center", py: 0.6,
            borderRadius: "6px", fontSize: 13, fontWeight: 600,
            cursor: "pointer", transition: "all 0.15s ease",
            bgcolor: value === opt.value ? "#fff" : "transparent",
            color: value === opt.value ? "#07C160" : "#999",
            boxShadow: value === opt.value ? "0 1px 3px rgba(0,0,0,0.1)" : "none",
          }}>
          {opt.label}
        </Box>
      ))}
    </Box>
  );
}

function TasksHeader({ segment, loading, onSegmentChange, onOpenCreate }) {
  return (
    <Box sx={{ display: "flex", alignItems: "center", px: 2, height: 48, bgcolor: "#fff", borderBottom: "0.5px solid #d9d9d9", flexShrink: 0, gap: 1 }}>
      <SegmentControl value={segment} options={TASK_SEGMENT_OPTS} onChange={onSegmentChange} />
      {loading && <CircularProgress size={14} sx={{ color: "#07C160", flexShrink: 0 }} />}
      <Box onClick={onOpenCreate}
        sx={{ width: 28, height: 28, borderRadius: "4px", bgcolor: "#07C160", display: "flex", alignItems: "center", justifyContent: "center", cursor: "pointer", flexShrink: 0, "&:active": { opacity: 0.8 } }}>
        <Typography sx={{ color: "#fff", fontSize: 20, lineHeight: 1, mt: "-2px" }}>+</Typography>
      </Box>
    </Box>
  );
}

function AppointmentRow({ task, onClick }) {
  const timeStr = task.due_at ? task.due_at.slice(11, 16) : "--:--";
  return (
    <Box onClick={onClick} sx={{ display: "flex", px: 2, py: 1.2, alignItems: "center", cursor: "pointer", "&:active": { bgcolor: "#f9f9f9" } }}>
      <Typography sx={{ fontSize: 14, fontWeight: 600, color: "#07C160", width: 50, flexShrink: 0 }}>
        {timeStr}
      </Typography>
      <Box sx={{ flex: 1, ml: 1 }}>
        <Typography sx={{ fontSize: 14, fontWeight: 500 }}>
          {task.title || task.patient_name || "预约"}
        </Typography>
        {task.content && (
          <Typography variant="caption" color="text.secondary">
            {task.content}
          </Typography>
        )}
      </Box>
    </Box>
  );
}

function TodoRow({ task, onComplete, onClick }) {
  return (
    <Box onClick={onClick} sx={{ display: "flex", px: 2, py: 1.2, alignItems: "center", cursor: "pointer", "&:active": { bgcolor: "#f9f9f9" } }}>
      <Box onClick={(e) => { e.stopPropagation(); onComplete(task.id, "completed"); }}
        sx={{
          width: 22, height: 22, borderRadius: "50%",
          border: "2px solid #ddd", flexShrink: 0, cursor: "pointer",
          display: "flex", alignItems: "center", justifyContent: "center",
          "&:active": { borderColor: "#07C160" },
        }} />
      <Box sx={{ flex: 1, ml: 1.5 }}>
        <Typography sx={{ fontSize: 14 }}>
          {task.title || TASK_TYPE_LABEL[task.task_type] || task.task_type}
        </Typography>
        {task.patient_name && (
          <Typography variant="caption" color="text.secondary">
            {task.patient_name}
          </Typography>
        )}
      </Box>
    </Box>
  );
}

function TaskGroupList({ tasks, loading, error, segment, isMobile, taskGroups, sortedGroups, onError, onComplete, onPostpone, onCancel, onTaskClick }) {
  if (segment === "today") {
    const appointments = tasks.filter((t) => t.task_type === "appointment");
    const todos = tasks.filter((t) => t.task_type !== "appointment");
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
        {appointments.length > 0 && (
          <Box>
            <Box sx={{ px: 2, py: 0.6, pt: 1.2 }}>
              <Typography sx={{ fontSize: 12, color: "#999", fontWeight: 500 }}>预约</Typography>
            </Box>
            <Box sx={{ bgcolor: "#fff" }}>
              {appointments.map((task, idx) => (
                <Box key={task.id} sx={{ borderBottom: idx < appointments.length - 1 ? "0.5px solid #f0f0f0" : "none" }}>
                  <AppointmentRow task={task} onClick={() => onTaskClick(task)} />
                </Box>
              ))}
            </Box>
          </Box>
        )}
        {todos.length > 0 && (
          <Box>
            <Box sx={{ px: 2, py: 0.6, pt: 1.2 }}>
              <Typography sx={{ fontSize: 12, color: "#999", fontWeight: 500 }}>待办</Typography>
            </Box>
            <Box sx={{ bgcolor: "#fff" }}>
              {todos.map((task, idx) => {
                const row = (
                  <Box key={task.id} sx={{ borderBottom: idx < todos.length - 1 ? "0.5px solid #f0f0f0" : "none" }}>
                    <TodoRow task={task} onComplete={onComplete} onClick={() => onTaskClick(task)} />
                  </Box>
                );
                if (isMobile && task.status === "pending") {
                  return (
                    <SwipeableTaskRow key={task.id}
                      onSwipeComplete={() => onComplete(task.id, "completed")}
                      onSwipeCancel={() => onCancel(task.id)}>
                      {row}
                    </SwipeableTaskRow>
                  );
                }
                return row;
              })}
            </Box>
          </Box>
        )}
        <Box sx={{ height: 24 }} />
      </Box>
    );
  }

  if (segment === "done") {
    return (
      <Box sx={{ flex: 1, overflowY: "auto" }}>
        {error && <Box sx={{ px: 2, pt: 1.5 }}><Alert severity="error" onClose={() => onError("")}>{error}</Alert></Box>}
        {!loading && !error && tasks.length === 0 && (
          <Box sx={{ display: "flex", flexDirection: "column", alignItems: "center", py: 8, gap: 1, px: 2 }}>
            <AssignmentOutlinedIcon sx={{ fontSize: 48, color: "#ccc" }} />
            <Typography variant="body2" color="text.disabled" sx={{ fontWeight: 500 }}>暂无已完成任务</Typography>
          </Box>
        )}
        <Box sx={{ bgcolor: "#fff", mt: 0.5 }}>
          {tasks.map((task, idx) => (
            <Box key={task.id} onClick={() => onTaskClick(task)}
              sx={{ display: "flex", alignItems: "center", px: 2, py: 1.2,
                borderBottom: idx < tasks.length - 1 ? "0.5px solid #f0f0f0" : "none",
                cursor: "pointer", "&:active": { bgcolor: "#f9f9f9" } }}>
              <Box sx={{ flex: 1, minWidth: 0 }}>
                <Typography sx={{ fontSize: 14, color: "#999", textDecoration: "line-through",
                  overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {task.title || TASK_TYPE_LABEL[task.task_type] || task.task_type}
                </Typography>
                {task.patient_name && (
                  <Typography variant="caption" sx={{ color: "#ccc", fontSize: 12 }}>
                    {task.patient_name}
                  </Typography>
                )}
              </Box>
              <Typography sx={{ fontSize: 11, color: "#ccc", flexShrink: 0, ml: 1 }}>
                {task.status === "cancelled" ? "已取消" : "已完成"}
              </Typography>
            </Box>
          ))}
        </Box>
        <Box sx={{ height: 24 }} />
      </Box>
    );
  }

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
            <Typography sx={{ fontSize: 12, color: group === "已逾期" ? "#FA5151" : "#999", fontWeight: 500 }}>{group}</Typography>
          </Box>
          <Box sx={{ bgcolor: "#fff" }}>
            {taskGroups[group].map((task, idx) => {
              const rowContent = (
                <Box key={task.id} sx={{ borderBottom: idx < taskGroups[group].length - 1 ? "0.5px solid #f0f0f0" : "none" }}>
                  <TaskRow task={task} isOverdue={group === "已逾期"} onComplete={onComplete} onPostpone={onPostpone} onCancel={onCancel} onClick={() => onTaskClick(task)} />
                </Box>
              );
              if (isMobile && task.status === "pending") {
                return (
                  <SwipeableTaskRow key={task.id}
                    onSwipeComplete={() => onComplete(task.id, "completed")}
                    onSwipeCancel={() => onCancel(task.id)}>
                    {rowContent}
                  </SwipeableTaskRow>
                );
              }
              return rowContent;
            })}
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
  const { tasks, loading, error, setError, segment, setSegment, detailTask, setDetailTask, createOpen, setCreateOpen, createForm, setCreateForm, creating, createError, setCreateError, patientOptions, setPatientOptions, postponeOpen, setPostponeOpen, postponeTaskId, setPostponeTaskId, postponeDate, setPostponeDate, cancelConfirmId, setCancelConfirmId, handleStatus, handleCreate, handleConfirmPostpone } = useTasksState(doctorId);

  const today = new Date(); today.setHours(0, 0, 0, 0);
  const tomorrow = new Date(today); tomorrow.setDate(today.getDate() + 1);
  const weekEnd = new Date(today); weekEnd.setDate(today.getDate() + 7);
  const taskGroups = {};
  tasks.forEach((t) => { const g = taskDateGroup(t, today, tomorrow, weekEnd); (taskGroups[g] = taskGroups[g] || []).push(t); });
  const sortedGroups = GROUP_ORDER.filter((g) => taskGroups[g]);

  if (detailTask) {
    return (
      <>
        <TaskDetailView task={detailTask}
          onBack={() => setDetailTask(null)}
          onComplete={(id, status) => { handleStatus(id, status); }}
          onCancel={(id) => setCancelConfirmId(id)} />
        <CancelDialog open={Boolean(cancelConfirmId)} isMobile={isMobile} onClose={() => setCancelConfirmId(null)}
          onConfirm={() => { handleStatus(cancelConfirmId, "cancelled"); setCancelConfirmId(null); }} />
      </>
    );
  }

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%", bgcolor: "#ededed" }}>
      <TasksHeader segment={segment} loading={loading} onSegmentChange={setSegment}
        onOpenCreate={() => { setCreateOpen(true); setCreateError(""); getPatients(doctorId, {}, 200).then((d) => setPatientOptions(d.items || [])).catch(() => {}); }} />
      <TaskGroupList tasks={tasks} loading={loading} error={error} segment={segment} isMobile={isMobile}
        taskGroups={taskGroups} sortedGroups={sortedGroups}
        onError={setError} onComplete={handleStatus}
        onPostpone={(e, id) => { setPostponeOpen(true); setPostponeTaskId(id); setPostponeDate(""); }}
        onCancel={(id) => setCancelConfirmId(id)}
        onTaskClick={(task) => setDetailTask(task)} />
      <PostponeDialog open={Boolean(postponeOpen)} isMobile={isMobile} postponeDate={postponeDate} onChange={setPostponeDate}
        onClose={() => { setPostponeOpen(false); setPostponeTaskId(null); setPostponeDate(""); }} onConfirm={handleConfirmPostpone} />
      <CancelDialog open={Boolean(cancelConfirmId)} isMobile={isMobile} onClose={() => setCancelConfirmId(null)}
        onConfirm={() => { handleStatus(cancelConfirmId, "cancelled"); setCancelConfirmId(null); }} />
      <CreateTaskDialog open={createOpen} isMobile={isMobile} createForm={createForm} creating={creating} createError={createError}
        patientOptions={patientOptions} onFieldChange={(k, v) => setCreateForm((f) => ({ ...f, [k]: v }))} onCreate={handleCreate} onClose={() => setCreateOpen(false)} />
    </Box>
  );
}
