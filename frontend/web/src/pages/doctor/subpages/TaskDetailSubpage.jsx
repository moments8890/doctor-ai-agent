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
import DescriptionOutlinedIcon from "@mui/icons-material/DescriptionOutlined";
import PersonOutlineOutlinedIcon from "@mui/icons-material/PersonOutlineOutlined";
import SubpageHeader from "../../../components/SubpageHeader";
import AppButton from "../../../components/AppButton";
import SectionLoading from "../../../components/SectionLoading";
import ConfirmDialog from "../../../components/ConfirmDialog";
import Toast, { useToast } from "../../../components/Toast";
import { TYPE, COLOR, RADIUS } from "../../../theme";
import { dp } from "../../../utils/doctorBasePath";



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

// ── AI Provenance source card ──
function SourceCard({ task, navigate }) {
  if (task.record_id) {
    // AI-generated task — link to the originating record
    const recordDate = task.record_created_at ? task.record_created_at.slice(0, 10) : null;
    const recordType = task.record_type || null;
    const description = recordDate && recordType
      ? `来自 ${recordDate} ${recordType} 记录`
      : "来自关联病历";

    return (
      <Box sx={{
        mx: 2, mt: 1.5, mb: 0.5, px: 2, py: 1.5,
        bgcolor: COLOR.surface, borderRadius: RADIUS.md,
      }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 0.75, mb: 0.75 }}>
          <DescriptionOutlinedIcon sx={{ fontSize: 14, color: COLOR.text4 }} />
          <Typography sx={{ fontSize: TYPE.micro.fontSize, fontWeight: 500, color: COLOR.text4 }}>
            AI生成来源
          </Typography>
        </Box>
        <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text2, mb: 0.75 }}>
          {description}
        </Typography>
        <Typography
          onClick={() => navigate(`${dp("patients")}/${task.patient_id}?view=record&record=${task.record_id}`)}
          sx={{
            fontSize: TYPE.caption.fontSize, color: COLOR.primary,
            cursor: "pointer", fontWeight: 500,
            "&:active": { opacity: 0.6 },
          }}
        >
          查看原记录 ›
        </Typography>
      </Box>
    );
  }

  // Manual task — simple gray label
  return (
    <Box sx={{
      mx: 2, mt: 1.5, mb: 0.5, px: 2, py: 1.5,
      bgcolor: COLOR.surface, borderRadius: RADIUS.md,
      display: "flex", alignItems: "center", gap: 0.75,
    }}>
      <PersonOutlineOutlinedIcon sx={{ fontSize: 14, color: COLOR.text4 }} />
      <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text4 }}>
        来源：医生手动创建
      </Typography>
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
      queryClient.invalidateQueries({ queryKey: QK.tasks(doctorId, "pending") });
      queryClient.invalidateQueries({ queryKey: QK.tasks(doctorId, "completed") });
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

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%", bgcolor: COLOR.surfaceAlt }}>
      <SubpageHeader title="任务详情" onBack={onBack} />

      <Box sx={{ flex: 1, overflow: "auto", pb: "80px" }}>
        {/* Task header card */}
        <Box sx={{ mt: 1, bgcolor: COLOR.white, borderTop: `0.5px solid ${COLOR.border}`, borderBottom: `0.5px solid ${COLOR.border}` }}>
          {/* Title + subtitle */}
          <Box sx={{ px: 2, py: 1.5, borderBottom: `0.5px solid ${COLOR.borderLight}` }}>
            <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
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
            {task.content && (
              <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text3, mt: 0.5, ml: "16px" }}>
                {task.content}
              </Typography>
            )}
          </Box>

          {/* AI provenance — source card */}
          <SourceCard task={task} navigate={navigate} />

          {/* Detail fields — only patient + due date */}
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

        {/* Notes — inline editable row, same layout as DetailField */}
        <Box sx={{ bgcolor: COLOR.white, borderTop: `0.5px solid ${COLOR.border}`, borderBottom: `0.5px solid ${COLOR.border}`, mt: 1 }}>
          <Box sx={{ display: "flex", gap: 1.5, px: 2, py: 1 }}>
            <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4, flexShrink: 0, minWidth: 48 }}>备注</Typography>
            <Box
              component="input"
              value={notes}
              onChange={(e) => { setNotes(e.target.value); setNotesDirty(true); }}
              onBlur={handleSaveNotes}
              placeholder="添加备注..."
              sx={{
                flex: 1, border: "none", outline: "none", p: 0,
                fontSize: TYPE.secondary.fontSize, color: COLOR.text2,
                fontFamily: "inherit", bgcolor: "transparent",
                "&::placeholder": { color: COLOR.text4 },
              }}
            />
            {saving && <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4, flexShrink: 0 }}>保存中</Typography>}
          </Box>
        </Box>

        {/* Delete */}
        {!isCompleted && (
          <Box sx={{ px: 2, py: 2 }}>
            <Typography
              onClick={() => setConfirmDelete(true)}
              sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4, cursor: "pointer", "&:active": { opacity: 0.6 } }}
            >
              删除任务
            </Typography>
          </Box>
        )}
      </Box>

      {/* Delete confirmation — cancel LEFT (grey), danger RIGHT (red) */}
      <ConfirmDialog
        open={confirmDelete}
        onClose={() => setConfirmDelete(false)}
        onCancel={() => setConfirmDelete(false)}
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
