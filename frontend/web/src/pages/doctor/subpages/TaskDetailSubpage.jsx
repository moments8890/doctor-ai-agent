/**
 * TaskDetailSubpage — WeChat-style task detail with patient context,
 * info rows, optional linked record, and sticky action footer.
 *
 * Handles three cases:
 *  - Review task: patient + linked record
 *  - Patient task: patient, no record
 *  - General task: no patient, no record
 *
 * @see /debug/doctor/tasks/task/:id
 */
import { Box, Typography } from "@mui/material";
import { TASK_TYPE_LABEL } from "../constants";
import NameAvatar from "../../../components/NameAvatar";
import SubpageHeader from "../../../components/SubpageHeader";
import AppButton from "../../../components/AppButton";
import { TYPE, COLOR } from "../../../theme";

const RECORD_TYPE_LABEL = {
  visit: "门诊记录", dictation: "语音记录", import: "导入记录",
  interview_summary: "预问诊记录", lab: "检验", imaging: "影像",
};

function isOverdue(dueAt) {
  if (!dueAt) return false;
  return new Date(dueAt) < new Date(new Date().toDateString());
}

/* ── Patient Card ── */

function PatientCard({ name, patientId, age, gender, onClick }) {
  const genderStr = gender ? ({ male: "男", female: "女" }[gender] || gender) : null;
  const subtitle = [genderStr, age ? `${age}岁` : null].filter(Boolean).join(" · ");
  return (
    <Box onClick={onClick}
      sx={{
        display: "flex", alignItems: "center", gap: 1.5,
        bgcolor: COLOR.white, px: 2, py: 1.5, mb: 1,
        cursor: onClick ? "pointer" : "default",
        "&:active": onClick ? { bgcolor: COLOR.surfaceAlt } : {},
      }}>
      <NameAvatar name={name} size={40} />
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Typography sx={{ fontSize: TYPE.action.fontSize, fontWeight: 600, color: COLOR.text1 }}>{name}</Typography>
        {subtitle && <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4, mt: 0.2 }}>{subtitle}</Typography>}
      </Box>
      {onClick && <Typography sx={{ color: COLOR.text4, fontSize: TYPE.caption.fontSize }}>›</Typography>}
    </Box>
  );
}

/* ── Info Row ── */

function InfoRow({ label, value, valueColor }) {
  return (
    <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", px: 2, py: 1, borderTop: `0.5px solid ${COLOR.borderLight}` }}>
      <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text4 }}>{label}</Typography>
      <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: valueColor || COLOR.text2 }}>{value}</Typography>
    </Box>
  );
}

/* ── Linked Record Card ── */

function LinkedRecordCard({ record, onClick }) {
  const typeLabel = RECORD_TYPE_LABEL[record.record_type] || "病历记录";
  const preview = record.structured?.chief_complaint || record.content || "";
  return (
    <Box onClick={onClick}
      sx={{
        bgcolor: COLOR.white, px: 2, py: 1.5, mb: 1,
        cursor: onClick ? "pointer" : "default",
        "&:active": onClick ? { bgcolor: COLOR.surfaceAlt } : {},
      }}>
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 0.5 }}>
        <Typography sx={{ fontSize: TYPE.secondary.fontSize, fontWeight: 500, color: COLOR.text1 }}>{typeLabel}</Typography>
        <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
          <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4 }}>{record.created_at?.slice(0, 10)}</Typography>
          {onClick && <Typography sx={{ color: COLOR.text4, fontSize: TYPE.caption.fontSize }}>›</Typography>}
        </Box>
      </Box>
      {preview && (
        <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text3, lineHeight: 1.5 }}>
          {preview}
        </Typography>
      )}
    </Box>
  );
}

/* ── Main ── */

export default function TaskDetailSubpage({
  task,
  patient,
  record,
  recentRecords = [],
  onBack,
  onComplete,
  onPostpone,
  onCancel,
  onPatientTap,
  onRecordTap,
}) {
  const taskTitle = task.title || TASK_TYPE_LABEL[task.task_type] || task.task_type;
  const typeLabel = TASK_TYPE_LABEL[task.task_type] || task.task_type;
  const statusLabel = task.status === "pending" ? "待处理"
    : task.status === "completed" || task.status === "done" ? "已完成"
    : task.status === "cancelled" ? "已取消"
    : task.status;
  const overdue = isOverdue(task.due_at) && task.status === "pending";
  const isPending = task.status === "pending";

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%", bgcolor: COLOR.surfaceAlt }}>
      <SubpageHeader title={taskTitle} onBack={onBack} />

      <Box sx={{ flex: 1, overflowY: "auto", pb: isPending ? "72px" : 2 }}>
        {/* Patient card — only if task has patient */}
        {task.patient_name && (
          <PatientCard
            name={task.patient_name}
            patientId={task.patient_id}
            gender={patient?.gender}
            age={patient?.year_of_birth ? new Date().getFullYear() - patient.year_of_birth : null}
            onClick={onPatientTap}
          />
        )}

        {/* Task info rows */}
        <Box sx={{ bgcolor: COLOR.white, mb: 1 }}>
          <InfoRow label="类型" value={typeLabel} />
          <InfoRow label="状态" value={statusLabel} />
          {task.due_at && (
            <InfoRow
              label="截止"
              value={task.due_at.slice(0, 10)}
              valueColor={overdue ? COLOR.danger : undefined}
            />
          )}
          {task.content && (
            <Box sx={{ px: 2, py: 1, borderTop: `0.5px solid ${COLOR.borderLight}` }}>
              <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4, mb: 0.5 }}>备注</Typography>
              <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text2, lineHeight: 1.6, whiteSpace: "pre-wrap" }}>
                {task.content}
              </Typography>
            </Box>
          )}
        </Box>

        {/* Linked record — only if exists */}
        {record && (
          <LinkedRecordCard record={record} onClick={onRecordTap} />
        )}

        {/* Recent records — when task has patient but no linked record */}
        {!record && recentRecords.length > 0 && (
          <Box sx={{ bgcolor: COLOR.white, mb: 1 }}>
            <Box sx={{ px: 2, py: 1, borderBottom: `0.5px solid ${COLOR.borderLight}` }}>
              <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4 }}>最近病历</Typography>
            </Box>
            {recentRecords.map(r => (
              <LinkedRecordCard key={r.id} record={r} />
            ))}
          </Box>
        )}
      </Box>

      {/* Sticky action footer — only for pending tasks */}
      {isPending && (
        <Box sx={{
          position: "absolute", bottom: 0, left: 0, right: 0,
          bgcolor: COLOR.white, borderTop: `0.5px solid ${COLOR.border}`,
          display: "flex", alignItems: "center", gap: 1,
          px: 2, py: 1,
          paddingBottom: "calc(10px + env(safe-area-inset-bottom))",
        }}>
          <Typography onClick={() => onPostpone?.(task.id)}
            sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text3, cursor: "pointer", "&:active": { opacity: 0.6 } }}>
            推迟
          </Typography>
          <Typography onClick={() => onCancel?.(task.id)}
            sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text4, cursor: "pointer", ml: 1, "&:active": { opacity: 0.6 } }}>
            取消
          </Typography>
          <Box sx={{ flex: 1 }} />
          <AppButton variant="primary" size="sm" onClick={() => onComplete?.(task.id, "completed")}>
            完成任务
          </AppButton>
        </Box>
      )}
    </Box>
  );
}
