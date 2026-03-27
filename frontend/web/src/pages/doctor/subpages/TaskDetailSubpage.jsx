/**
 * TaskDetailSubpage — shared presentational task detail view.
 *
 * Displays task info (type, status, due date, patient, content),
 * action buttons (complete/postpone/cancel), and an optional linked record.
 * Used by both real TasksPage (API data) and MockPages (static data).
 *
 * @see /debug/doctor-pages → 任务 → detail
 */
import { Box, Stack } from "@mui/material";
import { TASK_TYPE_LABEL } from "../constants";
import AppButton from "../../../components/AppButton";
import DetailCard from "../../../components/DetailCard";
import SubpageHeader from "../../../components/SubpageHeader";
import { COLOR } from "../../../theme";

const RECORD_TYPE_LABEL = {
  visit: "门诊记录", dictation: "语音记录", import: "导入记录", interview_summary: "预问诊记录",
};

export default function TaskDetailSubpage({
  task,
  record,
  onBack,
  onComplete,
  onPostpone,
  onCancel,
}) {
  const taskTitle = task.title || TASK_TYPE_LABEL[task.task_type] || task.task_type;
  const statusLabel = task.status === "pending" ? "待处理"
    : task.status === "completed" || task.status === "done" ? "已完成"
    : task.status === "cancelled" ? "已取消"
    : task.status;

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%", bgcolor: COLOR.surfaceAlt }}>
      <SubpageHeader title={task.patient_name || taskTitle} onBack={onBack} />
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
          {(task.status === "pending") && (
            <Stack spacing={1}>
              <Stack direction="row" spacing={1}>
                <AppButton variant="primary" size="sm" onClick={() => onComplete?.(task.id, "completed")}>完成任务</AppButton>
                <AppButton variant="secondary" size="sm" onClick={() => onPostpone?.(task.id)}>推迟</AppButton>
                <AppButton variant="danger" size="sm" onClick={() => onCancel?.(task.id)}>取消</AppButton>
              </Stack>
            </Stack>
          )}
        </DetailCard>

        {/* Linked record (optional — real page fetches from API) */}
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
