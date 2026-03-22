/**
 * TaskChecklist — renders a list of patient tasks with checkbox, title,
 * subtitle, due-date badge, urgency badge, and optional upload button.
 *
 * Props:
 *  - tasks: array of task objects
 *  - onComplete: (taskId) => void — called when user checks a pending task
 *  - onUpload: (taskId) => void — called when user taps upload on workup tasks
 */
import { Box, Typography } from "@mui/material";
import { TYPE, COLOR } from "../theme";
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
  try {
    return new Date(dueAt) < new Date();
  } catch {
    return false;
  }
}

function isWorkupTask(taskType) {
  return taskType && (taskType.includes("lab_review") || taskType.includes("imaging"));
}

function CheckCircle({ completed }) {
  if (completed) {
    return (
      <Box
        sx={{
          width: 20, height: 20, borderRadius: "50%",
          bgcolor: COLOR.success, display: "flex",
          alignItems: "center", justifyContent: "center", flexShrink: 0,
        }}
      >
        {/* White checkmark */}
        <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
          <path d="M2.5 6L5 8.5L9.5 3.5" stroke="#fff" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </Box>
    );
  }
  return (
    <Box
      sx={{
        width: 20, height: 20, borderRadius: "50%",
        border: `1.5px solid ${COLOR.border}`, flexShrink: 0,
      }}
    />
  );
}

export default function TaskChecklist({ tasks, onComplete, onUpload }) {
  if (!tasks || tasks.length === 0) return null;

  return (
    <Box sx={{ bgcolor: "#fff" }}>
      {tasks.map((task) => {
        const completed = task.status === "done" || task.status === "completed";
        const overdue = !completed && isOverdue(task.due_at);
        const workup = isWorkupTask(task.task_type);

        return (
          <Box
            key={task.id}
            sx={{
              display: "flex", alignItems: "center", gap: "12px",
              px: "12px", py: "8px",
              borderBottom: `0.5px solid #f0f0f0`,
            }}
          >
            {/* Checkbox */}
            <Box
              onClick={!completed && onComplete ? () => onComplete(task.id) : undefined}
              sx={{ cursor: !completed ? "pointer" : "default" }}
            >
              <CheckCircle completed={completed} />
            </Box>

            {/* Title + subtitle */}
            <Box sx={{ flex: 1, minWidth: 0 }}>
              <Typography
                sx={{
                  fontSize: 15, fontWeight: 500,
                  color: completed ? COLOR.text4 : COLOR.text1,
                  textDecoration: completed ? "line-through" : "none",
                  lineHeight: 1.4,
                }}
              >
                {task.title}
              </Typography>
              {task.content && (
                <Typography
                  sx={{
                    fontSize: 13, fontWeight: 400, color: COLOR.text4,
                    lineHeight: 1.4, mt: 0.2,
                    overflow: "hidden", textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}
                >
                  {task.content}
                </Typography>
              )}
            </Box>

            {/* Urgency badge for workup tasks */}
            {workup && task.urgency && (
              <StatusBadge
                label={task.urgency}
                colorMap={{ "\u7D27\u6025": COLOR.danger, "\u5E38\u89C4": COLOR.text4 }}
              />
            )}

            {/* Due date badge */}
            {task.due_at && !completed && (
              <Typography
                sx={{
                  ...TYPE.caption,
                  color: overdue ? COLOR.danger : COLOR.text4,
                  fontWeight: overdue ? 500 : 400,
                  flexShrink: 0,
                }}
              >
                {formatDate(task.due_at)}
              </Typography>
            )}

            {/* Completion date for done tasks */}
            {completed && task.completed_at && (
              <Typography
                sx={{
                  ...TYPE.caption,
                  color: COLOR.success,
                  flexShrink: 0,
                }}
              >
                {formatDate(task.completed_at)}
              </Typography>
            )}

            {/* Upload button for workup tasks */}
            {workup && !completed && onUpload && (
              <AppButton
                variant="ghost"
                size="sm"
                onClick={() => onUpload(task.id)}
              >
                上传
              </AppButton>
            )}
          </Box>
        );
      })}
    </Box>
  );
}
