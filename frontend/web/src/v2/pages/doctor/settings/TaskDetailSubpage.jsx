/**
 * @route /doctor/tasks/:taskId
 *
 * TaskDetailSubpage v2 — full task detail view.
 * antd-mobile only, no MUI.
 *
 * Shows task title + urgency, patient link, due date, source,
 * notes (inline editable), mark complete, delete.
 */
import { useCallback, useEffect, useState } from "react";
import { SafeArea, NavBar, Button, Toast, Dialog, List } from "antd-mobile";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { QK } from "../../../../lib/queryKeys";
import { useApi } from "../../../../api/ApiContext";
import { useDoctorStore } from "../../../../store/doctorStore";
import { APP, FONT, RADIUS } from "../../../theme";
import { pageContainer, navBarStyle, scrollable } from "../../../layouts";
import { LoadingCenter, ActionFooter } from "../../../components";
import SubpageBackHome from "../../../components/SubpageBackHome";

// ── Helpers ────────────────────────────────────────────────────────

function dueLabel(dueAt) {
  if (!dueAt) return null;
  const normalized =
    dueAt.includes("Z") || dueAt.includes("+") ? dueAt : dueAt + "Z";
  const d = new Date(normalized);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const tomorrow = new Date(today);
  tomorrow.setDate(tomorrow.getDate() + 1);
  const dDate = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const dateStr = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  if (dDate.getTime() < today.getTime())
    return { text: `${dateStr} (已过期)`, color: APP.danger };
  if (dDate.getTime() === today.getTime())
    return { text: `${dateStr} (今天)`, color: APP.danger };
  if (dDate.getTime() === tomorrow.getTime())
    return { text: `${dateStr} (明天)`, color: APP.warning };
  return { text: dateStr, color: APP.text3 };
}

// ── Source card ────────────────────────────────────────────────────

function SourceCard({ task, navigate }) {
  if (task.record_id) {
    const recordDate = task.record_created_at
      ? task.record_created_at.slice(0, 10)
      : null;
    const recordType = task.record_type || null;
    const description =
      recordDate && recordType
        ? `来自 ${recordDate} ${recordType} 记录`
        : "来自关联病历";

    return (
      <div
        style={{
          margin: "12px 16px 4px",
          padding: "12px 16px",
          backgroundColor: APP.surfaceAlt,
          borderRadius: RADIUS.md,
          border: `0.5px solid ${APP.borderLight}`,
        }}
      >
        <div
          style={{
            fontSize: FONT.xs,
            fontWeight: 600,
            color: APP.text4,
            marginBottom: 6,
          }}
        >
          AI生成来源
        </div>
        <div style={{ fontSize: FONT.base, color: APP.text2, marginBottom: 6 }}>
          {description}
        </div>
        {task.patient_id && (
          <span
            onClick={() =>
              navigate(
                `/doctor/patients/${task.patient_id}?view=record&record=${task.record_id}`
              )
            }
            style={{
              fontSize: FONT.sm,
              color: APP.primary,
              fontWeight: 500,
              cursor: "pointer",
            }}
          >
            查看原记录 ›
          </span>
        )}
      </div>
    );
  }

  return (
    <div
      style={{
        margin: "12px 16px 4px",
        padding: "10px 16px",
        backgroundColor: APP.surfaceAlt,
        borderRadius: RADIUS.md,
        border: `0.5px solid ${APP.borderLight}`,
        display: "flex",
        alignItems: "center",
        gap: 8,
      }}
    >
      <span style={{ fontSize: FONT.base, color: APP.text4 }}>来源：医生手动创建</span>
    </div>
  );
}

// ── Main ───────────────────────────────────────────────────────────

