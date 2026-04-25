/**
 * TasksTab — patient task list (v2, antd-mobile).
 *
 * Matches doctor TaskPage UI: JumboTabs, date-grouped pending rows with
 * circle-checkbox, completed rows with CheckCircleOutline, optimistic updates.
 * Patient-specific: no create-task, no patient_name prefix, no followup merging.
 */

import { useCallback, useState } from "react";
import { useNavigate } from "react-router-dom";
import { JumboTabs, List, Tag, ErrorBlock, Button, Ellipsis } from "antd-mobile";
import { CheckCircleOutline, ClockCircleOutline } from "antd-mobile-icons";
import {
  usePatientTasks,
  useCompletePatientTask,
  useUncompletePatientTask,
} from "../../../lib/patientQueries";
import { relativeFuture } from "../../../utils/time";
import { APP, FONT } from "../../theme";
import { pageContainer, scrollable } from "../../layouts";
import { LoadingCenter, EmptyState, ListSectionDivider as SectionHeader } from "../../components";

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

// ---------------------------------------------------------------------------
// Row components
// ---------------------------------------------------------------------------

function TabTitleWithCount({ label, count }) {
  return count > 0 ? <span>{label} ({count})</span> : <span>{label}</span>;
}

function PendingRow({ item, isOverdue, onComplete, onTap }) {
  const title = item.title || "任务";
  const subtitle = item.content && item.content.trim() !== title.trim() ? item.content : null;
  const dueLabel = item.due_at ? (relativeFuture(item.due_at) || "") : "";
  return (
    <List.Item
      onClick={onTap}
      prefix={
        <div
          onClick={(e) => { e.stopPropagation(); onComplete(item); }}
          style={{
            width: 24, height: 24, borderRadius: "50%",
            border: `2px solid ${isOverdue ? APP.danger : APP.border}`,
            display: "flex", alignItems: "center", justifyContent: "center",
            cursor: "pointer", flexShrink: 0,
          }}
        />
      }
      description={
        <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 2 }}>
          {subtitle && (
            <div style={{ fontSize: FONT.sm, color: APP.text4, flex: 1, minWidth: 0 }}>
              <Ellipsis direction="end" content={subtitle} rows={1} />
            </div>
          )}
          {dueLabel && (
            <Tag color={isOverdue ? "danger" : "default"} style={{ fontSize: FONT.xs, flexShrink: 0 }}>
              <ClockCircleOutline style={{ fontSize: FONT.xs, marginRight: 2 }} />
              {dueLabel}
            </Tag>
          )}
        </div>
      }
      style={{ "--padding-left": "12px" }}
    >
      <span style={{ fontSize: FONT.md, color: isOverdue ? APP.danger : APP.text1, fontWeight: 500 }}>
        {title}
      </span>
    </List.Item>
  );
}

function CompletedRow({ item, onUncomplete, onTap }) {
  const title = item.title || item.content || "任务";
  const timeStr = item.completed_at ? new Date(item.completed_at).toLocaleDateString("zh-CN", { month: "2-digit", day: "2-digit" }) : "";
  return (
    <List.Item
      onClick={onTap}
      prefix={
        <CheckCircleOutline
          onClick={(e) => { e.stopPropagation(); onUncomplete(item); }}
          style={{ fontSize: FONT.xl, color: APP.primary, cursor: "pointer", flexShrink: 0 }}
        />
      }
      extra={<span style={{ fontSize: FONT.sm, color: APP.text4 }}>{timeStr}</span>}
      style={{ "--padding-left": "12px" }}
    >
      <span style={{ fontSize: FONT.md, color: APP.text4, textDecoration: "line-through" }}>
        {title}
      </span>
    </List.Item>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function TasksTab({ token: _token }) {
  const navigate = useNavigate();
  const { data: tasks = [], isLoading, isError, refetch } = usePatientTasks();
  const completeTask = useCompletePatientTask();
  const uncompleteTask = useUncompletePatientTask();
  const [activeTab, setActiveTab] = useState("pending");
  const [pendingOverride, setPendingOverride] = useState(null);
  const [completedOverride, setCompletedOverride] = useState(null);

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
      onSuccess: () => {
        // Drop overrides so the refetched canonical list takes over.
        setPendingOverride(null);
        setCompletedOverride(null);
      },
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
      onSuccess: () => {
        // Drop overrides so the refetched canonical list takes over.
        setPendingOverride(null);
        setCompletedOverride(null);
      },
      onError: () => {
        setPendingOverride(null);
        setCompletedOverride(null);
      },
    });
  }, [uncompleteTask, rawPending, rawCompleted]);

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
        {activeTab === "pending" && (
          dateGroups.length > 0 ? dateGroups.map((group) => (
            <div key={group.label} style={{ marginTop: 12 }}>
              <SectionHeader color={group.color}>{group.label}</SectionHeader>
              <List>
                {group.items.map((item) => (
                  <PendingRow
                    key={item.id}
                    item={item}
                    isOverdue={group.label === "已逾期"}
                    onComplete={handleComplete}
                    onTap={() => handleTap(item)}
                  />
                ))}
              </List>
            </div>
          )) : (
            <EmptyState title="暂无待处理任务" description="医生安排的复查、用药提醒会显示在这里" />
          )
        )}
        {activeTab === "completed" && (
          completed.length > 0 ? (
            <div style={{ marginTop: 12 }}>
              <List>
                {completed.map((item) => (
                  <CompletedRow
                    key={item.id}
                    item={item}
                    onUncomplete={handleUncomplete}
                    onTap={() => handleTap(item)}
                  />
                ))}
              </List>
            </div>
          ) : (
            <EmptyState title="暂无已完成任务" description="完成的任务会出现在这里" />
          )
        )}
        <div style={{ height: 24 }} />
      </div>
    </div>
  );
}
