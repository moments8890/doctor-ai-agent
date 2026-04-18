/**
 * @route /doctor/tasks
 *
 * TaskPage v2 — antd-mobile implementation.
 * Two tabs: 待完成 (pending followups + tasks) / 已完成 (completed).
 * Date-grouped pending items; optimistic complete/uncomplete toggle.
 * No MUI, no framer-motion.
 */
import { useState, useCallback } from "react";
import {
  CapsuleTabs,
  List,
  Button,
  SpinLoading,
  ErrorBlock,
  Tag,
  Popup,
  Input,
  Toast,
} from "antd-mobile";
import {
  CheckCircleOutline,
  AddCircleOutline,
  ClockCircleOutline,
} from "antd-mobile-icons";
import { useQueryClient } from "@tanstack/react-query";
import { usePendingTasks, useCompletedTasks, useDraftSummary } from "../../../lib/doctorQueries";
import { QK } from "../../../lib/queryKeys";
import { useApi } from "../../../api/ApiContext";
import { relativeFuture } from "../../../utils/time";
import { APP, FONT, RADIUS } from "../../theme";

// ── Helpers ────────────────────────────────────────────────────────────────────

function localDateStr(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function normalizeDue(raw) {
  if (!raw) return null;
  // Backend stores naive UTC — append Z so Date parses it as UTC
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
    const dueRaw = item.due_at || item._sortDate || "";
    const normalized = normalizeDue(dueRaw);
    const dueDate = normalized ? new Date(normalized) : null;
    const dueDateStr = dueDate ? localDateStr(dueDate) : "";

    if (!dueDate || dueDateStr < todayStr) {
      buckets.overdue.push(item);
    } else if (dueDateStr === todayStr) {
      buckets.today.push(item);
    } else if (dueDateStr === tomorrowStr) {
      buckets.tomorrow.push(item);
    } else if (dueDateStr <= weekEndStr) {
      buckets.thisWeek.push(item);
    } else {
      buckets.later.push(item);
    }
  });

  const groups = [];
  if (buckets.overdue.length) groups.push({ label: "已逾期", color: "#FA5151", items: buckets.overdue });
  if (buckets.today.length) groups.push({ label: "今天", color: "#07C160", items: buckets.today });
  if (buckets.tomorrow.length) groups.push({ label: "明天", color: APP.text3, items: buckets.tomorrow });
  if (buckets.thisWeek.length) groups.push({ label: "本周", color: APP.text4, items: buckets.thisWeek });
  if (buckets.later.length) groups.push({ label: "之后", color: APP.text4, items: buckets.later });
  return groups;
}

// ── Create task popup ──────────────────────────────────────────────────────────

function CreateTaskPopup({ visible, onClose, doctorId, onCreated }) {
  const api = useApi();
  const queryClient = useQueryClient();
  const [title, setTitle] = useState("");
  const [dueAt, setDueAt] = useState("");
  const [creating, setCreating] = useState(false);

  const handleCreate = async () => {
    if (!title.trim() || creating) return;
    setCreating(true);
    try {
      await api.createTask(doctorId, {
        taskType: "general",
        title: title.trim(),
        dueAt: dueAt || undefined,
      });
      queryClient.invalidateQueries({ queryKey: QK.tasks(doctorId, "pending") });
      onCreated?.();
      setTitle("");
      setDueAt("");
      onClose();
    } catch {
      Toast.show({ content: "创建失败，请重试", position: "bottom" });
    } finally {
      setCreating(false);
    }
  };

  return (
    <Popup
      visible={visible}
      onMaskClick={onClose}
      position="bottom"
      bodyStyle={{ borderRadius: "16px 16px 0 0", padding: "20px 16px 32px" }}
    >
      <div style={{ marginBottom: 16 }}>
        <span style={{ fontSize: 17, fontWeight: 600, color: APP.text1 }}>新建任务</span>
      </div>

      <div style={{ marginBottom: 12 }}>
        <div style={{ fontSize: 13, color: APP.text4, marginBottom: 6 }}>任务标题</div>
        <Input
          value={title}
          onChange={setTitle}
          placeholder="例如：术后复查CT"
          style={{ "--font-size": "15px" }}
        />
        <div style={{ height: 0.5, backgroundColor: APP.border, marginTop: 8 }} />
      </div>

      <div style={{ marginBottom: 24 }}>
        <div style={{ fontSize: 13, color: APP.text4, marginBottom: 6 }}>截止日期（可选）</div>
        <input
          type="date"
          value={dueAt}
          onChange={(e) => setDueAt(e.target.value)}
          style={{
            width: "100%",
            padding: "10px 0",
            border: "none",
            borderBottom: `0.5px solid ${APP.border}`,
            fontSize: 15,
            outline: "none",
            fontFamily: "inherit",
            backgroundColor: "transparent",
            color: APP.text1,
          }}
        />
      </div>

      <div style={{ display: "flex", gap: 8 }}>
        <Button
          block
          color="default"
          size="large"
          onClick={onClose}
          disabled={creating}
        >
          取消
        </Button>
        <Button
          block
          color="primary"
          size="large"
          onClick={handleCreate}
          loading={creating}
          disabled={!title.trim()}
        >
          创建
        </Button>
      </div>
    </Popup>
  );
}