export default function TaskDetailSubpage({ taskId: taskIdProp }) {
  const navigate = useNavigate();
  const api = useApi();
  const queryClient = useQueryClient();
  const { doctorId } = useDoctorStore();

  // Support receiving taskId either as a prop or from the URL path
  const taskId = taskIdProp;

  const [task, setTask] = useState(null);
  const [loading, setLoading] = useState(true);
  const [notes, setNotes] = useState("");
  const [notesDirty, setNotesDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [completing, setCompleting] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const load = useCallback(async () => {
    if (!taskId || !doctorId) return;
    setLoading(true);
    try {
      const data = await (api.getTaskById || (() => Promise.resolve(null)))(
        taskId,
        doctorId
      );
      setTask(data);
      setNotes(data?.notes || "");
    } catch {
      Toast.show({ content: "加载失败", position: "bottom" });
    } finally {
      setLoading(false);
    }
  }, [taskId, doctorId, api]);

  useEffect(() => {
    load();
  }, [load]);

  async function handleSaveNotes() {
    if (!notesDirty || saving) return;
    setSaving(true);
    try {
      await (api.patchTaskNotes || (() => Promise.resolve()))(
        taskId,
        doctorId,
        notes
      );
      queryClient.invalidateQueries({ queryKey: QK.tasks(doctorId, "pending") });
      queryClient.invalidateQueries({
        queryKey: QK.tasks(doctorId, "completed"),
      });
      setNotesDirty(false);
      Toast.show({ content: "备注已保存", position: "bottom" });
    } catch {
      Toast.show({ content: "保存失败", position: "bottom" });
    } finally {
      setSaving(false);
    }
  }

  async function handleComplete() {
    if (completing) return;
    setCompleting(true);
    try {
      await (api.patchTask || (() => Promise.resolve()))(
        taskId,
        doctorId,
        "completed"
      );
      queryClient.invalidateQueries({ queryKey: QK.tasks(doctorId, "pending") });
      queryClient.invalidateQueries({
        queryKey: QK.tasks(doctorId, "completed"),
      });
      Toast.show({ content: "已标记完成", position: "bottom" });
      setTimeout(() => navigate(-1), 400);
    } catch {
      Toast.show({ content: "操作失败", position: "bottom" });
      setCompleting(false);
    }
  }

  function confirmDelete() {
    Dialog.confirm({
      title: "确认删除",
      content: `确定要删除任务"${task?.title}"吗？`,
      confirmText: "删除",
      cancelText: "取消",
      onConfirm: handleDelete,
    });
  }

  async function handleDelete() {
    if (deleting) return;
    setDeleting(true);
    try {
      await (api.patchTask || (() => Promise.resolve()))(
        taskId,
        doctorId,
        "cancelled"
      );
      queryClient.invalidateQueries({ queryKey: QK.tasks(doctorId, "pending") });
      queryClient.invalidateQueries({
        queryKey: QK.tasks(doctorId, "completed"),
      });
      Toast.show({ content: "已删除", position: "bottom" });
      setTimeout(() => navigate(-1), 400);
    } catch {
      Toast.show({ content: "删除失败", position: "bottom" });
      setDeleting(false);
    }
  }

  // ── Render ───────────────────────────────────────────────────────

  if (loading) {
    return (
      <div style={pageContainer}>
        <SafeArea position="top" />
        <NavBar backArrow={<SubpageBackHome />} onBack={() => navigate(-1)} style={navBarStyle}>任务详情</NavBar>
        <LoadingCenter />
      </div>
    );
  }

  if (!task) {
    return (
      <div style={pageContainer}>
        <NavBar backArrow={<SubpageBackHome />} onBack={() => navigate(-1)} style={navBarStyle}>任务详情</NavBar>
        <div style={{ paddingTop: 64, textAlign: "center", color: APP.text4, fontSize: FONT.base }}>
          任务不存在
        </div>
      </div>
    );
  }

  const isCompleted = task.status === "completed";
  const due = dueLabel(task.due_at);
  const isUrgent = due?.color === APP.danger;

  return (
    <div style={pageContainer}>
      <NavBar backArrow={<SubpageBackHome />} onBack={() => navigate(-1)} style={navBarStyle}>
        任务详情
      </NavBar>

      <div style={scrollable}>
        {/* Task header */}
        <List>
          <List.Item
            prefix={
              <div
                style={{
                  width: 8,
                  height: 8,
                  borderRadius: "50%",
                  backgroundColor: isUrgent ? APP.danger : APP.warning,
                  flexShrink: 0,
                }}
              />
            }
            extra={
              isUrgent ? (
                <span
                  style={{
                    fontSize: FONT.xs,
                    fontWeight: 600,
                    backgroundColor: APP.danger,
                    color: APP.white,
                    borderRadius: RADIUS.xs,
                    padding: "2px 6px",
                  }}
                >
                  紧急
                </span>
              ) : undefined
            }
            description={task.content || undefined}
          >
            <span style={{ fontWeight: 600, fontSize: FONT.md }}>{task.title}</span>
          </List.Item>
        </List>

        {/* Source card */}
        <SourceCard task={task} navigate={navigate} />

        {/* Detail fields */}
        <List style={{ marginTop: 8 }}>
          {task.patient_name && (
            <List.Item
              arrow={!!task.patient_id}
              onClick={task.patient_id ? () => navigate(`/doctor/patients/${task.patient_id}`) : undefined}
              extra={<span style={{ color: APP.primary }}>{task.patient_name}</span>}
            >
              患者
            </List.Item>
          )}
          {due && (
            <List.Item extra={<span style={{ color: due.color }}>{due.text}</span>}>
              截止
            </List.Item>
          )}
          <List.Item
            extra={saving ? <span style={{ fontSize: FONT.sm, color: APP.text4 }}>保存中</span> : undefined}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ color: APP.text4, fontSize: FONT.sm, flexShrink: 0 }}>备注</span>
              <input
                value={notes}
                onChange={(e) => { setNotes(e.target.value); setNotesDirty(true); }}
                onBlur={handleSaveNotes}
                placeholder="添加备注..."
                style={{
                  flex: 1, border: "none", outline: "none", padding: 0,
                  fontSize: FONT.base, color: APP.text2, fontFamily: "inherit",
                  backgroundColor: "transparent",
                }}
              />
            </div>
          </List.Item>
          {isCompleted && (
            <List.Item extra={<span style={{ color: APP.primary, fontWeight: 500 }}>已完成 {task.completed_at ? task.completed_at.slice(0, 10) : ""}</span>}>
              状态
            </List.Item>
          )}
        </List>

        {/* Delete link */}
        {!isCompleted && (
          <div style={{ padding: 16 }}>
            <span
              onClick={confirmDelete}
              style={{ fontSize: FONT.base, color: APP.text4, cursor: "pointer" }}
            >
              删除任务
            </span>
          </div>
        )}
      </div>

      {/* Bottom action bar */}
      {!isCompleted && (
        <ActionFooter>
          {task.patient_id && (
            <Button block fill="outline" onClick={() => navigate(`/doctor/patients/${task.patient_id}`)}>
              查看患者
            </Button>
          )}
          <Button block color="primary" loading={completing} onClick={handleComplete}>
            标记完成
          </Button>
        </ActionFooter>
      )}
    </div>
  );
}
