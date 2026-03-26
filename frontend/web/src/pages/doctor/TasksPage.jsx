/**
 * @route /doctor/tasks
 *
 * 任务列表面板：统一优先级列表，支持筛选芯片、日期分组，合并审核和任务。
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
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
import { getTasks, patchTask, postponeTask, createTask, getPatients, getTaskRecord } from "../../api";
import { TASK_TYPE_LABEL, TASK_FILTER_CHIPS } from "./constants";
import AskAIBar from "../../components/AskAIBar";
import AppButton from "../../components/AppButton";
import BarButton from "../../components/BarButton";
import DetailCard from "../../components/DetailCard";
import ListCard from "../../components/ListCard";
import NewItemCard from "../../components/NewItemCard";
import PageSkeleton from "../../components/PageSkeleton";
import SectionLabel from "../../components/SectionLabel";
import ReviewDetail from "./ReviewDetail";
import SubpageHeader from "./SubpageHeader";
import { TYPE, ICON } from "../../theme";

const TASK_TYPE_ICON_COLOR = {
  follow_up: "#07C160", medication: "#5b9bd5", checkup: "#e8833a", general: "#8e44ad",
};

const TASK_TYPE_ICON = {
  follow_up: EventRepeatOutlinedIcon, medication: MedicationOutlinedIcon,
  checkup: BiotechOutlinedIcon, general: AssignmentOutlinedIcon,
};

function tomorrowStr() {
  const d = new Date();
  d.setDate(d.getDate() + 1);
  return d.toISOString().slice(0, 10);
}

/* ── Date grouping ── */

function groupByDate(items) {
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const endOfWeek = new Date(today);
  endOfWeek.setDate(today.getDate() + (7 - today.getDay()));
  const groups = { "已逾期": [], "今天": [], "本周": [], "之后": [], "无截止日期": [] };
  for (const item of items) {
    const due = item.due_at || item.created_at;
    if (!due) { groups["无截止日期"].push(item); continue; }
    const d = new Date(due);
    const dd = new Date(d.getFullYear(), d.getMonth(), d.getDate());
    if (dd < today) groups["已逾期"].push(item);
    else if (dd.getTime() === today.getTime()) groups["今天"].push(item);
    else if (dd < endOfWeek) groups["本周"].push(item);
    else groups["之后"].push(item);
  }
  return Object.entries(groups).filter(([, items]) => items.length > 0);
}

/* ── Filter chips — uses shared FilterChips component ── */
import FilterBar from "../../components/FilterBar";

function TaskFilterChips({ active, counts, onChange }) {
  return <FilterBar items={TASK_FILTER_CHIPS} active={active} counts={counts} onChange={onChange} />;
}

/* ── Unified task item ── */