// ── Pending task row ───────────────────────────────────────────────────────────

function PendingTaskItem({ item, isOverdue, onComplete }) {
  const title = item._isFollowup
    ? `${item.patient_name} · ${item.task}`
    : item.title || "任务";
  const subtitle = item._isFollowup ? item.detail : item.content;
  const dueLabel = item.due_at ? (relativeFuture(item.due_at) || "") : "";

  return (
    <List.Item
      prefix={
        <div
          onClick={(e) => { e.stopPropagation(); onComplete(item); }}
          style={{
            width: 24,
            height: 24,
            borderRadius: "50%",
            border: `2px solid ${isOverdue ? "#FA5151" : APP.border}`,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            cursor: "pointer",
            flexShrink: 0,
          }}
        />
      }
      description={
        <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 2 }}>
          {subtitle && (
            <span style={{ fontSize: 12, color: APP.text4, flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {subtitle}
            </span>
          )}
          {dueLabel && (
            <Tag
              color={isOverdue ? "danger" : "default"}
              style={{ fontSize: 11, flexShrink: 0 }}
            >
              <ClockCircleOutline style={{ fontSize: 11, marginRight: 2 }} />
              {dueLabel}
            </Tag>
          )}
        </div>
      }
      style={{ "--padding-left": "12px" }}
    >
      <span style={{ fontSize: 15, color: isOverdue ? "#FA5151" : APP.text1, fontWeight: 500 }}>
        {title}
      </span>
    </List.Item>
  );
}

// ── Completed task row ─────────────────────────────────────────────────────────

function CompletedTaskItem({ item, onUncomplete }) {
  const label = item.patient_name
    ? `${item.patient_name} · ${item.task || item.title || ""}`
    : item.task || item.title || "任务";

  return (
    <List.Item
      prefix={
        <CheckCircleOutline
          onClick={(e) => { e.stopPropagation(); onUncomplete(item); }}
          style={{ fontSize: 22, color: "#07C160", cursor: "pointer", flexShrink: 0 }}
        />
      }
      extra={
        <span style={{ fontSize: 12, color: APP.text4 }}>{item.time}</span>
      }
      style={{ "--padding-left": "12px" }}
    >
      <span style={{ fontSize: 15, color: APP.text4, textDecoration: "line-through" }}>
        {label}
      </span>
    </List.Item>
  );
}

// ── Main page ──────────────────────────────────────────────────────────────────

