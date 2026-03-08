import { useMemo, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Collapse,
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";
import CancelOutlinedIcon from "@mui/icons-material/CancelOutlined";
import AccessTimeIcon from "@mui/icons-material/AccessTime";
import WarningAmberRoundedIcon from "@mui/icons-material/WarningAmberRounded";
import ScheduleIcon from "@mui/icons-material/Schedule";
import AddIcon from "@mui/icons-material/Add";
import { t } from "../../i18n";

const TASK_TYPES = ["follow_up", "medication", "lab_review", "referral", "imaging", "appointment", "general"];

function isOverdue(dueAt) {
  if (!dueAt) return false;
  return new Date(dueAt) < new Date();
}

function isDueSoon(dueAt) {
  if (!dueAt) return false;
  const diff = new Date(dueAt) - new Date();
  return diff >= 0 && diff < 48 * 60 * 60 * 1000;
}

function formatDue(dueAt) {
  if (!dueAt) return null;
  const d = new Date(dueAt);
  return d.toLocaleDateString("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function todayIso() {
  return new Date().toISOString().slice(0, 10);
}

function TaskTypeChip({ taskType }) {
  const label = t(`manage.tasks.taskType.${taskType}`) || taskType;
  const colorMap = {
    follow_up: "primary",
    medication: "secondary",
    lab_review: "info",
    referral: "warning",
    imaging: "default",
    appointment: "success",
  };
  return <Chip size="small" color={colorMap[taskType] || "default"} label={label} />;
}

function PostponeRow({ taskId, onPostpone, onCancel }) {
  const [date, setDate] = useState(todayIso());
  const [busy, setBusy] = useState(false);

  async function submit() {
    if (!date) return;
    setBusy(true);
    try {
      await onPostpone(taskId, `${date}T23:59:00+00:00`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Stack direction="row" spacing={0.8} alignItems="center" sx={{ mt: 0.8 }}>
      <TextField
        type="date"
        size="small"
        value={date}
        onChange={(e) => setDate(e.target.value)}
        inputProps={{ min: todayIso() }}
        sx={{ width: 160 }}
      />
      <Button size="small" variant="contained" onClick={submit} disabled={busy || !date}>
        {t("manage.tasks.postponeConfirm")}
      </Button>
      <Button size="small" variant="text" onClick={onCancel} disabled={busy}>
        {t("manage.tasks.cancel")}
      </Button>
    </Stack>
  );
}

function TaskCard({ task, onComplete, onCancel, onPostpone }) {
  const overdue = isOverdue(task.due_at);
  const dueSoon = isDueSoon(task.due_at);
  const isPending = task.status === "pending";
  const [showPostpone, setShowPostpone] = useState(false);

  async function handlePostpone(taskId, dueAt) {
    await onPostpone(taskId, dueAt);
    setShowPostpone(false);
  }

  return (
    <Card
      sx={{
        borderRadius: 1.5,
        borderLeft: `4px solid ${overdue && isPending ? "#ef4444" : dueSoon && isPending ? "#f97316" : isPending ? "#0f766e" : "#cbd5e1"}`,
        opacity: task.status === "cancelled" ? 0.6 : 1,
      }}
    >
      <CardContent sx={{ p: 1.5 }}>
        <Stack
          direction={{ xs: "column", sm: "row" }}
          spacing={1}
          sx={{ justifyContent: "space-between", alignItems: { sm: "center" } }}
        >
          <Box sx={{ flex: 1 }}>
            <Stack direction="row" spacing={0.7} sx={{ alignItems: "center", flexWrap: "wrap", mb: 0.4 }}>
              <TaskTypeChip taskType={task.task_type} />
              {task.status === "completed" ? (
                <Chip size="small" color="success" icon={<CheckCircleOutlineIcon />} label={t("manage.tasks.status.completed")} />
              ) : task.status === "cancelled" ? (
                <Chip size="small" color="default" icon={<CancelOutlinedIcon />} label={t("manage.tasks.status.cancelled")} />
              ) : overdue ? (
                <Chip size="small" color="error" icon={<WarningAmberRoundedIcon />} label={t("manage.tasks.overdue")} />
              ) : dueSoon ? (
                <Chip size="small" color="warning" icon={<AccessTimeIcon />} label={t("manage.followUp.due_soon")} />
              ) : null}
            </Stack>
            <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
              {task.title}
            </Typography>
            {task.due_at ? (
              <Typography
                variant="caption"
                sx={{ display: "block", mt: 0.2, color: overdue && isPending ? "error.main" : "text.secondary" }}
              >
                {t("manage.tasks.dueAt")}：{formatDue(task.due_at)}
              </Typography>
            ) : null}
            <Collapse in={showPostpone}>
              <PostponeRow
                taskId={task.id}
                onPostpone={handlePostpone}
                onCancel={() => setShowPostpone(false)}
              />
            </Collapse>
          </Box>
          {isPending ? (
            <Stack direction="row" spacing={0.7} flexShrink={0}>
              <Button
                size="small"
                variant="contained"
                color="success"
                onClick={() => onComplete(task.id)}
                startIcon={<CheckCircleOutlineIcon />}
              >
                {t("manage.tasks.complete")}
              </Button>
              <Button
                size="small"
                variant="outlined"
                color="warning"
                onClick={() => setShowPostpone((v) => !v)}
                startIcon={<ScheduleIcon />}
              >
                {t("manage.tasks.postpone")}
              </Button>
              <Button
                size="small"
                variant="outlined"
                color="error"
                onClick={() => onCancel(task.id)}
              >
                {t("manage.tasks.cancel")}
              </Button>
            </Stack>
          ) : null}
        </Stack>
      </CardContent>
    </Card>
  );
}

function CreateTaskForm({ onCreate, onClose }) {
  const [taskType, setTaskType] = useState("follow_up");
  const [title, setTitle] = useState("");
  const [dueDate, setDueDate] = useState("");
  const [content, setContent] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  async function submit() {
    if (!title.trim()) return;
    setBusy(true);
    setErr("");
    try {
      await onCreate({
        taskType,
        title: title.trim(),
        dueAt: dueDate ? `${dueDate}T23:59:00+00:00` : undefined,
        content: content.trim() || undefined,
      });
      onClose();
    } catch (e) {
      setErr(t("manage.tasks.createFailed", { message: e.message }));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card sx={{ borderRadius: 1.5, border: "1px dashed", borderColor: "primary.main" }}>
      <CardContent sx={{ p: 1.5 }}>
        <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1 }}>
          {t("manage.tasks.newTask")}
        </Typography>
        {err ? <Alert severity="error" sx={{ mb: 1 }}>{err}</Alert> : null}
        <Stack spacing={1.2}>
          <FormControl size="small" fullWidth>
            <InputLabel>{t("manage.tasks.fields.taskType")}</InputLabel>
            <Select
              label={t("manage.tasks.fields.taskType")}
              value={taskType}
              onChange={(e) => setTaskType(e.target.value)}
            >
              {TASK_TYPES.map((tt) => (
                <MenuItem key={tt} value={tt}>
                  {t(`manage.tasks.taskType.${tt}`) || tt}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          <TextField
            size="small"
            fullWidth
            label={t("manage.tasks.fields.title")}
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            required
          />
          <TextField
            type="date"
            size="small"
            fullWidth
            label={t("manage.tasks.fields.dueDate")}
            value={dueDate}
            onChange={(e) => setDueDate(e.target.value)}
            InputLabelProps={{ shrink: true }}
            inputProps={{ min: todayIso() }}
          />
          <TextField
            size="small"
            fullWidth
            label={t("manage.tasks.fields.content")}
            value={content}
            onChange={(e) => setContent(e.target.value)}
            multiline
            rows={2}
          />
          <Stack direction="row" spacing={1} justifyContent="flex-end">
            <Button size="small" variant="text" onClick={onClose} disabled={busy}>
              {t("manage.tasks.cancel")}
            </Button>
            <Button
              size="small"
              variant="contained"
              startIcon={<AddIcon />}
              onClick={submit}
              disabled={busy || !title.trim()}
            >
              {t("manage.tasks.create")}
            </Button>
          </Stack>
        </Stack>
      </CardContent>
    </Card>
  );
}

export default function TaskPanel({ tasks, loading, error, onComplete, onCancel, onPostpone, onCreate }) {
  const [statusFilter, setStatusFilter] = useState("pending");
  const [showCreate, setShowCreate] = useState(false);

  const filtered = useMemo(() => {
    if (!statusFilter) return tasks;
    return tasks.filter((t) => t.status === statusFilter);
  }, [tasks, statusFilter]);

  const sorted = useMemo(() => {
    return [...filtered].sort((a, b) => {
      const aOverdue = isOverdue(a.due_at) && a.status === "pending" ? 0 : 1;
      const bOverdue = isOverdue(b.due_at) && b.status === "pending" ? 0 : 1;
      if (aOverdue !== bOverdue) return aOverdue - bOverdue;
      if (a.due_at && b.due_at) return new Date(a.due_at) - new Date(b.due_at);
      if (a.due_at) return -1;
      if (b.due_at) return 1;
      return 0;
    });
  }, [filtered]);

  const pendingCount = useMemo(() => tasks.filter((t) => t.status === "pending").length, [tasks]);
  const overdueCount = useMemo(
    () => tasks.filter((t) => t.status === "pending" && isOverdue(t.due_at)).length,
    [tasks]
  );

  return (
    <Stack spacing={1.25}>
      {error ? <Alert severity="error">{error}</Alert> : null}

      {overdueCount > 0 ? (
        <Alert severity="error" icon={<WarningAmberRoundedIcon />}>
          {t("manage.tasks.overdueAlert", { count: overdueCount })}
        </Alert>
      ) : pendingCount > 0 ? (
        <Alert severity="info">{t("manage.tasks.pendingAlert", { count: pendingCount })}</Alert>
      ) : null}

      <Card sx={{ borderRadius: 1.5 }}>
        <CardContent sx={{ display: "flex", gap: 1, alignItems: "center" }}>
          <FormControl size="small" sx={{ minWidth: 180 }}>
            <InputLabel id="task-status-filter-label">{t("manage.tasks.filters.status")}</InputLabel>
            <Select
              labelId="task-status-filter-label"
              label={t("manage.tasks.filters.status")}
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
            >
              <MenuItem value="">{t("common.all")}</MenuItem>
              <MenuItem value="pending">{t("manage.tasks.status.pending")}</MenuItem>
              <MenuItem value="completed">{t("manage.tasks.status.completed")}</MenuItem>
              <MenuItem value="cancelled">{t("manage.tasks.status.cancelled")}</MenuItem>
            </Select>
          </FormControl>
          <Box sx={{ flex: 1 }} />
          <Button
            size="small"
            variant="outlined"
            startIcon={<AddIcon />}
            onClick={() => setShowCreate((v) => !v)}
          >
            {t("manage.tasks.newTask")}
          </Button>
        </CardContent>
      </Card>

      <Collapse in={showCreate}>
        <CreateTaskForm
          onCreate={onCreate}
          onClose={() => setShowCreate(false)}
        />
      </Collapse>

      {sorted.map((task) => (
        <TaskCard
          key={task.id}
          task={task}
          onComplete={onComplete}
          onCancel={onCancel}
          onPostpone={onPostpone}
        />
      ))}
      {!sorted.length && !loading ? (
        <Typography color="text.secondary">{t("manage.tasks.empty")}</Typography>
      ) : null}
    </Stack>
  );
}