function TaskAvatar({ item }) {
  const isReview = item._type === "review";
  const iconColor = isReview ? "#d46b08" : (TASK_TYPE_ICON_COLOR[item.task_type] || "#8e44ad");
  const TaskIcon = isReview ? AssignmentOutlinedIcon : (TASK_TYPE_ICON[item.task_type] || AssignmentOutlinedIcon);
  return (
    <Box sx={{ width: 36, height: 36, borderRadius: "4px", bgcolor: iconColor,
      display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
      <TaskIcon sx={{ color: "#fff", fontSize: ICON.lg }} />
    </Box>
  );
}

function UnifiedTaskItem({ item, onTap }) {
  const isReview = item._type === "review";
  const isReviewed = isReview && item.status === "reviewed";
  const chipLabel = isReview ? (isReviewed ? "已审核" : "待审核") : (TASK_TYPE_LABEL[item.task_type] || "任务");
  const chipBg = isReview ? (isReviewed ? "#e8f5e9" : "#FFF7E6") : "#e8f5e9";
  const chipColor = isReview ? (isReviewed ? "#07C160" : "#d46b08") : "#07C160";
  const title = isReview ? `${item.patient_name} 问诊记录` : item.title;
  const subtitle = isReview
    ? (isReviewed ? "已确认" : item.diagnosis_status === "completed" ? "AI诊断已完成 · 等待确认" : "AI诊断中...")
    : (item.content || item.patient_name || "");
  return (
    <ListCard
      avatar={<TaskAvatar item={item} />}
      title={title}
      subtitle={subtitle}
      right={
        <Typography sx={{ fontSize: TYPE.micro.fontSize, px: 0.8, py: 0.1, borderRadius: "4px", bgcolor: chipBg, color: chipColor }}>
          {chipLabel}
        </Typography>
      }
      onClick={() => onTap(item)}
    />
  );
}

/* ── Swipeable row (touch) ── */

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

/* ── Task detail view ── */

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

  const taskTitle = task.title || TASK_TYPE_LABEL[task.task_type] || task.task_type;
  const statusLabel = task.status === "pending" ? "待处理" : task.status === "completed" ? "已完成" : task.status === "cancelled" ? "已取消" : task.status;

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%", bgcolor: "#f7f7f7" }}>
      <SubpageHeader title={task.patient_name || taskTitle} onBack={isMobile ? onBack : undefined} />
      <Box sx={{ flex: 1, overflowY: "auto" }}>
        <DetailCard
          title={`${taskTitle}${task.patient_name ? ` · ${task.patient_name}` : ""}`}
          fields={[
            { label: "类型", value: TASK_TYPE_LABEL[task.task_type] || task.task_type },
            { label: "状态", value: statusLabel },
            ...(task.due_at ? [{ label: "到期", value: task.due_at.slice(0, 10) }] : []),
            ...(task.patient_name ? [{ label: "患者", value: task.patient_name }] : []),
          ]}
          note={task.content}
        >
          {task.status === "pending" && (
            <Stack spacing={1}>
              <Stack direction="row" spacing={1}>
                <AppButton variant="primary" size="sm" onClick={() => { onComplete(task.id, "completed"); onBack(); }}>完成任务</AppButton>
                <AppButton variant="secondary" size="sm" onClick={() => onPostpone(null, task.id)}>推迟</AppButton>
                <AppButton variant="danger" size="sm" onClick={() => onCancel(task.id)}>取消</AppButton>
              </Stack>
            </Stack>
          )}
        </DetailCard>

        {/* Linked record */}
        {loadingRecord && (
          <Box sx={{ display: "flex", justifyContent: "center", py: 2 }}>
            <CircularProgress size={20} />
          </Box>
        )}
        {record && (
          <DetailCard
            title={RECORD_TYPE_LABEL[record.record_type] || "病历记录"}
            note={record.content || "（内容为空）"}
            noteLabel="病历内容"
          />
        )}
      </Box>
    </Box>
  );
}

/* ── Dialogs ── */

function PostponeDialog({ open, isMobile, postponeDate, onChange, onClose, onConfirm }) {
  return (
    <Dialog open={open} onClose={onClose}
      PaperProps={{ sx: isMobile
        ? { position: "fixed", bottom: 0, left: 0, right: 0, m: 0, borderRadius: "12px 12px 0 0", width: "100%" }
        : { borderRadius: 2, minWidth: 240 }
      }}
      sx={isMobile ? { "& .MuiDialog-container": { alignItems: "flex-end" } } : {}}>
      <Box sx={{ p: 2.5 }}>
        <Typography sx={{ fontWeight: 600, fontSize: TYPE.action.fontSize, mb: 1.5, color: "#333" }}>选择新到期日</Typography>
        <TextField type="date" size="small" fullWidth InputLabelProps={{ shrink: true }}
          value={postponeDate} onChange={(e) => onChange(e.target.value)} sx={{ mb: 2 }} />
        <Box sx={{ display: "flex", gap: 1.5 }}>
          <Box onClick={onClose}
            sx={{ flex: 1, textAlign: "center", py: 1.2, borderRadius: "4px", bgcolor: "#f5f5f5", cursor: "pointer", fontSize: TYPE.body.fontSize, color: "#666", "&:active": { opacity: 0.7 } }}>
            取消
          </Box>
          <Box onClick={postponeDate ? onConfirm : undefined}
            sx={{ flex: 1, textAlign: "center", py: 1.2, borderRadius: "4px", bgcolor: postponeDate ? "#07C160" : "#e0e0e0", cursor: postponeDate ? "pointer" : "default", fontSize: TYPE.heading.fontSize, color: "#fff", fontWeight: 600, "&:active": postponeDate ? { opacity: 0.7 } : {} }}>
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
        <Typography sx={{ fontWeight: 600, fontSize: TYPE.action.fontSize, mb: 0.5, textAlign: "center", color: "#333" }}>取消任务</Typography>
        <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: "#999", mb: 2.5, textAlign: "center" }}>此任务将被标记为已取消</Typography>
        <Box sx={{ display: "flex", gap: 1.5 }}>
          <Box onClick={onClose}
            sx={{ flex: 1, textAlign: "center", py: 1.2, borderRadius: "4px", bgcolor: "#f5f5f5", cursor: "pointer", fontSize: TYPE.body.fontSize, color: "#666", "&:active": { opacity: 0.7 } }}>
            保留
          </Box>
          <Box onClick={onConfirm}
            sx={{ flex: 1, textAlign: "center", py: 1.2, borderRadius: "4px", bgcolor: "#FA5151", cursor: "pointer", fontSize: TYPE.heading.fontSize, color: "#fff", fontWeight: 600, "&:active": { opacity: 0.7 } }}>
            确认取消
          </Box>
        </Box>
      </Box>
    </Dialog>
  );
}

