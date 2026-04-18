/**
 * TasksTab — patient task list (v2, antd-mobile).
 *
 * Business logic ported from src/pages/patient/TasksTab.jsx.
 * Splits tasks into pending / completed with filter pills.
 * Supports mark-complete and undo.
 */

import { useCallback, useEffect, useState } from "react";
import { Button, Checkbox, ErrorBlock, List, SpinLoading, Tag } from "antd-mobile";
import { CheckCircleOutline, ClockCircleOutline } from "antd-mobile-icons";
import { usePatientApi } from "../../../api/PatientApiContext";
import { APP, FONT, RADIUS } from "../../theme";

// ---------------------------------------------------------------------------
// Filter pill row (shared pattern with RecordsTab)
// ---------------------------------------------------------------------------

function FilterPills({ items, active, onChange }) {
  return (
    <div
      style={{
        display: "flex",
        gap: 8,
        padding: "8px 12px",
        overflowX: "auto",
        background: APP.surface,
        borderBottom: `0.5px solid ${APP.border}`,
        flexShrink: 0,
      }}
    >
      {items.map((item) => (
        <div
          key={item.key}
          onClick={() => onChange(item.key)}
          style={{
            padding: "4px 12px",
            borderRadius: 100,
            fontSize: FONT.sm,
            whiteSpace: "nowrap",
            cursor: "pointer",
            background: active === item.key ? APP.primary : APP.borderLight,
            color: active === item.key ? APP.white : APP.text3,
            fontWeight: active === item.key ? 600 : 400,
          }}
        >
          {item.label}
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Section header
// ---------------------------------------------------------------------------

function SectionHeader({ children }) {
  return (
    <div
      style={{
        padding: "8px 16px 4px",
        fontSize: 12,
        color: APP.text4,
        fontWeight: 600,
        background: APP.surfaceAlt,
      }}
    >
      {children}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Task item
// ---------------------------------------------------------------------------

function TaskItem({ task, onComplete, onUndo }) {
  const isDone = task.status === "completed";

  function formatDate(iso) {
    if (!iso) return "";
    try {
      return new Date(iso).toLocaleDateString("zh-CN", {
        month: "2-digit",
        day: "2-digit",
      });
    } catch {
      return "";
    }
  }

  return (
    <List.Item
      prefix={
        isDone ? (
          <CheckCircleOutline style={{ fontSize: 22, color: APP.primary }} />
        ) : (
          <ClockCircleOutline style={{ fontSize: 22, color: APP.warning }} />
        )
      }
      title={
        <span
          style={{
            fontSize: FONT.md,
            fontWeight: 500,
            color: isDone ? APP.text4 : APP.text1,
            textDecoration: isDone ? "line-through" : "none",
          }}
        >
          {task.title || task.content || "任务"}
        </span>
      }
      description={
        task.due_date ? (
          <span style={{ fontSize: FONT.sm, color: APP.text4 }}>
            截止日期：{formatDate(task.due_date)}
          </span>
        ) : undefined
      }
      extra={
        <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 6 }}>
          <Tag
            color={isDone ? "success" : "warning"}
            fill="outline"
            style={{ fontSize: 11 }}
          >
            {isDone ? "已完成" : "待完成"}
          </Tag>
          {!isDone && onComplete && (
            <Button
              size="mini"
              color="primary"
              fill="outline"
              onClick={(e) => {
                e.stopPropagation();
                onComplete(task.id);
              }}
            >
              完成
            </Button>
          )}
          {isDone && onUndo && (
            <Button
              size="mini"
              color="default"
              fill="outline"
              onClick={(e) => {
                e.stopPropagation();
                onUndo(task.id);
              }}
            >
              撤销
            </Button>
          )}
        </div>
      }
    />
  );
}

// ---------------------------------------------------------------------------
// TasksTab
// ---------------------------------------------------------------------------

const FILTERS = [
  { key: "all", label: "全部" },
  { key: "pending", label: "待完成" },
  { key: "done", label: "已完成" },
];

export default function TasksTab({ token }) {
  const { getPatientTasks, completePatientTask, uncompletePatientTask } = usePatientApi();
  const [tasks, setTasks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [filter, setFilter] = useState("all");

  const loadTasks = useCallback(() => {
    setLoading(true);
    setError(false);
    getPatientTasks(token)
      .then((data) => setTasks(Array.isArray(data) ? data : []))
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, [token, getPatientTasks]);

  useEffect(() => {
    loadTasks();
  }, [loadTasks]);

  async function handleComplete(taskId) {
    try {
      await completePatientTask(token, taskId);
      setTasks((prev) =>
        prev.map((t) => (t.id === taskId ? { ...t, status: "completed" } : t))
      );
    } catch {}
  }

  async function handleUndo(taskId) {
    try {
      await uncompletePatientTask(token, taskId);
      setTasks((prev) =>
        prev.map((t) =>
          t.id === taskId ? { ...t, status: "pending", completed_at: null } : t
        )
      );
    } catch {}
  }

  if (loading) {
    return (
      <div
        style={{
          flex: 1,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          padding: 32,
        }}
      >
        <SpinLoading color="primary" />
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ padding: 16 }}>
        <ErrorBlock status="default" title="加载失败" description="无法获取任务列表">
          <Button color="primary" size="small" onClick={loadTasks}>
            重试
          </Button>
        </ErrorBlock>
      </div>
    );
  }

  const pending = tasks.filter((t) => t.status === "pending");
  const completed = tasks.filter((t) => t.status === "completed");

  const filtered =
    filter === "all"
      ? tasks
      : filter === "pending"
      ? pending
      : completed;

  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
      <FilterPills items={FILTERS} active={filter} onChange={setFilter} />

      <div style={{ flex: 1, overflowY: "auto" }}>
        {filtered.length === 0 ? (
          <ErrorBlock
            status="empty"
            title="暂无任务"
            description="医生安排的复查、用药提醒将显示在这里"
          />
        ) : filter === "all" ? (
          <>
            {pending.length > 0 && (
              <>
                <SectionHeader>待完成 · {pending.length}</SectionHeader>
                <List>
                  {pending.map((t) => (
                    <TaskItem key={t.id} task={t} onComplete={handleComplete} />
                  ))}
                </List>
              </>
            )}
            {completed.length > 0 && (
              <>
                <SectionHeader>已完成 · {completed.length}</SectionHeader>
                <List>
                  {completed.map((t) => (
                    <TaskItem key={t.id} task={t} onUndo={handleUndo} />
                  ))}
                </List>
              </>
            )}
          </>
        ) : (
          <List>
            {filtered.map((t) => (
              <TaskItem
                key={t.id}
                task={t}
                onComplete={filter === "pending" ? handleComplete : undefined}
                onUndo={filter === "done" ? handleUndo : undefined}
              />
            ))}
          </List>
        )}
      </div>
    </div>
  );
}
