/**
 * 任务列表面板：按状态分组展示医疗任务，支持新建、完成、推迟和取消操作。
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
import { getTasks, patchTask, postponeTask, createTask, getPatients, getTaskRecord, getReviewQueue } from "../../api";
import { TASK_TYPE_LABEL } from "./constants";
import PatientAvatar from "./PatientAvatar";
import ReviewDetail from "./ReviewDetail";

const SEGMENTS = [
  { value: "todo", label: "待办" },
  { value: "review", label: "待审核" },
  { value: "done", label: "已完成" },
];

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


function TaskRow({ task, isOverdue }) {
  const iconColor = TASK_TYPE_ICON_COLOR[task.task_type] || "#999";
  const TaskIcon = TASK_TYPE_ICON[task.task_type] || AssignmentOutlinedIcon;
  return (
    <Box sx={{ display: "flex", alignItems: "flex-start", px: 2, py: 1.4 }}>
      <Box sx={{ width: 40, height: 40, borderRadius: "4px", bgcolor: iconColor,
        display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, mr: 1.5, mt: 0.3 }}>
        <TaskIcon sx={{ color: "#fff", fontSize: 22 }} />
      </Box>
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Box sx={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 1 }}>
          <Typography variant="body2" sx={{ fontWeight: 500, fontSize: 15, color: isOverdue ? "#FA5151" : "text.primary", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: 1 }}>
            {task.title || TASK_TYPE_LABEL[task.task_type] || task.task_type}
          </Typography>
          {task.due_at && (
            <Typography variant="caption" sx={{ color: isOverdue ? "#FA5151" : "#bbb", flexShrink: 0, fontSize: 11 }}>
              {task.due_at.slice(5, 10)}
            </Typography>
          )}
        </Box>
        {task.content && (
          <Typography sx={{ fontSize: 13, color: "#999", display: "block", mt: 0.2, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {task.content}
          </Typography>
        )}
        {task.patient_name && (
          <Typography variant="caption" sx={{ color: "#999", display: "block", mt: 0.2 }}>
            {task.patient_name}
          </Typography>
        )}
      </Box>
    </Box>
  );
}

function SwipeableTaskRow({ children, onSwipeLeft, onSwipeRight }) {
  const startX = useRef(null);
  const startY = useRef(null);
  const swiped = useRef(false);

  function handleTouchStart(e) {
    startX.current = e.touches[0].clientX;
    startY.current = e.touches[0].clientY;
    swiped.current = false;
  }
  function handleTouchEnd(e) {
    if (startX.current === null || swiped.current) return;
    const dx = e.changedTouches[0].clientX - startX.current;
    const dy = e.changedTouches[0].clientY - startY.current;
    if (Math.abs(dx) > 60 && Math.abs(dx) > Math.abs(dy) * 1.5) {
      swiped.current = true;
      if (dx < 0) onSwipeLeft?.();
      else onSwipeRight?.();
    }
    startX.current = null;
    startY.current = null;
  }
  return (
    <Box onTouchStart={handleTouchStart} onTouchEnd={handleTouchEnd}>
      {children}
    </Box>
  );
}

function TaskDetailView({ task, doctorId, isMobile, onBack, onComplete, onPostpone, onCancel }) {
  const iconColor = TASK_TYPE_ICON_COLOR[task.task_type] || "#999";
  const TaskIcon = TASK_TYPE_ICON[task.task_type] || AssignmentOutlinedIcon;
  const [record, setRecord] = useState(null);
  const [loadingRecord, setLoadingRecord] = useState(false);

  useEffect(() => {
    if (task.record_id && doctorId) {
      setLoadingRecord(true);
      getTaskRecord(task.record_id, doctorId)
        .then(setRecord)
        .catch(() => {})
        .finally(() => setLoadingRecord(false));
    }
  }, [task.record_id, doctorId]);

  const RECORD_TYPE_LABEL = {
    visit: "门诊记录", dictation: "语音记录", import: "导入记录", interview_summary: "预问诊记录",
  };

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%", bgcolor: "#f7f7f7" }}>
      <Box sx={{ display: "flex", alignItems: "center", height: 48, px: 1, bgcolor: "#fff", borderBottom: "1px solid #e5e5e5", flexShrink: 0 }}>
        <Box onClick={onBack} sx={{ display: "flex", alignItems: "center", gap: 0.3, cursor: "pointer", color: "#07C160", pr: 2, py: 1 }}>
          <Typography sx={{ fontSize: 15, color: "#07C160" }}>← 返回</Typography>
        </Box>
        <Typography sx={{ flex: 1, textAlign: "center", fontWeight: 600, fontSize: 16, mr: 5 }}>任务详情</Typography>
      </Box>
      <Box sx={{ flex: 1, overflowY: "auto", p: 2 }}>
        {/* Task header */}
        <Box sx={{ bgcolor: "#fff", borderRadius: 2, p: 2.5, mb: 1.5 }}>
          <Stack direction="row" alignItems="center" spacing={1.5} sx={{ mb: 2 }}>
            <Box sx={{ width: 44, height: 44, borderRadius: "10px", bgcolor: iconColor, display: "flex", alignItems: "center", justifyContent: "center" }}>
              <TaskIcon sx={{ color: "#fff", fontSize: 24 }} />
            </Box>
            <Box>
              <Typography sx={{ fontWeight: 600, fontSize: 17 }}>
                {task.title || TASK_TYPE_LABEL[task.task_type] || task.task_type}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                {TASK_TYPE_LABEL[task.task_type] || task.task_type}
              </Typography>
            </Box>
          </Stack>
          {task.content && (
            <Typography sx={{ fontSize: 14, color: "#555", lineHeight: 1.8, mb: 1.5 }}>{task.content}</Typography>
          )}
          {task.patient_name && (
            <Typography sx={{ fontSize: 13, color: "#999", mb: 0.5 }}>患者：{task.patient_name}</Typography>
          )}
          {task.due_at && (
            <Typography sx={{ fontSize: 13, color: "#999", mb: 0.5 }}>到期日：{task.due_at.slice(0, 10)}</Typography>
          )}
          <Typography sx={{ fontSize: 13, color: "#999" }}>状态：{task.status === "pending" ? "待处理" : task.status === "completed" ? "已完成" : task.status === "cancelled" ? "已取消" : task.status}</Typography>
        </Box>

        {/* Linked record content */}
        {loadingRecord && (
          <Box sx={{ display: "flex", justifyContent: "center", py: 2 }}>
            <CircularProgress size={24} />
          </Box>
        )}
        {record && (
          <Box sx={{ bgcolor: "#fff", borderRadius: 2, p: 2.5, mb: 1.5 }}>
            <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 1.5 }}>
              <Typography sx={{ fontWeight: 600, fontSize: 15 }}>
                {RECORD_TYPE_LABEL[record.record_type] || "病历记录"}
              </Typography>
              {record.needs_review && (
                <Typography sx={{ fontSize: 12, color: "#fff", bgcolor: "#FA5151", px: 1, py: 0.3, borderRadius: 1 }}>
                  待审阅
                </Typography>
              )}
            </Stack>
            {record.patient_name && (
              <Typography sx={{ fontSize: 13, color: "#999", mb: 1 }}>患者：{record.patient_name}</Typography>
            )}
            <Typography sx={{ fontSize: 14, color: "#333", lineHeight: 1.8, whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
              {record.content || "（内容为空）"}
            </Typography>
            {record.tags && record.tags.length > 0 && (
              <Box sx={{ mt: 1.5, display: "flex", flexWrap: "wrap", gap: 0.5 }}>
                {record.tags.map((tag, i) => (
                  <Typography key={i} sx={{ fontSize: 12, color: "#07C160", bgcolor: "#e8f5e9", px: 1, py: 0.2, borderRadius: 1 }}>
                    {tag}
                  </Typography>
                ))}
              </Box>
            )}
            {record.created_at && (
              <Typography sx={{ fontSize: 12, color: "#bbb", mt: 1 }}>
                创建于 {record.created_at.slice(0, 16).replace("T", " ")}
              </Typography>
            )}
          </Box>
        )}

        {/* Actions */}
        {task.status === "pending" && (
          <Stack spacing={1}>
            <Box onClick={() => { onComplete(task.id, "completed"); onBack(); }}
              sx={{ bgcolor: "#07C160", color: "#fff", textAlign: "center", py: 1.3, borderRadius: "4px", cursor: "pointer", fontWeight: 600, fontSize: 15, "&:active": { opacity: 0.7 } }}>
              完成任务
            </Box>
            <Box onClick={() => onPostpone(null, task.id)}
              sx={{ bgcolor: "#fff", color: "#666", textAlign: "center", py: 1.3, borderRadius: "4px", cursor: "pointer", fontSize: 15, "&:active": { opacity: 0.7 } }}>
              推迟
            </Box>
            <Box onClick={() => onCancel(task.id)}
              sx={{ bgcolor: "#fff", color: "#FA5151", textAlign: "center", py: 1.3, borderRadius: "4px", cursor: "pointer", fontSize: 15, "&:active": { opacity: 0.7 } }}>
              取消任务
            </Box>
          </Stack>
        )}
      </Box>
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

