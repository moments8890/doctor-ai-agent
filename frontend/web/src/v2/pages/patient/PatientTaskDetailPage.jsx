/**
 * @route /patient/tasks/:id
 * Patient task detail with complete/undo. Uses GET /api/patient/tasks/:id endpoint
 * (Phase 0). Fields: task_type, status (pending|completed|cancelled),
 * source_record_id (derived from task.record_id, NOT task.source_id), completed_at.
 */
import { Button, Dialog, Ellipsis, NavBar, Tag } from "antd-mobile";
import { LeftOutline } from "antd-mobile-icons";
import { useNavigate } from "react-router-dom";
import { APP, FONT } from "../../theme";
import { pageContainer, navBarStyle, scrollable } from "../../layouts";
import { Card, LoadingCenter, EmptyState } from "../../components";
import {
  usePatientTaskDetail,
  useCompletePatientTask,
  useUncompletePatientTask,
} from "../../../lib/patientQueries";

const STATUS_LABEL = {
  pending:   { text: "待完成", color: "warning" },
  completed: { text: "已完成", color: "success" },
  cancelled: { text: "已取消", color: "default" },
};

function fmt(iso) {
  if (!iso) return "";
  return new Date(iso).toLocaleString("zh-CN", { dateStyle: "medium", timeStyle: "short" });
}

export default function PatientTaskDetailPage({ taskId }) {
  const navigate = useNavigate();
  const { data: task, isLoading, isError } = usePatientTaskDetail(taskId);
  const completeTask   = useCompletePatientTask();
  const uncompleteTask = useUncompletePatientTask();

  function handleComplete() {
    completeTask.mutate(Number(taskId));
  }
  function handleUncomplete() {
    Dialog.confirm({
      title: "撤销完成",
      content: "确定要撤销该任务的完成状态吗？",
      cancelText: "取消",
      confirmText: "撤销",
      onConfirm: () => uncompleteTask.mutate(Number(taskId)),
    });
  }

  const isOverdue = task?.due_at
    && task.status === "pending"
    && new Date(task.due_at).getTime() < Date.now();

  return (
    <div style={pageContainer}>
      <NavBar backArrow={<LeftOutline />} onBack={() => navigate(-1)} style={navBarStyle}>
        任务详情
      </NavBar>
      <div style={scrollable}>
        {isLoading && <LoadingCenter />}
        {isError && (
          <EmptyState
            title="任务不存在或已删除"
            description="请回到任务列表"
            action="返回列表"
            onAction={() => navigate("/patient/tasks")}
          />
        )}
        {task && (
          <>
            {/* Header */}
            <Card style={{ marginTop: 8 }}>
              <div style={{ padding: "12px 14px" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
                  <Tag color={STATUS_LABEL[task.status]?.color || "default"}>
                    {STATUS_LABEL[task.status]?.text || task.status}
                  </Tag>
                </div>
                <div style={{ fontSize: FONT.lg, fontWeight: 700, color: APP.text1 }}>
                  {task.title}
                </div>
              </div>
            </Card>

            {/* 任务详情 */}
            {task.content && (
              <Card style={{ marginTop: 8 }}>
                <div style={{ padding: "12px 14px" }}>
                  <div style={{ fontSize: FONT.sm, fontWeight: 600, color: APP.text4, marginBottom: 6 }}>
                    任务详情
                  </div>
                  <Ellipsis
                    content={task.content}
                    rows={10}
                    expandText="展开"
                    collapseText="收起"
                    style={{ fontSize: FONT.base, color: APP.text1, lineHeight: 1.6 }}
                  />
                </div>
              </Card>
            )}

            {/* 时间 */}
            <Card style={{ marginTop: 8 }}>
              <div style={{ padding: "12px 14px" }}>
                <div style={{ fontSize: FONT.sm, fontWeight: 600, color: APP.text4, marginBottom: 6 }}>
                  时间
                </div>
                {task.due_at && (
                  <div style={{ fontSize: FONT.base, color: isOverdue ? APP.danger : APP.text1, marginBottom: 4 }}>
                    截止: {fmt(task.due_at)}
                  </div>
                )}
                <div style={{ fontSize: FONT.base, color: APP.text1, marginBottom: 4 }}>
                  创建: {fmt(task.created_at)}
                </div>
                {task.status === "completed" && task.completed_at && (
                  <div style={{ fontSize: FONT.base, color: APP.text1 }}>
                    完成: {fmt(task.completed_at)}
                  </div>
                )}
              </div>
            </Card>

            {/* 来源 — only when source_record_id is set */}
            {task.source_record_id && (
              <Card style={{ marginTop: 8 }}>
                <div
                  onClick={() => navigate(`/patient/records/${task.source_record_id}`)}
                  style={{ padding: "12px 14px", cursor: "pointer" }}
                >
                  <div style={{ fontSize: FONT.sm, fontWeight: 600, color: APP.text4, marginBottom: 4 }}>
                    来源
                  </div>
                  <div style={{ fontSize: FONT.base, color: APP.primary }}>
                    {task.task_type === "follow_up" ? "随访任务 · " : ""}关联病历 #{task.source_record_id}
                  </div>
                </div>
              </Card>
            )}

            {/* Action button */}
            <div style={{ margin: "24px 12px" }}>
              {task.status === "pending" && (
                <Button block color="primary" size="large" onClick={handleComplete}
                  loading={completeTask.isPending}>
                  标记完成
                </Button>
              )}
              {task.status === "completed" && (
                <Button block color="default" size="large" onClick={handleUncomplete}
                  loading={uncompleteTask.isPending}>
                  撤销完成
                </Button>
              )}
              {task.status === "cancelled" && (
                <div style={{ textAlign: "center", color: APP.text4, fontSize: FONT.sm }}>
                  此任务已取消
                </div>
              )}
            </div>

            <div style={{ height: 32 }} />
          </>
        )}
      </div>
    </div>
  );
}
