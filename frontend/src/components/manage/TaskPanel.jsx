import { useMemo, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  Typography,
} from "@mui/material";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";
import CancelOutlinedIcon from "@mui/icons-material/CancelOutlined";
import AccessTimeIcon from "@mui/icons-material/AccessTime";
import WarningAmberRoundedIcon from "@mui/icons-material/WarningAmberRounded";
import { t } from "../../i18n";

function isOverdue(dueAt) {
  if (!dueAt) return false;
  return new Date(dueAt) < new Date();
}

function isDueSoon(dueAt) {
  if (!dueAt) return false;
  const diff = new Date(dueAt) - new Date();
  return diff >= 0 && diff < 48 * 60 * 60 * 1000; // within 48h
}

function formatDue(dueAt) {
  if (!dueAt) return null;
  const d = new Date(dueAt);
  return d.toLocaleDateString("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function TaskTypeChip({ taskType }) {
  const label = t(`manage.tasks.taskType.${taskType}`) || taskType;
  const colorMap = {
    follow_up: "primary",
    medication: "secondary",
    lab_review: "info",
    referral: "warning",
    imaging: "default",
  };
  return <Chip size="small" color={colorMap[taskType] || "default"} label={label} />;
}

function TaskCard({ task, onComplete, onCancel }) {
  const overdue = isOverdue(task.due_at);
  const dueSoon = isDueSoon(task.due_at);
  const isPending = task.status === "pending";

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
            {task.trigger_reason ? (
              <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.2 }}>
                {t("manage.tasks.triggerReason")}：{task.trigger_reason}
              </Typography>
            ) : null}
            {task.due_at ? (
              <Typography
                variant="caption"
                sx={{ display: "block", mt: 0.2, color: overdue && isPending ? "error.main" : "text.secondary" }}
              >
                {t("manage.tasks.dueAt")}：{formatDue(task.due_at)}
              </Typography>
            ) : null}
          </Box>
          {isPending ? (
            <Stack direction="row" spacing={0.7}>
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

export default function TaskPanel({ tasks, loading, error, onComplete, onCancel }) {
  const [statusFilter, setStatusFilter] = useState("pending");

  const filtered = useMemo(() => {
    if (!statusFilter) return tasks;
    return tasks.filter((t) => t.status === statusFilter);
  }, [tasks, statusFilter]);

  // Sort: overdue first, then pending, then by due_at
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
        <CardContent sx={{ display: "flex", gap: 1 }}>
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
        </CardContent>
      </Card>

      {sorted.map((task) => (
        <TaskCard
          key={task.id}
          task={task}
          onComplete={onComplete}
          onCancel={onCancel}
        />
      ))}
      {!sorted.length && !loading ? (
        <Typography color="text.secondary">{t("manage.tasks.empty")}</Typography>
      ) : null}
    </Stack>
  );
}