function ReviewQueueItem({ item, reviewed }) {
  return (
    <Box sx={{ display: "flex", alignItems: "flex-start", gap: 1.5, px: 2, py: 1.4 }}>
      <PatientAvatar name={item.patient_name} size={40} />
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Box sx={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 1 }}>
          <Typography sx={{ fontWeight: 500, fontSize: 15, color: "text.primary",
            overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: 1 }}>
            {item.patient_name || "未知患者"} · 问诊记录
          </Typography>
          <Typography sx={{ fontSize: 11, flexShrink: 0, color: "#fff",
            bgcolor: reviewed ? "#07C160" : "#ff9500", px: 0.8, py: 0.1, borderRadius: "3px" }}>
            {reviewed ? "已审核" : "待审核"}
          </Typography>
        </Box>
        {item.chief_complaint && (
          <Typography sx={{ fontSize: 13, color: "#999", mt: 0.2,
            overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {item.chief_complaint}
          </Typography>
        )}
      </Box>
    </Box>
  );
}

const GROUP_ORDER = ["已逾期", "今天", "明天", "本周", "之后", "无截止日期"];

function useTasksState(doctorId) {
  const [tasks, setTasks] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [segment, setSegment] = useState("todo");
  const [createOpen, setCreateOpen] = useState(false);
  const [createForm, setCreateForm] = useState({ taskType: "follow_up", title: "", dueAt: tomorrowStr(), patientId: "", patientSearch: "", content: "" });
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState("");
  const [patientOptions, setPatientOptions] = useState([]);
  const [postponeOpen, setPostponeOpen] = useState(false);
  const [postponeTaskId, setPostponeTaskId] = useState(null);
  const [postponeDate, setPostponeDate] = useState("");
  const [cancelConfirmId, setCancelConfirmId] = useState(null);
  const [reviews, setReviews] = useState([]);
  const [reviewLoading, setReviewLoading] = useState(false);
  const [reviewedItems, setReviewedItems] = useState([]);

  const load = useCallback(() => {
    setLoading(true); setError("");
    const fetch = segment === "done"
      ? Promise.all([getTasks(doctorId, "completed"), getTasks(doctorId, "cancelled"), getReviewQueue(doctorId, "reviewed")])
          .then(([c, x, r]) => {
            setReviewedItems(r.items || []);
            return [...(Array.isArray(c) ? c : c.items || []), ...(Array.isArray(x) ? x : x.items || [])]
              .sort((a, b) => (b.updated_at || "").localeCompare(a.updated_at || ""));
          })
      : getTasks(doctorId, "pending").then((d) => Array.isArray(d) ? d : (d.items || []));
    fetch.then(setTasks).catch((e) => setError(e.message || "任务加载失败")).finally(() => setLoading(false));
  }, [doctorId, segment]);

  const loadReviews = useCallback(() => {
    setReviewLoading(true);
    getReviewQueue(doctorId, "pending_review")
      .then((d) => setReviews(d.items || []))
      .catch(() => {})
      .finally(() => setReviewLoading(false));
  }, [doctorId]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { loadReviews(); }, [loadReviews, segment]);

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

  return { tasks, loading, error, setError, segment, setSegment, createOpen, setCreateOpen, createForm, setCreateForm, creating, createError, setCreateError, patientOptions, setPatientOptions, postponeOpen, setPostponeOpen, postponeTaskId, setPostponeTaskId, postponeDate, setPostponeDate, cancelConfirmId, setCancelConfirmId, load, handleStatus, handleCreate, handleConfirmPostpone, reviews, reviewLoading, loadReviews, reviewedItems };
}

function TasksHeader({ segment, loading, onSegmentChange, onOpenCreate }) {
  return (
    <Box sx={{ display: "flex", alignItems: "center", px: 2, py: 1, bgcolor: "#ededed", borderBottom: "0.5px solid #d9d9d9", flexShrink: 0, gap: 1 }}>
      <Box sx={{ display: "flex", flex: 1, bgcolor: "#d6d6d6", borderRadius: "4px", p: "2px" }}>
        {SEGMENTS.map((s) => (
          <Box key={s.value} onClick={() => onSegmentChange(s.value)}
            sx={{ flex: 1, textAlign: "center", py: 0.5, borderRadius: "3px", cursor: "pointer", fontSize: 13,
              bgcolor: segment === s.value ? "#fff" : "transparent",
              color: segment === s.value ? "#111" : "#666",
              fontWeight: segment === s.value ? 600 : 400,
              transition: "all 0.15s" }}>
            {s.label}
          </Box>
        ))}
      </Box>
      {loading && <CircularProgress size={14} sx={{ color: "#07C160" }} />}
      <Box onClick={onOpenCreate}
        sx={{ width: 28, height: 28, borderRadius: "4px", bgcolor: "#07C160", display: "flex", alignItems: "center", justifyContent: "center", cursor: "pointer", flexShrink: 0, "&:active": { opacity: 0.8 } }}>
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
            <Typography sx={{ fontSize: 12, color: group === "已逾期" ? "#FA5151" : "#999", fontWeight: 500 }}>{group}</Typography>
          </Box>
          <Box sx={{ bgcolor: "#fff" }}>
            {taskGroups[group].map((task, idx) => (
              <Box key={task.id} sx={{ borderBottom: idx < taskGroups[group].length - 1 ? "0.5px solid #f0f0f0" : "none" }}>
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
  const [detailTask, setDetailTask] = useState(null);
  const [detailReview, setDetailReview] = useState(null);
  const { tasks, loading, error, setError, segment, setSegment, createOpen, setCreateOpen, createForm, setCreateForm, creating, createError, setCreateError, patientOptions, setPatientOptions, postponeOpen, setPostponeOpen, postponeTaskId, setPostponeTaskId, postponeDate, setPostponeDate, cancelConfirmId, setCancelConfirmId, load, handleStatus, handleCreate, handleConfirmPostpone, reviews, reviewLoading, loadReviews, reviewedItems } = useTasksState(doctorId);

  const today = new Date(); today.setHours(0, 0, 0, 0);
  const tomorrow = new Date(today); tomorrow.setDate(today.getDate() + 1);
  const weekEnd = new Date(today); weekEnd.setDate(today.getDate() + 7);
  const taskGroups = {};
  tasks.forEach((t) => { const g = taskDateGroup(t, today, tomorrow, weekEnd); (taskGroups[g] = taskGroups[g] || []).push(t); });
  const sortedGroups = GROUP_ORDER.filter((g) => taskGroups[g]);

  const handleComplete = (id, status) => { handleStatus(id, status); };
  const handlePostpone = (e, id) => { setPostponeOpen(true); setPostponeTaskId(id); setPostponeDate(""); };
  const handleCancel = (id) => setCancelConfirmId(id);

  if (detailReview) {
    return (
      <ReviewDetail
        queueId={detailReview.id}
        doctorId={doctorId}
        onBack={() => { setDetailReview(null); loadReviews(); }}
        onConfirmed={() => loadReviews()}
      />
    );
  }

  if (detailTask) {
    return (
      <TaskDetailView task={detailTask} doctorId={doctorId} isMobile={isMobile}
        onBack={() => { setDetailTask(null); load(); }}
        onComplete={handleComplete}
        onPostpone={handlePostpone}
        onCancel={handleCancel} />
    );
  }

  const todoItems = segment === "todo"
    ? [
        ...reviews.map((r) => ({ ...r, _type: "review", _sortTime: r.created_at })),
        ...tasks.map((t) => ({ ...t, _type: "task", _sortTime: t.due_at || t.created_at })),
      ].sort((a, b) => (b._sortTime || "").localeCompare(a._sortTime || ""))
    : [];

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%", bgcolor: "#ededed" }}>
      <TasksHeader segment={segment} loading={loading} onSegmentChange={setSegment}
        onOpenCreate={() => { setCreateOpen(true); setCreateError(""); getPatients(doctorId, {}, 200).then((d) => setPatientOptions(d.items || [])).catch(() => {}); }} />
      <Box sx={{ flex: 1, overflowY: "auto" }}>
        {error && <Box sx={{ px: 2, pt: 1.5 }}><Alert severity="error" onClose={() => setError("")}>{error}</Alert></Box>}

        {/* todo segment */}
        {segment === "todo" && todoItems.length === 0 && !loading && !reviewLoading && (
          <Box sx={{ display: "flex", flexDirection: "column", alignItems: "center", py: 8, gap: 1, px: 2 }}>
            <AssignmentOutlinedIcon sx={{ fontSize: 48, color: "#ccc" }} />
            <Typography variant="body2" color="text.disabled" sx={{ fontWeight: 500 }}>暂无待办</Typography>
          </Box>
        )}
        {segment === "todo" && (
          <Box sx={{ bgcolor: "#fff" }}>
            {todoItems.map((item) =>
              item._type === "review" ? (
                <Box key={`review-${item.id}`} onClick={() => setDetailReview(item)}
                  sx={{ borderBottom: "0.5px solid #f0f0f0", cursor: "pointer" }}>
                  <ReviewQueueItem item={item} />
                </Box>
              ) : (
                <SwipeableTaskRow key={`task-${item.id}`}
                  onSwipeLeft={() => { if (item.status === "pending") handleComplete(item.id, "completed"); }}
                  onSwipeRight={() => { if (item.status === "pending") handleCancel(item.id); }}>
                  <Box onClick={() => setDetailTask(item)}
                    sx={{ borderBottom: "0.5px solid #f0f0f0", cursor: "pointer" }}>
                    <TaskRow task={item} isOverdue={false} />
                  </Box>
                </SwipeableTaskRow>
              )
            )}
          </Box>
        )}

        {/* review segment */}
        {segment === "review" && !reviewLoading && reviews.length === 0 && (
          <Box sx={{ display: "flex", flexDirection: "column", alignItems: "center", py: 8, gap: 1, px: 2 }}>
            <AssignmentOutlinedIcon sx={{ fontSize: 48, color: "#ccc" }} />
            <Typography variant="body2" color="text.disabled" sx={{ fontWeight: 500 }}>暂无待审核记录</Typography>
          </Box>
        )}
        {segment === "review" && reviews.map((item) => (
          <Box key={`review-${item.id}`} onClick={() => setDetailReview(item)}
            sx={{ borderBottom: "0.5px solid #f0f0f0", cursor: "pointer", bgcolor: "#fff" }}>
            <ReviewQueueItem item={item} />
          </Box>
        ))}

        {/* done segment */}
        {segment === "done" && reviewedItems.length > 0 && (
          <>
            <Box sx={{ px: 2, py: 0.6, pt: 1.2 }}>
              <Typography sx={{ fontSize: 12, color: "#999", fontWeight: 500 }}>已审核记录</Typography>
            </Box>
            <Box sx={{ bgcolor: "#fff" }}>
              {reviewedItems.map((item) => (
                <Box key={`reviewed-${item.id}`} onClick={() => setDetailReview(item)}
                  sx={{ borderBottom: "0.5px solid #f0f0f0", cursor: "pointer" }}>
                  <ReviewQueueItem item={item} reviewed />
                </Box>
              ))}
            </Box>
          </>
        )}
        {segment === "done" && sortedGroups.map((group) => (
          <Box key={group}>
            <Box sx={{ px: 2, py: 0.6, pt: 1.2 }}>
              <Typography sx={{ fontSize: 12, color: group === "已逾期" ? "#FA5151" : "#999", fontWeight: 500 }}>{group}</Typography>
            </Box>
            <Box sx={{ bgcolor: "#fff" }}>
              {taskGroups[group].map((task, idx) => (
                <SwipeableTaskRow key={task.id}
                  onSwipeLeft={() => { if (task.status === "pending") handleComplete(task.id, "completed"); }}
                  onSwipeRight={() => { if (task.status === "pending") handleCancel(task.id); }}>
                  <Box onClick={() => setDetailTask(task)}
                    sx={{ borderBottom: idx < taskGroups[group].length - 1 ? "0.5px solid #f0f0f0" : "none", cursor: "pointer" }}>
                    <TaskRow task={task} isOverdue={group === "已逾期"} />
                  </Box>
                </SwipeableTaskRow>
              ))}
            </Box>
          </Box>
        ))}

        <Box sx={{ height: 24 }} />
      </Box>
      <PostponeDialog open={Boolean(postponeOpen)} isMobile={isMobile} postponeDate={postponeDate} onChange={setPostponeDate}
        onClose={() => { setPostponeOpen(false); setPostponeTaskId(null); setPostponeDate(""); }} onConfirm={handleConfirmPostpone} />
      <CancelDialog open={Boolean(cancelConfirmId)} isMobile={isMobile} onClose={() => setCancelConfirmId(null)}
        onConfirm={() => { handleStatus(cancelConfirmId, "cancelled"); setCancelConfirmId(null); }} />
      <CreateTaskDialog open={createOpen} isMobile={isMobile} createForm={createForm} creating={creating} createError={createError}
        patientOptions={patientOptions} onFieldChange={(k, v) => setCreateForm((f) => ({ ...f, [k]: v }))} onCreate={handleCreate} onClose={() => setCreateOpen(false)} />
    </Box>
  );
}