function CreateTaskSubpage({ createForm, creating, createError, patientOptions, onFieldChange, onCreate, onClose }) {
  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%", bgcolor: "#f7f7f7" }}>
      <SubpageHeader title="新建任务" onBack={onClose}
        right={<BarButton onClick={onCreate} loading={creating}>创建</BarButton>}
      />
      <Box sx={{ flex: 1, overflowY: "auto", p: 2 }}>
        {createError && <Alert severity="error" sx={{ mb: 2 }}>{createError}</Alert>}
        <Stack spacing={2.5}>
          <TextField select label="任务类型" size="small" fullWidth
            value={createForm.taskType}
            onChange={(e) => onFieldChange("taskType", e.target.value)}>
            {Object.entries(TASK_TYPE_LABEL).map(([k, v]) => {
              const ItemIcon = TASK_TYPE_ICON[k] || AssignmentOutlinedIcon;
              const ic = TASK_TYPE_ICON_COLOR[k] || "#999";
              return (
                <MenuItem key={k} value={k} sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                  <ItemIcon sx={{ fontSize: ICON.md, color: ic }} />
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
      </Box>
    </Box>
  );
}

/* ── Main component ── */

export default function TasksPage({ doctorId, urlSubpage, urlSubId }) {
  const navigate = useNavigate();
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down("sm"));

  const [filter, setFilter] = useState("all");
  const [detailTask, setDetailTask] = useState(null);
  const [detailReview, setDetailReview] = useState(null);

  // Data
  const [pendingTasks, setPendingTasks] = useState([]);
  const [doneTasks, setDoneTasks] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // URL-driven detail: /doctor/tasks/task/:id or /doctor/tasks/review/:id
  // Sync URL params → state on mount/change
  useEffect(() => {
    if (urlSubpage === "review" && urlSubId) {
      setDetailReview({ id: Number(urlSubId) });
      setDetailTask(null);
    } else if (urlSubpage === "task" && urlSubId) {
      const id = Number(urlSubId);
      const found = [...pendingTasks, ...doneTasks].find(t => t.id === id);
      if (found) { setDetailTask(found); setDetailReview(null); }
    } else if (urlSubpage === "new") {
      setCreateOpen(true);
      setDetailTask(null);
      setDetailReview(null);
    } else if (!urlSubpage) {
      setDetailTask(null);
      setDetailReview(null);
    }
  }, [urlSubpage, urlSubId, pendingTasks, doneTasks]);

  // Create dialog
  const [createOpen, setCreateOpen] = useState(urlSubpage === "new");
  const [createForm, setCreateForm] = useState({ taskType: "follow_up", title: "", dueAt: tomorrowStr(), patientId: "", patientSearch: "", content: "" });
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState("");
  const [patientOptions, setPatientOptions] = useState([]);

  // Postpone / Cancel
  const [postponeOpen, setPostponeOpen] = useState(false);
  const [postponeTaskId, setPostponeTaskId] = useState(null);
  const [postponeDate, setPostponeDate] = useState("");
  const [cancelConfirmId, setCancelConfirmId] = useState(null);

  const loadAll = useCallback(() => {
    setLoading(true);
    setError("");
    Promise.all([
      getTasks(doctorId, "pending").then((d) => Array.isArray(d) ? d : (d.items || [])),
      Promise.all([getTasks(doctorId, "completed"), getTasks(doctorId, "cancelled")])
        .then(([c, x]) => [
          ...(Array.isArray(c) ? c : c.items || []),
          ...(Array.isArray(x) ? x : x.items || []),
        ].sort((a, b) => (b.updated_at || "").localeCompare(a.updated_at || ""))),
    ])
      .then(([pending, done]) => {
        setPendingTasks(pending);
        setDoneTasks(done);
      })
      .catch((e) => setError(typeof e === "string" ? e : (e?.message || e?.detail || "任务加载失败")))
      .finally(() => setLoading(false));
  }, [doctorId]);

  useEffect(() => { loadAll(); }, [loadAll]);

  // Normalize items with _type tag
  const taggedPending = pendingTasks.map((t) => ({ ...t, _type: "task" }));
  const taggedDone = doneTasks.map((t) => ({ ...t, _type: "task" }));

  // Filter by active chip
  let filtered = [];
  if (filter === "all") filtered = taggedPending;
  else if (filter === "task") filtered = taggedPending;
  else if (filter === "done") filtered = taggedDone;

  const dateGroups = groupByDate(filtered);

  const pendingCount = pendingTasks.length;

  // Actions
  async function handleStatus(taskId, status) {
    try { await patchTask(taskId, doctorId, status); loadAll(); }
    catch (e) { setError(e.message || "任务状态更新失败"); }
  }
  async function handleCreate() {
    if (!createForm.taskType) return;
    setCreating(true); setCreateError("");
    try {
      await createTask(doctorId, { taskType: createForm.taskType, title: createForm.title || TASK_TYPE_LABEL[createForm.taskType] || createForm.taskType, dueAt: createForm.dueAt || undefined, patientId: createForm.patientId ? Number(createForm.patientId) : undefined, content: createForm.content || undefined });
      setCreateOpen(false); setCreateForm({ taskType: "follow_up", title: "", dueAt: tomorrowStr(), patientId: "", patientSearch: "", content: "" }); loadAll();
    } catch (e) { setCreateError(e.message || "创建失败"); } finally { setCreating(false); }
  }
  async function handleConfirmPostpone() {
    if (!postponeDate || !postponeTaskId) return;
    try { await postponeTask(postponeTaskId, doctorId, postponeDate); setPostponeOpen(false); setPostponeTaskId(null); setPostponeDate(""); loadAll(); }
    catch (e) { setError(e.message || "推迟失败"); setPostponeOpen(false); }
  }
  const handleComplete = (id, status) => handleStatus(id, status);
  const handlePostpone = (e, id) => { setPostponeOpen(true); setPostponeTaskId(id); setPostponeDate(""); };
  const handleCancel = (id) => setCancelConfirmId(id);

  function openCreateDialog() {
    setCreateOpen(true);
    setCreateError("");
    navigate("/doctor/tasks/new");
    getPatients(doctorId, {}, 200).then((d) => setPatientOptions(d.items || [])).catch(() => {});
  }

  function handleItemTap(item) {
    if (item._type === "review") {
      setDetailReview(item);
      navigate(`/doctor/tasks/review/${item.id}`);
    } else if (item.record_id) {
      // Tasks linked to a record (e.g. diagnosis pipeline) → open review page
      navigate(`/doctor/review/${item.record_id}`);
    } else {
      setDetailTask(item);
      navigate(`/doctor/tasks/task/${item.id}`);
    }
  }

  // Mobile subpage override: drill-in views
  const mobileSubpage = isMobile && createOpen ? (
    <CreateTaskSubpage createForm={createForm} creating={creating} createError={createError}
      patientOptions={patientOptions} onFieldChange={(k, v) => setCreateForm((f) => ({ ...f, [k]: v }))}
      onCreate={handleCreate} onClose={() => setCreateOpen(false)} />
  ) : isMobile && detailReview ? (
    <ReviewDetail queueId={detailReview.id} doctorId={doctorId} isMobile={true}
      onBack={() => { setDetailReview(null); loadAll(); navigate("/doctor/tasks"); }} onConfirmed={() => { loadAll(); }} />
  ) : isMobile && detailTask ? (
    <TaskDetailView task={detailTask} doctorId={doctorId} isMobile={isMobile}
      onBack={() => { setDetailTask(null); loadAll(); navigate("/doctor/tasks"); }}
      onComplete={handleComplete} onPostpone={handlePostpone} onCancel={handleCancel} />
  ) : null;

  const listPane = (
    <>
      <TaskFilterChips active={filter} onChange={setFilter}
        counts={{
          all: taggedPending.length,
          task: taggedPending.length,
          done: taggedDone.length,
        }} />
      <Box sx={{ flex: 1, overflowY: "auto" }}>
        <NewItemCard title="新建任务" subtitle="添加随访、检查、用药等任务" onClick={openCreateDialog} />
        {error && <Box sx={{ px: 2, pt: 1.5 }}><Alert severity="error" onClose={() => setError("")}>{error}</Alert></Box>}
        {!loading && !error && filtered.length === 0 && (
          <Box sx={{ display: "flex", flexDirection: "column", alignItems: "center", py: 6, gap: 1 }}>
            <AssignmentOutlinedIcon sx={{ fontSize: ICON.display, color: "#ddd" }} />
            <Typography sx={{ color: "#999", fontSize: TYPE.body.fontSize }}>暂无任务</Typography>
            <Typography sx={{ color: "#bbb", fontSize: TYPE.caption.fontSize }}>在聊天中说「今日任务」或点击新建</Typography>
          </Box>
        )}
        {dateGroups.map(([group, items]) => (
          <Box key={group}>
            <SectionLabel sx={group === "已逾期" ? { "& .MuiTypography-root": { color: "#FA5151" } } : {}}>
              {group}
            </SectionLabel>
            <Box sx={{ bgcolor: "#fff" }}>
              {items.map((item, idx) => (
                <SwipeableTaskRow key={`${item._type}-${item.id}`}
                  onSwipeLeft={() => { if (item._type === "task" && item.status === "pending") handleComplete(item.id, "completed"); }}
                  onSwipeRight={() => { if (item._type === "task" && item.status === "pending") handleCancel(item.id); }}>
                  <Box sx={{ borderBottom: idx < items.length - 1 ? "0.5px solid #f0f0f0" : "none" }}>
                    <UnifiedTaskItem item={item} onTap={handleItemTap} />
                  </Box>
                </SwipeableTaskRow>
              ))}
            </Box>
          </Box>
        ))}
        <Box sx={{ height: 24 }} />
      </Box>
    </>
  );

  const detailContent = createOpen && !isMobile ? (
    <CreateTaskSubpage createForm={createForm} creating={creating} createError={createError}
      patientOptions={patientOptions} onFieldChange={(k, v) => setCreateForm((f) => ({ ...f, [k]: v }))}
      onCreate={handleCreate} onClose={() => setCreateOpen(false)} />
  ) : detailReview ? (
    <ReviewDetail queueId={detailReview.id} doctorId={doctorId} isMobile={isMobile}
      onBack={() => { setDetailReview(null); loadAll(); navigate("/doctor/tasks"); }} onConfirmed={() => { loadAll(); }} />
  ) : detailTask ? (
    <TaskDetailView task={detailTask} doctorId={doctorId} isMobile={isMobile}
      onBack={() => { setDetailTask(null); loadAll(); navigate("/doctor/tasks"); }}
      onComplete={handleComplete} onPostpone={handlePostpone} onCancel={handleCancel} />
  ) : null;

  return (
    <>
      <PageSkeleton
        title="任务"
        headerRight={null}
        isMobile={isMobile}
        mobileView={mobileSubpage}
        listPane={listPane}
        detailPane={detailContent}
      />
      <PostponeDialog open={Boolean(postponeOpen)} isMobile={isMobile} postponeDate={postponeDate} onChange={setPostponeDate}
        onClose={() => { setPostponeOpen(false); setPostponeTaskId(null); setPostponeDate(""); }} onConfirm={handleConfirmPostpone} />
      <CancelDialog open={Boolean(cancelConfirmId)} isMobile={isMobile} onClose={() => setCancelConfirmId(null)}
        onConfirm={() => { handleStatus(cancelConfirmId, "cancelled"); setCancelConfirmId(null); }} />
    </>
  );
}
