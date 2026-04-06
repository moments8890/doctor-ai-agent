/**
 * TaskDetailSubpage — full task detail view.
 *
 * Shows task title + urgency, patient link, due date, source,
 * content, notes (editable), reminder, mark complete, delete.
 *
 * Props: { taskId, doctorId, onBack, isMobile }
 */
import { useCallback, useEffect, useState } from "react";
import { Box, Typography } from "@mui/material";
import { useQueryClient } from "@tanstack/react-query";
import { QK } from "../../../lib/queryKeys";
import { useApi } from "../../../api/ApiContext";
import { useAppNavigate } from "../../../hooks/useAppNavigate";
import SubpageHeader from "../../../components/SubpageHeader";
import AppButton from "../../../components/AppButton";
import SectionLoading from "../../../components/SectionLoading";
import ConfirmDialog from "../../../components/ConfirmDialog";
import Toast, { useToast } from "../../../components/Toast";
import { TYPE, COLOR, RADIUS } from "../../../theme";
import { dp } from "../../../utils/doctorBasePath";

const SOURCE_LABELS = {
  manual: "医生手动创建",
  rule: "知识规则 → 自动生成",
  diagnosis_auto: "AI诊断审核 → 自动生成",
};

const TYPE_LABELS = {
  general: "通用",
  review: "审核",
  follow_up: "随访",
  medication: "用药",
  checkup: "检查",
};

function dueLabel(dueAt) {
  if (!dueAt) return null;
  const d = new Date(dueAt);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const tomorrow = new Date(today);
  tomorrow.setDate(tomorrow.getDate() + 1);
  const dDate = new Date(d);
  dDate.setHours(0, 0, 0, 0);

  const dateStr = dueAt.slice(0, 10);
  if (dDate.getTime() < today.getTime()) return { text: `${dateStr} (已过期)`, color: COLOR.danger };
  if (dDate.getTime() === today.getTime()) return { text: `${dateStr} (今天)`, color: COLOR.danger };
  if (dDate.getTime() === tomorrow.getTime()) return { text: `${dateStr} (明天)`, color: COLOR.warning };
  return { text: dateStr, color: COLOR.text2 };
}

function DetailField({ label, children, color }) {
  return (
    <Box sx={{ display: "flex", gap: 1.5, px: 2, py: 1, borderBottom: `0.5px solid ${COLOR.borderLight}` }}>
      <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4, flexShrink: 0, minWidth: 48 }}>
        {label}
      </Typography>
      <Box sx={{ fontSize: TYPE.secondary.fontSize, color: color || COLOR.text2, lineHeight: 1.5, flex: 1 }}>
        {children}
      </Box>
    </Box>
  );
}

