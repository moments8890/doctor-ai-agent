/**
 * TasksTab — patient task list (v2, antd-mobile).
 *
 * Patient parity (Task 4.4): card pattern + visible tap-target prefix
 * (NOT SwipeAction — older audience needs a discoverable affordance).
 * PullToRefresh wraps the rendered list. Optimistic-override behavior
 * from Task 3.3 is preserved (dataUpdatedAt clears overrides atomically
 * with the canonical refetch).
 */

import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { JumboTabs, ErrorBlock, Button, Ellipsis, PullToRefresh } from "antd-mobile";
import CheckOutlinedIcon from "@mui/icons-material/CheckOutlined";
import {
  usePatientTasks,
  useCompletePatientTask,
  useUncompletePatientTask,
} from "../../../lib/patientQueries";
import { relativeFuture } from "../../../utils/time";
import { APP, FONT, ICON, RADIUS } from "../../theme";
import { pageContainer, scrollable } from "../../layouts";
import {
  LoadingCenter,
  EmptyState,
  ListSectionDivider as SectionHeader,
  Card,
} from "../../components";

// ---------------------------------------------------------------------------
// Date helpers
// ---------------------------------------------------------------------------

function localDateStr(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function normalizeDue(raw) {
  if (!raw) return null;
  if (!raw.includes("Z") && !raw.includes("+")) return raw + "Z";
  return raw;
}

function groupByDate(items) {
  const now = new Date();
  const todayStr = localDateStr(now);
  const tomorrow = new Date(now);
  tomorrow.setDate(tomorrow.getDate() + 1);
  const tomorrowStr = localDateStr(tomorrow);
  const weekEnd = new Date(now);
  weekEnd.setDate(weekEnd.getDate() + (7 - now.getDay()));
  const weekEndStr = localDateStr(weekEnd);

  const buckets = { overdue: [], today: [], tomorrow: [], thisWeek: [], later: [] };
  items.forEach((item) => {
    const dueRaw = item.due_at || "";
    const normalized = normalizeDue(dueRaw);
    const dueDate = normalized ? new Date(normalized) : null;
    const dueDateStr = dueDate ? localDateStr(dueDate) : "";
    if (!dueDate || dueDateStr < todayStr) buckets.overdue.push(item);
    else if (dueDateStr === todayStr) buckets.today.push(item);
    else if (dueDateStr === tomorrowStr) buckets.tomorrow.push(item);
    else if (dueDateStr <= weekEndStr) buckets.thisWeek.push(item);
    else buckets.later.push(item);
  });

  const groups = [];
  if (buckets.overdue.length) groups.push({ label: "已逾期", color: APP.danger, items: buckets.overdue });
  if (buckets.today.length) groups.push({ label: "今天", color: APP.primary, items: buckets.today });
  if (buckets.tomorrow.length) groups.push({ label: "明天", color: APP.text3, items: buckets.tomorrow });
  if (buckets.thisWeek.length) groups.push({ label: "本周", color: APP.text4, items: buckets.thisWeek });
  if (buckets.later.length) groups.push({ label: "之后", color: APP.text4, items: buckets.later });
  return groups;
}

function formatDueDate(dueAt) {
  // Prefer relative phrasing for near-future deadlines; fall back to MM-DD.
  const rel = relativeFuture(dueAt);
  if (rel) return rel;
  const normalized = normalizeDue(dueAt);
  if (!normalized) return "";
  const d = new Date(normalized);
  if (isNaN(d.getTime())) return "";
  return d.toLocaleDateString("zh-CN", { month: "2-digit", day: "2-digit" });
}

// ---------------------------------------------------------------------------
// Row component — visible tap-target prefix + card body
// ---------------------------------------------------------------------------

function TabTitleWithCount({ label, count }) {
  return count > 0 ? <span>{label} ({count})</span> : <span>{label}</span>;
}

function TaskCard({ item, isOverdue, onToggle, onTap }) {
  const completed = item.status === "completed";
  const title = item.title || item.content || "任务";
  const dueLabel = item.due_at ? `截止: ${formatDueDate(item.due_at)}` : "";

  return (
    <Card style={{ margin: "8px 12px" }}>
      <div
        data-testid="patient-task-row"
        onClick={onTap}
        style={{
          display: "flex",
          alignItems: "center",
          gap: 12,
          padding: "12px 14px",
          cursor: "pointer",
        }}
      >
        {/* Visible tap-target prefix — 36px tinted circle */}
        <div
          role="button"
          aria-label={completed ? "撤销完成" : "标记完成"}
          onClick={(e) => {
            e.stopPropagation();
            onToggle(item);
          }}
          style={{
            width: 36,
            height: 36,
            borderRadius: RADIUS.md,
            background: completed ? APP.primaryLight : APP.surfaceAlt,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            flexShrink: 0,
            cursor: "pointer",
          }}
        >
          {completed ? (
            <CheckOutlinedIcon sx={{ fontSize: ICON.sm, color: APP.primary }} />
          ) : (
            <div
              style={{
                width: 18,
                height: 18,
                borderRadius: "50%",
                border: `1.5px solid ${APP.border}`,
              }}
            />
          )}
        </div>

        {/* Body */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div
            style={{
              fontSize: FONT.base,
              fontWeight: 500,
              color: completed ? APP.text4 : (isOverdue ? APP.danger : APP.text1),
              textDecoration: completed ? "line-through" : "none",
            }}
          >
            <Ellipsis content={title} rows={2} direction="end" />
          </div>
          {dueLabel && (
            <div style={{ fontSize: FONT.sm, color: APP.text4, marginTop: 4 }}>
              {dueLabel}
            </div>
          )}
        </div>
      </div>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function TasksTab({ token: _token }) {
  const navigate = useNavigate();
  const { data: tasks = [], isLoading, isError, refetch, dataUpdatedAt } = usePatientTasks();
  const completeTask = useCompletePatientTask();
  const uncompleteTask = useUncompletePatientTask();
  const [activeTab, setActiveTab] = useState("pending");
  const [pendingOverride, setPendingOverride] = useState(null);
  const [completedOverride, setCompletedOverride] = useState(null);

  useEffect(() => {
    // Canonical list just refreshed — drop overrides so we render fresh data
    // atomically with the new tasks (avoids flicker between override clear
    // and refetch resolution).
    setPendingOverride(null);
    setCompletedOverride(null);
  }, [dataUpdatedAt]);

  // Derived lists with optimistic overrides
  const rawPending = tasks.filter((t) => t.status !== "completed");
  const rawCompleted = tasks.filter((t) => t.status === "completed");
  const pending = pendingOverride !== null ? pendingOverride : rawPending;
  const completed = completedOverride !== null ? completedOverride : rawCompleted;

  const dateGroups = groupByDate(pending);

  const handleTap = (item) => navigate(`/patient/tasks/${item.id}`);

  const handleComplete = useCallback((item) => {
    setPendingOverride((prev) => {
      const cur = prev !== null ? prev : rawPending;
      return cur.filter((t) => t.id !== item.id);
    });
    setCompletedOverride((prev) => {
      const cur = prev !== null ? prev : rawCompleted;
      return [{ ...item, status: "completed", completed_at: new Date().toISOString() }, ...cur];
    });
    completeTask.mutate(item.id, {
      onError: () => {
        setPendingOverride(null);
        setCompletedOverride(null);
      },
    });
  }, [completeTask, rawPending, rawCompleted]);

  const handleUncomplete = useCallback((item) => {
    setCompletedOverride((prev) => {
      const cur = prev !== null ? prev : rawCompleted;
      return cur.filter((t) => t.id !== item.id);
    });
    setPendingOverride((prev) => {
      const cur = prev !== null ? prev : rawPending;
      return [{ ...item, status: "pending", completed_at: null }, ...cur];
    });
    uncompleteTask.mutate(item.id, {
      onError: () => {
        setPendingOverride(null);
        setCompletedOverride(null);
      },
    });
  }, [uncompleteTask, rawPending, rawCompleted]);

  const handleToggle = useCallback((item) => {
    if (item.status === "completed") handleUncomplete(item);
    else handleComplete(item);
  }, [handleComplete, handleUncomplete]);

  if (isLoading) return <LoadingCenter />;
  if (isError) return (
    <div style={{ padding: 16 }}>
      <ErrorBlock status="default" title="加载失败" description="无法获取任务列表">
        <Button color="primary" size="small" onClick={() => refetch()}>重试</Button>
      </ErrorBlock>
    </div>
  );

  return (
    <div style={pageContainer}>
      <div style={{ backgroundColor: APP.surface, borderBottom: `0.5px solid ${APP.border}`, flexShrink: 0 }}>
        <JumboTabs activeKey={activeTab} onChange={setActiveTab}>
          <JumboTabs.Tab title={<TabTitleWithCount label="待完成" count={pending.length} />} key="pending" />
          <JumboTabs.Tab title={<TabTitleWithCount label="已完成" count={completed.length} />} key="completed" />
        </JumboTabs>
      </div>

      <div style={scrollable}>
        <PullToRefresh onRefresh={async () => { await refetch(); }}>
          {activeTab === "pending" && (
            dateGroups.length > 0 ? dateGroups.map((group) => (
              <div key={group.label} style={{ marginTop: 12 }}>
                <SectionHeader color={group.color}>{group.label}</SectionHeader>
                {group.items.map((item) => (
                  <TaskCard
                    key={item.id}
                    item={item}
                    isOverdue={group.label === "已逾期"}
                    onToggle={handleToggle}
                    onTap={() => handleTap(item)}
                  />
                ))}
              </div>
            )) : (
              <EmptyState title="暂无待处理任务" description="医生安排的复查、用药提醒会显示在这里" />
            )
          )}
          {activeTab === "completed" && (
            completed.length > 0 ? (
              <div style={{ marginTop: 12 }}>
                {completed.map((item) => (
                  <TaskCard
                    key={item.id}
                    item={item}
                    isOverdue={false}
                    onToggle={handleToggle}
                    onTap={() => handleTap(item)}
                  />
                ))}
              </div>
            ) : (
              <EmptyState title="暂无已完成任务" description="完成的任务会出现在这里" />
            )
          )}
          <div style={{ height: 24 }} />
        </PullToRefresh>
      </div>
    </div>
  );
}
