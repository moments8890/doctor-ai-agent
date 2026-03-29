/**
 * TaskChecklist — renders a list of patient tasks using ActionRow.
 *
 * Thin wrapper that maps task objects to ActionRow props, handling
 * overdue detection, urgency badges, and upload buttons.
 *
 * Props:
 *  - tasks: array of task objects
 *  - onComplete: (taskId) => void — called when user checks a pending task
 *  - onUndo: (taskId) => void — called when user unchecks a completed task
 *  - onUpload: (taskId) => void — called when user taps upload on workup tasks
 */
import { Box } from "@mui/material";
import { COLOR } from "../theme";
import ActionRow from "./ActionRow";
import StatusBadge from "./StatusBadge";
import AppButton from "./AppButton";

function formatDate(iso) {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleDateString("zh-CN", {
      year: "numeric", month: "2-digit", day: "2-digit",
    });
  } catch {
    return iso;
  }
}

function isOverdue(dueAt) {
  if (!dueAt) return false;
  try { return new Date(dueAt) < new Date(); } catch { return false; }
}

function isWorkupTask(taskType) {
  return taskType && (taskType.includes("lab_review") || taskType.includes("imaging"));
}

export default function TaskChecklist({ tasks, onComplete, onUndo, onUpload }) {
  if (!tasks || tasks.length === 0) return null;

  return (
    <Box sx={{ bgcolor: COLOR.white }}>
      {tasks.map((task) => {
        const completed = task.status === "done" || task.status === "completed";
        const overdue = !completed && isOverdue(task.due_at);
        const workup = isWorkupTask(task.task_type);

        return (
          <ActionRow
            key={task.id}
            title={task.title}
            subtitle={task.content}
            done={completed}
            overdue={overdue}
            right={
              completed && task.completed_at ? formatDate(task.completed_at)
              : task.due_at && !completed ? formatDate(task.due_at)
              : undefined
            }
            badge={workup && task.urgency ? (
              <StatusBadge label={task.urgency} colorMap={{ "\u7D27\u6025": COLOR.danger, "\u5E38\u89C4": COLOR.text4 }} />
            ) : undefined}
            action={workup && !completed && onUpload ? (
              <AppButton variant="ghost" size="sm" onClick={() => onUpload(task.id)}>上传</AppButton>
            ) : undefined}
            onToggle={
              !completed && onComplete ? () => onComplete(task.id)
              : completed && onUndo ? () => onUndo(task.id)
              : undefined
            }
          />
        );
      })}
    </Box>
  );
}