export default function TaskPage({ doctorId }) {
  const api = useApi();
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState("pending");
  const [createOpen, setCreateOpen] = useState(false);

  // Optimistic overrides
  const [pendingOverride, setPendingOverride] = useState(null);
  const [completedOverride, setCompletedOverride] = useState(null);

  const { data: pendingTasksData, isLoading: ptLoading } = usePendingTasks();
  const { data: completedTasksData, isLoading: ctLoading } = useCompletedTasks();
  const { data: summaryData, isLoading: sumLoading } = useDraftSummary();

  const loading = ptLoading || ctLoading || sumLoading;

  // Derive raw lists
  const rawPendingTasks = Array.isArray(pendingTasksData)
    ? pendingTasksData
    : pendingTasksData?.items || [];
  const rawCompletedTasks = Array.isArray(completedTasksData)
    ? completedTasksData
    : completedTasksData?.items || [];
  const upcomingFollowups = summaryData?.upcoming_followups || [];
  const recentlySent = summaryData?.recently_sent || summaryData?.sent || [];

  // Apply optimistic overrides
  const pendingTasks = pendingOverride !== null ? pendingOverride : rawPendingTasks;
  const completedItems = completedOverride !== null
    ? completedOverride
    : [...recentlySent, ...rawCompletedTasks];

  // Merge followups + tasks into pending list
  const allPendingItems = [
    ...upcomingFollowups.map((f) => ({
      ...f,
      _isFollowup: true,
      _sortDate: f.due_at || "",
    })),
    ...pendingTasks
      .filter((t) => !t.title?.startsWith("审阅"))
      .map((t) => ({
        ...t,
        _isFollowup: false,
        _sortDate: t.due_at || t.due || "",
      })),
  ].sort((a, b) => (a._sortDate || "").localeCompare(b._sortDate || ""));

  const dateGroups = groupByDate(allPendingItems);

  const handleComplete = useCallback(
    async (item) => {
      // Optimistic: remove from pending, add to completed
      setPendingOverride((prev) => {
        const cur = prev !== null ? prev : rawPendingTasks;
        return cur.filter((t) => t.id !== item.id);
      });
      setCompletedOverride((prev) => {
        const cur = prev !== null ? prev : [...recentlySent, ...rawCompletedTasks];
        return [
          {
            id: item.id,
            patient_name: item.patient_name,
            task: item.task || item.title || "",
            time: "刚刚",
          },
          ...cur,
        ];
      });

      try {
        const patchTask = api.patchTask || (() => Promise.resolve());
        await patchTask(item.id, doctorId, "completed");
        queryClient.invalidateQueries({ queryKey: QK.tasks(doctorId, "pending") });
        queryClient.invalidateQueries({ queryKey: QK.tasks(doctorId, "completed") });
      } catch {
        // revert
        setPendingOverride(null);
        setCompletedOverride(null);
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [api, doctorId, rawPendingTasks, rawCompletedTasks, recentlySent]
  );

  const handleUncomplete = useCallback(
    async (item) => {
      // Optimistic: remove from completed, add back to pending
      setCompletedOverride((prev) => {
        const cur = prev !== null ? prev : [...recentlySent, ...rawCompletedTasks];
        return cur.filter((s) => s.id !== item.id);
      });
      setPendingOverride((prev) => {
        const cur = prev !== null ? prev : rawPendingTasks;
        return [
          {
            id: item.id,
            title: item.task || item.title || "任务",
            content: "",
            patient_name: item.patient_name,
            task_type: "general",
            due_at: null,
          },
          ...cur,
        ];
      });

      try {
        const patchTask = api.patchTask || (() => Promise.resolve());
        await patchTask(item.id, doctorId, "pending");
        queryClient.invalidateQueries({ queryKey: QK.tasks(doctorId, "pending") });
        queryClient.invalidateQueries({ queryKey: QK.tasks(doctorId, "completed") });
      } catch {
        // revert
        setPendingOverride(null);
        setCompletedOverride(null);
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [api, doctorId, rawPendingTasks, rawCompletedTasks, recentlySent]
  );

  const handleCreated = useCallback(() => {
    setPendingOverride(null);
    setCompletedOverride(null);
  }, []);

  // ── Render ─────────────────────────────────────────────────────────

  if (loading) {
    return (
      <div
        style={{
          height: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <SpinLoading color="primary" style={{ "--size": "36px" }} />
      </div>
    );
  }

  return (
    <div
      style={{
        height: "100%",
        display: "flex",
        flexDirection: "column",
        backgroundColor: APP.surfaceAlt,
        overflow: "hidden",
      }}
    >
      {/* Filter tabs */}
      <div
        style={{
          backgroundColor: APP.surface,
          borderBottom: `0.5px solid ${APP.border}`,
          padding: "8px 16px 0",
          flexShrink: 0,
        }}
      >
        <CapsuleTabs
          activeKey={activeTab}
          onChange={setActiveTab}
          style={{ "--adm-color-primary": "#07C160" }}
        >
          <CapsuleTabs.Tab
            title={
              <span>
                待完成
                {allPendingItems.length > 0 && (
                  <span
                    style={{
                      marginLeft: 4,
                      fontSize: 11,
                      color: activeTab === "pending" ? "#07C160" : APP.text4,
                    }}
                  >
                    {allPendingItems.length}
                  </span>
                )}
              </span>
            }
            key="pending"
          />
          <CapsuleTabs.Tab
            title={
              <span>
                已完成
                {completedItems.length > 0 && (
                  <span
                    style={{
                      marginLeft: 4,
                      fontSize: 11,
                      color: activeTab === "completed" ? "#07C160" : APP.text4,
                    }}
                  >
                    {completedItems.length}
                  </span>
                )}
              </span>
            }
            key="completed"
          />
        </CapsuleTabs>
      </div>

      {/* Scrollable content */}
      <div style={{ flex: 1, overflowY: "auto", WebkitOverflowScrolling: "touch" }}>
        {activeTab === "pending" && (
          <>
            {/* New task button */}
            <div style={{ padding: "12px 16px 0" }}>
              <Button
                block
                color="default"
                size="middle"
                onClick={() => setCreateOpen(true)}
                style={{ borderRadius: 8, borderStyle: "dashed" }}
              >
                <AddCircleOutline style={{ marginRight: 6, verticalAlign: "middle" }} />
                新建任务
              </Button>
            </div>

            {/* Date-grouped task list */}
            {dateGroups.length > 0 ? (
              dateGroups.map((group) => (
                <div key={group.label} style={{ marginTop: 12 }}>
                  <div
                    style={{
                      padding: "4px 16px 6px",
                      fontSize: 12,
                      fontWeight: 600,
                      color: group.color,
                    }}
                  >
                    {group.label}
                  </div>
                  <List>
                    {group.items.map((item) => (
                      <PendingTaskItem
                        key={`${item._isFollowup ? "f" : "t"}-${item.id}`}
                        item={item}
                        isOverdue={group.label === "已逾期"}
                        onComplete={handleComplete}
                      />
                    ))}
                  </List>
                </div>
              ))
            ) : (
              <ErrorBlock
                status="empty"
                title="暂无待处理任务"
                description="患者随访和待办提醒会出现在这里"
                style={{ marginTop: 48 }}
              />
            )}
          </>
        )}

        {activeTab === "completed" && (
          <>
            {completedItems.length > 0 ? (
              <div style={{ marginTop: 12 }}>
                <List>
                  {completedItems.map((item) => (
                    <CompletedTaskItem
                      key={item.id}
                      item={item}
                      onUncomplete={handleUncomplete}
                    />
                  ))}
                </List>
              </div>
            ) : (
              <ErrorBlock
                status="empty"
                title="暂无已完成任务"
                description="完成的任务和已发送消息会出现在这里"
                style={{ marginTop: 48 }}
              />
            )}
          </>
        )}

        {/* Bottom padding */}
        <div style={{ height: 24 }} />
      </div>

      {/* Create task popup */}
      <CreateTaskPopup
        visible={createOpen}
        onClose={() => setCreateOpen(false)}
        doctorId={doctorId}
        onCreated={handleCreated}
      />
    </div>
  );
}
