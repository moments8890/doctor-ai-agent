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
import { NavBar, SpinLoading, Button, Toast, Dialog } from "antd-mobile";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { QK } from "../../../../lib/queryKeys";
import { useApi } from "../../../../api/ApiContext";
import { useDoctorStore } from "../../../../store/doctorStore";
import { APP } from "../../../theme";

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
    return { text: `${dateStr} (已过期)`, color: "#FA5151" };
  if (dDate.getTime() === today.getTime())
    return { text: `${dateStr} (今天)`, color: "#FA5151" };
  if (dDate.getTime() === tomorrow.getTime())
    return { text: `${dateStr} (明天)`, color: "#FFC300" };
  return { text: dateStr, color: APP.text3 };
}

// ── Detail field row ───────────────────────────────────────────────

function DetailField({ label, children, color }) {
  return (
    <div
      style={{
        display: "flex",
        gap: 12,
        padding: "10px 16px",
        borderBottom: `0.5px solid ${APP.borderLight}`,
      }}
    >
      <span
        style={{
          fontSize: 12,
          color: APP.text4,
          flexShrink: 0,
          minWidth: 40,
          lineHeight: "22px",
        }}
      >
        {label}
      </span>
      <div
        style={{
          fontSize: 14,
          color: color || APP.text2,
          lineHeight: 1.6,
          flex: 1,
        }}
      >
        {children}
      </div>
    </div>
  );
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
          borderRadius: 8,
          border: `0.5px solid ${APP.borderLight}`,
        }}
      >
        <div
          style={{
            fontSize: 11,
            fontWeight: 600,
            color: APP.text4,
            marginBottom: 6,
          }}
        >
          AI生成来源
        </div>
        <div style={{ fontSize: 13, color: APP.text2, marginBottom: 6 }}>
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
              fontSize: 12,
              color: "#07C160",
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
        borderRadius: 8,
        border: `0.5px solid ${APP.borderLight}`,
        display: "flex",
        alignItems: "center",
        gap: 8,
      }}
    >
      <span style={{ fontSize: 14, color: APP.text4 }}>来源：医生手动创建</span>
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
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          height: "100%",
          backgroundColor: APP.surfaceAlt,
        }}
      >
        <NavBar
          onBack={() => navigate(-1)}
          style={{
            "--height": "44px",
            "--border-bottom": `0.5px solid ${APP.border}`,
            backgroundColor: APP.surface,
            flexShrink: 0,
          }}
        >
          任务详情
        </NavBar>
        <div
          style={{ display: "flex", justifyContent: "center", paddingTop: 48 }}
        >
          <SpinLoading color="primary" />
        </div>
      </div>
    );
  }

  if (!task) {
    return (
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          height: "100%",
          backgroundColor: APP.surfaceAlt,
        }}
      >
        <NavBar
          onBack={() => navigate(-1)}
          style={{
            "--height": "44px",
            "--border-bottom": `0.5px solid ${APP.border}`,
            backgroundColor: APP.surface,
            flexShrink: 0,
          }}
        >
          任务详情
        </NavBar>
        <div
          style={{
            paddingTop: 64,
            textAlign: "center",
            color: APP.text4,
            fontSize: 14,
          }}
        >
          任务不存在
        </div>
      </div>
    );
  }

  const isCompleted = task.status === "completed";
  const due = dueLabel(task.due_at);
  const isUrgent = due?.color === "#FA5151";

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100%",
        backgroundColor: APP.surfaceAlt,
        overflow: "hidden",
      }}
    >
      <NavBar
        onBack={() => navigate(-1)}
        style={{
          "--height": "44px",
          "--border-bottom": `0.5px solid ${APP.border}`,
          backgroundColor: APP.surface,
          flexShrink: 0,
        }}
      >
        任务详情
      </NavBar>

      <div style={{ flex: 1, overflowY: "auto", paddingBottom: 80 }}>
        {/* Task header card */}
        <div
          style={{
            marginTop: 8,
            backgroundColor: APP.surface,
            borderTop: `0.5px solid ${APP.border}`,
            borderBottom: `0.5px solid ${APP.border}`,
          }}
        >
          {/* Title row */}
          <div
            style={{
              padding: "12px 16px",
              borderBottom: `0.5px solid ${APP.borderLight}`,
            }}
          >
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
              }}
            >
              <div
                style={{
                  width: 8,
                  height: 8,
                  borderRadius: "50%",
                  backgroundColor: isUrgent ? "#FA5151" : "#FFC300",
                  flexShrink: 0,
                }}
              />
              <span
                style={{
                  fontSize: 16,
                  fontWeight: 600,
                  color: APP.text1,
                  flex: 1,
                }}
              >
                {task.title}
              </span>
              {isUrgent && (
                <span
                  style={{
                    fontSize: 11,
                    fontWeight: 600,
                    backgroundColor: "#FA5151",
                    color: "#fff",
                    borderRadius: 3,
                    padding: "2px 6px",
                    lineHeight: 1.5,
                  }}
                >
                  紧急
                </span>
              )}
            </div>
            {task.content && (
              <div
                style={{
                  fontSize: 13,
                  color: APP.text3,
                  marginTop: 4,
                  marginLeft: 16,
                  lineHeight: 1.5,
                }}
              >
                {task.content}
              </div>
            )}
          </div>

          {/* Source card */}
          <SourceCard task={task} navigate={navigate} />

          {/* Patient */}
          {task.patient_name && (
            <DetailField label="患者">
              <span
                onClick={() =>
                  task.patient_id &&
                  navigate(`/doctor/patients/${task.patient_id}`)
                }
                style={{
                  color: "#07C160",
                  cursor: task.patient_id ? "pointer" : "default",
                  fontSize: 14,
                }}
              >
                {task.patient_name} ›
              </span>
            </DetailField>
          )}

          {/* Due date */}
          {due && (
            <DetailField label="截止" color={due.color}>
              {due.text}
            </DetailField>
          )}

          {/* Action buttons */}
          {!isCompleted && (
            <div
              style={{
                display: "flex",
                gap: 8,
                padding: "12px 16px",
                borderTop: `0.5px solid ${APP.borderLight}`,
              }}
            >
              {task.patient_id && (
                <Button
                  block
                  fill="outline"
                  onClick={() =>
                    navigate(`/doctor/patients/${task.patient_id}`)
                  }
                >
                  查看患者
                </Button>
              )}
              <Button
                block
                color="primary"
                loading={completing}
                onClick={handleComplete}
              >
                标记完成
              </Button>
            </div>
          )}

          {isCompleted && (
            <div
              style={{
                padding: "12px 16px",
                borderTop: `0.5px solid ${APP.borderLight}`,
                fontSize: 14,
                color: "#07C160",
                fontWeight: 500,
              }}
            >
              已完成 {task.completed_at ? task.completed_at.slice(0, 10) : ""}
            </div>
          )}
        </div>

        {/* Notes */}
        <div
          style={{
            backgroundColor: APP.surface,
            borderTop: `0.5px solid ${APP.border}`,
            borderBottom: `0.5px solid ${APP.border}`,
            marginTop: 8,
          }}
        >
          <div
            style={{
              display: "flex",
              gap: 12,
              padding: "10px 16px",
              alignItems: "center",
            }}
          >
            <span
              style={{
                fontSize: 12,
                color: APP.text4,
                flexShrink: 0,
                minWidth: 40,
              }}
            >
              备注
            </span>
            <input
              value={notes}
              onChange={(e) => {
                setNotes(e.target.value);
                setNotesDirty(true);
              }}
              onBlur={handleSaveNotes}
              placeholder="添加备注..."
              style={{
                flex: 1,
                border: "none",
                outline: "none",
                padding: 0,
                fontSize: 14,
                color: APP.text2,
                fontFamily: "inherit",
                backgroundColor: "transparent",
              }}
            />
            {saving && (
              <span style={{ fontSize: 12, color: APP.text4, flexShrink: 0 }}>
                保存中
              </span>
            )}
          </div>
        </div>

        {/* Delete */}
        {!isCompleted && (
          <div style={{ padding: "16px" }}>
            <span
              onClick={confirmDelete}
              style={{ fontSize: 13, color: APP.text4, cursor: "pointer" }}
            >
              删除任务
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