export default function TaskDetailSubpage({ taskId, doctorId, onBack, isMobile }) {
  const api = useApi();
  const queryClient = useQueryClient();
  const navigate = useAppNavigate();
  const [task, setTask] = useState(null);
  const [loading, setLoading] = useState(true);
  const [notes, setNotes] = useState("");
  const [notesDirty, setNotesDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [completing, setCompleting] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [toast, showToast] = useToast();

  const load = useCallback(async () => {
    if (!taskId || !doctorId) return;
    setLoading(true);
    try {
      const data = await (api.getTaskById || (() => Promise.resolve(null)))(taskId, doctorId);
      setTask(data);
      setNotes(data?.notes || "");
    } catch {
      showToast("加载失败");
    } finally {
      setLoading(false);
    }
  }, [taskId, doctorId, api]);

  useEffect(() => { load(); }, [load]);

  const handleSaveNotes = async () => {
    if (!notesDirty || saving) return;
    setSaving(true);
    try {
      await (api.patchTaskNotes || (() => Promise.resolve()))(taskId, doctorId, notes);
      setNotesDirty(false);
      showToast("备注已保存");
    } catch {
      showToast("保存失败");
    } finally {
      setSaving(false);
    }
  };

  const handleComplete = async () => {
    if (completing) return;
    setCompleting(true);
    try {
      await (api.patchTask || (() => Promise.resolve()))(taskId, doctorId, "completed");
      queryClient.invalidateQueries({ queryKey: QK.tasks(doctorId, "pending") });
      queryClient.invalidateQueries({ queryKey: QK.tasks(doctorId, "completed") });
      queryClient.invalidateQueries({ queryKey: QK.draftSummary(doctorId) });
      showToast("已标记完成");
      setTimeout(() => onBack?.(), 400);
    } catch {
      showToast("操作失败");
      setCompleting(false);
    }
  };

  const handleDelete = async () => {
    if (deleting) return;
    setDeleting(true);
    try {
      await (api.patchTask || (() => Promise.resolve()))(taskId, doctorId, "cancelled");
      queryClient.invalidateQueries({ queryKey: QK.tasks(doctorId, "pending") });
      queryClient.invalidateQueries({ queryKey: QK.tasks(doctorId, "completed") });
      queryClient.invalidateQueries({ queryKey: QK.draftSummary(doctorId) });
      showToast("已删除");
      setTimeout(() => onBack?.(), 400);
    } catch {
      showToast("删除失败");
      setDeleting(false);
    }
  };

  if (loading) {
    return (
      <Box sx={{ display: "flex", flexDirection: "column", height: "100%", bgcolor: COLOR.surfaceAlt }}>
        <SubpageHeader title="任务详情" onBack={onBack} />
        <SectionLoading py={6} />
      </Box>
    );
  }

  if (!task) {
    return (
      <Box sx={{ display: "flex", flexDirection: "column", height: "100%", bgcolor: COLOR.surfaceAlt }}>
        <SubpageHeader title="任务详情" onBack={onBack} />
        <Box sx={{ py: 6, textAlign: "center" }}>
          <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text4 }}>任务不存在</Typography>
        </Box>
      </Box>
    );
  }

  const isCompleted = task.status === "completed";
  const due = dueLabel(task.due_at);
  const isUrgent = due?.color === COLOR.danger;
  const sourceLabel = SOURCE_LABELS[task.source_type] || "系统创建";

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%", bgcolor: COLOR.surfaceAlt }}>
      <SubpageHeader title="任务详情" onBack={onBack} />

      <Box sx={{ flex: 1, overflow: "auto", pb: "80px" }}>
        {/* Task header card */}
        <Box sx={{ mt: 1, bgcolor: COLOR.white, borderTop: `0.5px solid ${COLOR.border}`, borderBottom: `0.5px solid ${COLOR.border}` }}>
          {/* Title row */}
          <Box sx={{ px: 2, py: 1.5, borderBottom: `0.5px solid ${COLOR.borderLight}`, display: "flex", alignItems: "center", gap: 1 }}>
            <Box sx={{ width: 8, height: 8, borderRadius: "50%", bgcolor: isUrgent ? COLOR.danger : COLOR.warning, flexShrink: 0 }} />
            <Typography sx={{ fontSize: TYPE.action.fontSize, fontWeight: 600, flex: 1 }}>
              {task.title}
            </Typography>
            {isUrgent && (
              <Box component="span" sx={{ fontSize: TYPE.micro.fontSize, fontWeight: 600, bgcolor: COLOR.danger, color: COLOR.white, borderRadius: RADIUS.sm, px: 0.75, py: 0.25, lineHeight: 1.5 }}>
                紧急
              </Box>
            )}
          </Box>

          {/* Detail fields */}
          {task.patient_name && (
            <DetailField label="患者">
              <Typography
                component="span"
                onClick={() => task.patient_id && navigate(`${dp("patients")}/${task.patient_id}`)}
                sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.primary, cursor: task.patient_id ? "pointer" : "default", "&:active": { opacity: 0.6 } }}
              >
                {task.patient_name} ›
              </Typography>
            </DetailField>
          )}

          {due && (
            <DetailField label="截止" color={due.color}>
              {due.text}
            </DetailField>
          )}

          <DetailField label="来源">
            {sourceLabel}
          </DetailField>

          <DetailField label="类型">
            {TYPE_LABELS[task.task_type] || task.task_type}
          </DetailField>

          {task.content && (
            <DetailField label="详情">
              {task.content}
            </DetailField>
          )}

          {task.record_id && (
            <DetailField label="关联">
              <Typography
                component="span"
                onClick={() => navigate(`${dp("review")}/${task.record_id}`)}
                sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.primary, cursor: "pointer", "&:active": { opacity: 0.6 } }}
              >
                查看关联记录 ›
              </Typography>
            </DetailField>
          )}

          {/* Action buttons — cancel LEFT (grey), primary RIGHT (green) */}
          {!isCompleted && (
            <Box sx={{ display: "flex", gap: 1, px: 2, py: 1.5, borderTop: `0.5px solid ${COLOR.borderLight}` }}>
              {task.patient_id && (
                <AppButton variant="secondary" size="md" fullWidth onClick={() => navigate(`${dp("patients")}/${task.patient_id}`)}>
                  查看患者
                </AppButton>
              )}
              <AppButton variant="primary" size="md" fullWidth onClick={handleComplete} loading={completing}>
                标记完成
              </AppButton>
            </Box>
          )}

          {isCompleted && (
            <Box sx={{ px: 2, py: 1.5, borderTop: `0.5px solid ${COLOR.borderLight}` }}>
              <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.primary, fontWeight: 500 }}>
                已完成 {task.completed_at ? task.completed_at.slice(0, 10) : ""}
              </Typography>
            </Box>
          )}
        </Box>

        {/* Notes section */}
        <Box sx={{ px: 2, py: 2 }}>
          <Typography sx={{ fontSize: TYPE.secondary.fontSize, fontWeight: 600, color: COLOR.text2, mb: 1 }}>
            备注
          </Typography>
          <Box
            component="textarea"
            value={notes}
            onChange={(e) => { setNotes(e.target.value); setNotesDirty(true); }}
            onBlur={handleSaveNotes}
            placeholder="添加备注..."
            sx={{
              width: "100%", minHeight: 60, p: 1.5,
              bgcolor: COLOR.white, border: `0.5px solid ${COLOR.border}`,
              borderRadius: RADIUS.md, fontSize: TYPE.secondary.fontSize,
              color: COLOR.text2, resize: "vertical",
              fontFamily: "inherit", outline: "none",
              "&:focus": { borderColor: COLOR.primary },
            }}
          />
          {notesDirty && (
            <Typography
              onClick={handleSaveNotes}
              sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.primary, mt: 0.5, cursor: "pointer" }}
            >
              {saving ? "保存中..." : "保存备注"}
            </Typography>
          )}
        </Box>

        {/* Reminder + Delete */}
        <Box sx={{ bgcolor: COLOR.white, borderTop: `0.5px solid ${COLOR.border}`, borderBottom: `0.5px solid ${COLOR.border}` }}>
          <Box sx={{ display: "flex", alignItems: "center", px: 2, py: 1.5, borderBottom: `0.5px solid ${COLOR.borderLight}` }}>
            <Typography sx={{ fontSize: TYPE.body.fontSize, flex: 1 }}>提醒</Typography>
            <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: task.reminder_at ? COLOR.primary : COLOR.text4 }}>
              {task.reminder_at ? task.reminder_at.slice(0, 16).replace("T", " ") : "未设置"}
            </Typography>
          </Box>

          {!isCompleted && (
            <Box
              onClick={() => setConfirmDelete(true)}
              sx={{ px: 2, py: 1.5, cursor: "pointer", "&:active": { opacity: 0.6 } }}
            >
              <Typography sx={{ fontSize: TYPE.body.fontSize, color: COLOR.danger }}>
                删除任务
              </Typography>
            </Box>
          )}
        </Box>
      </Box>

      {/* Delete confirmation — cancel LEFT (grey), danger RIGHT (red) */}
      <ConfirmDialog
        open={confirmDelete}
        onClose={() => setConfirmDelete(false)}
        title="确认删除"
        message={`确定要删除任务"${task.title}"吗？`}
        confirmLabel="删除"
        onConfirm={handleDelete}
        loading={deleting}
        danger
      />

      <Toast message={toast} />
    </Box>
  );
}
