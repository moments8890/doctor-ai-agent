/**
 * @route /doctor/tasks
 *
 * TaskPage -- "任务" tab. Shows pending replies, followups, tasks,
 * and completed items. Three filter tabs:
 *   1. 患者消息 · 待回复  (pending messages with AI drafts)
 *   2. 即将到期的随访     (upcoming scheduled follow-ups)
 *   3. 待办提醒           (doctor-created tasks/reminders)
 *   4. 最近已发送         (recently sent messages)
 */
import { useEffect, useState, useCallback, useRef } from "react";
import { Box, CircularProgress, Snackbar, Typography, useMediaQuery, useTheme } from "@mui/material";
import MailOutlineIcon from "@mui/icons-material/MailOutline";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";
import { relativeFuture } from "../../utils/time";
import { useApi } from "../../api/ApiContext";
import { useAppNavigate } from "../../hooks/useAppNavigate";
import { useQueryClient } from "@tanstack/react-query";
import { usePendingTasks, useCompletedTasks, useDrafts, useDraftSummary } from "../../lib/doctorQueries";
import { QK } from "../../lib/queryKeys";
import { useDoctorStore } from "../../store/doctorStore";
import EmptyState from "../../components/EmptyState";
import SectionLoading from "../../components/SectionLoading";
import PullToRefresh from "../../components/PullToRefresh";
import SectionLabel from "../../components/SectionLabel";
import AppButton from "../../components/AppButton";
import SheetDialog from "../../components/SheetDialog";
import PageSkeleton from "../../components/PageSkeleton";

import TaskDetailSubpage from "./subpages/TaskDetailSubpage";

import ActionRow from "../../components/ActionRow";
import FilterBar from "../../components/FilterBar";
import NewItemCard from "../../components/NewItemCard";
import { TYPE, COLOR, RADIUS, HIGHLIGHT_ROW_SX } from "../../theme";
import { dp } from "../../utils/doctorBasePath";
import { markOnboardingStep, ONBOARDING_STEP } from "./constants";

// Task type badge mapping removed — ActionRow uses checkbox instead of IconBadge

// ── Scheduled follow-up row ──
// Old TaskCheckbox, CompletableRow, ScheduledRow, TaskRow, SentRow replaced by ActionRow

// ── Send confirmation sheet ──
function SendConfirmSheet({ open, onClose, item, onConfirm, sending }) {
  const navigate = useAppNavigate();
  if (!item) return null;
  return (
    <SheetDialog
      open={open}
      onClose={onClose}
      title="确认发送"
      subtitle={`${item.patient_name} · ${item.patient_context || ""}`}
      footer={
        <Box sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
          <AppButton
            variant="primary"
            size="lg"
            fullWidth
            onClick={onConfirm}
            loading={sending}
            loadingLabel="发送中..."
          >
            确认发送
          </AppButton>
          <AppButton
            variant="secondary"
            size="lg"
            fullWidth
            onClick={onClose}
            disabled={sending}
          >
            返回修改
          </AppButton>
        </Box>
      }
    >
      {/* Draft text */}
      <Box sx={{
        bgcolor: COLOR.surface,
        borderRadius: RADIUS.md,
        px: 1.5, py: 1, mb: 1.5,
      }}>
        <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text2, lineHeight: 1.6 }}>
          {item.draft_text}
        </Typography>
      </Box>

      {/* Cited rules */}
      {item.cited_rules?.length > 0 && (
        <Box sx={{ mb: 1.5 }}>
          <Typography sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.text4, mb: 0.5 }}>
            引用规则：
          </Typography>
          <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.5 }}>
            {item.cited_rules.map((rule) => (
              <Box
                key={rule.id}
                component="span"
                onClick={() => {
                  onClose();
                  navigate(`${dp("settings/knowledge")}/${rule.id}`);
                }}
                sx={{
                  fontSize: 11,
                  color: COLOR.primary,
                  bgcolor: COLOR.successLight,
                  px: 1,
                  py: 0.5,
                  borderRadius: RADIUS.sm,
                  cursor: "pointer",
                  fontWeight: 500,
                  "&:hover": { bgcolor: COLOR.successLight },
                }}
              >
                {rule.title}
              </Box>
            ))}
          </Box>
        </Box>
      )}

      {/* Disclaimer */}
      <Typography sx={{
        fontSize: TYPE.micro.fontSize,
        color: COLOR.text4,
        textAlign: "center",
        mt: 1,
      }}>
        AI辅助生成，经医生审核
      </Typography>
    </SheetDialog>
  );
}

// ── Create task sheet ──
function CreateTaskSheet({ open, onClose, doctorId, onCreated }) {
  const api = useApi();
  const queryClient = useQueryClient();
  const [title, setTitle] = useState("");
  const [dueAt, setDueAt] = useState("");
  const [creating, setCreating] = useState(false);

  const handleCreate = async () => {
    if (!title.trim() || creating) return;
    setCreating(true);
    try {
      const task = await api.createTask(doctorId, {
        taskType: "general",
        title: title.trim(),
        dueAt: dueAt || undefined,
      });
      queryClient.invalidateQueries({ queryKey: QK.tasks(doctorId, "pending") });
      onCreated?.(task);
      setTitle("");
      setDueAt("");
      onClose();
    } catch {
      // keep sheet open
    } finally {
      setCreating(false);
    }
  };

  return (
    <SheetDialog
      open={open}
      onClose={onClose}
      title="新建任务"
      footer={
        <Box sx={{ display: "flex", gap: 1 }}>
          <AppButton variant="secondary" size="lg" fullWidth onClick={onClose} disabled={creating}>
            取消
          </AppButton>
          <AppButton variant="primary" size="lg" fullWidth onClick={handleCreate} loading={creating} disabled={!title.trim()}>
            创建
          </AppButton>
        </Box>
      }
    >
      <Box sx={{ display: "flex", flexDirection: "column", gap: 2, overflow: "hidden" }}>
        <Box sx={{ minWidth: 0 }}>
          <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4, mb: 0.5 }}>任务标题</Typography>
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="例如：术后复查CT"
            style={{
              width: "100%", padding: "12px", border: `0.5px solid #e8e8e8`,
              borderRadius: "6px", fontSize: "15px", boxSizing: "border-box",
              outline: "none", fontFamily: "inherit",
            }}
          />
        </Box>
        <Box sx={{ minWidth: 0 }}>
          <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4, mb: 0.5 }}>截止日期（可选）</Typography>
          <input
            type="date"
            value={dueAt}
            onChange={(e) => setDueAt(e.target.value)}
            style={{
              width: "100%", padding: "12px",
              border: `0.5px solid #e8e8e8`,
              borderRadius: "6px", fontSize: "15px", boxSizing: "border-box",
              outline: "none", fontFamily: "inherit",
            }}
          />
        </Box>
      </Box>
    </SheetDialog>
  );
}

// ── Snooze / reschedule sheet ──
function SnoozeSheet({ open, onClose, taskId, doctorId, onSnoozed }) {
  const api = useApi();
  const queryClient = useQueryClient();
  const [showDatePicker, setShowDatePicker] = useState(false);
  const [saving, setSaving] = useState(false);
  const dateRef = useRef(null);

  const handlePick = async (isoDate) => {
    if (saving) return;
    setSaving(true);
    try {
      await api.postponeTask(taskId, doctorId, isoDate);
      queryClient.invalidateQueries({ queryKey: QK.tasks(doctorId, "pending") });
      queryClient.invalidateQueries({ queryKey: QK.draftSummary(doctorId) });
      onSnoozed?.();
      onClose();
    } catch {
      // keep sheet open
    } finally {
      setSaving(false);
      setShowDatePicker(false);
    }
  };

  const tomorrow = () => {
    const d = new Date(); d.setDate(d.getDate() + 1);
    return d.toISOString().slice(0, 10);
  };
  const plus3 = () => {
    const d = new Date(); d.setDate(d.getDate() + 3);
    return d.toISOString().slice(0, 10);
  };
  const nextMonday = () => {
    const d = new Date();
    const day = d.getDay();
    const diff = day === 0 ? 1 : 8 - day;
    d.setDate(d.getDate() + diff);
    return d.toISOString().slice(0, 10);
  };

  const options = [
    { label: "明天", getDate: tomorrow },
    { label: "3天后", getDate: plus3 },
    { label: "下周一", getDate: nextMonday },
  ];

  return (
    <SheetDialog
      open={open}
      onClose={() => { if (!saving) { onClose(); setShowDatePicker(false); } }}
      title="延期任务"
      subtitle="选择新的截止日期"
    >
      <Box sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
        {options.map((opt) => (
          <AppButton
            key={opt.label}
            variant="secondary"
            size="lg"
            fullWidth
            onClick={() => handlePick(opt.getDate())}
            loading={saving}
          >
            {opt.label}
          </AppButton>
        ))}

        {/* Custom date picker */}
        {!showDatePicker ? (
          <AppButton
            variant="secondary"
            size="lg"
            fullWidth
            onClick={() => {
              setShowDatePicker(true);
              setTimeout(() => dateRef.current?.showPicker?.(), 50);
            }}
          >
            自选日期
          </AppButton>
        ) : (
          <Box sx={{ display: "flex", gap: 1, alignItems: "center" }}>
            <Box
              component="input"
              ref={dateRef}
              type="date"
              onChange={(e) => {
                if (e.target.value) handlePick(e.target.value);
              }}
              sx={{
                flex: 1, p: 1.5, border: `0.5px solid ${COLOR.border}`,
                borderRadius: RADIUS.sm, fontSize: TYPE.body.fontSize,
                outline: "none", fontFamily: "inherit",
                "&:focus": { borderColor: COLOR.primary },
              }}
            />
            <AppButton
              variant="secondary"
              size="md"
              onClick={() => setShowDatePicker(false)}
            >
              取消
            </AppButton>
          </Box>
        )}
      </Box>
    </SheetDialog>
  );
}

// ── Main page ──
const VALID_TABS = new Set(["followups", "completed", "sent"]);

export default function TaskPage({ doctorId, urlSubpage }) {
  const api = useApi();
  const navigate = useAppNavigate();
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down("sm"));
  const [createOpen, setCreateOpen] = useState(false);
  const params = new URLSearchParams(window.location.search);
  const origin = params.get("origin") || "";
  const highlightTaskIds = new Set(
    (params.get("highlight_task_ids") || "")
      .split(",")
      .map((value) => value.trim())
      .filter(Boolean)
  );
  const { doctorId: _doctorId } = useDoctorStore();
  const queryClient = useQueryClient();
  const [error, setError] = useState(null);

  // Snooze sheet state
  const [snoozeTaskId, setSnoozeTaskId] = useState(null);

  // Send confirmation sheet state
  const [confirmItem, setConfirmItem] = useState(null);
  const [sending, setSending] = useState(false);

  // Teaching prompt state (shown after doctor edits a draft)
  const [teachEditId, setTeachEditId] = useState(null);
  const [teachSaving, setTeachSaving] = useState(false);
  const [teachSaved, setTeachSaved] = useState(false);

  const { data: pendingTasksData, isLoading: ptLoading, refetch: refetchPending } = usePendingTasks();
  const { data: completedTasksData, isLoading: ctLoading, refetch: refetchCompleted } = useCompletedTasks();
  const { data: draftsDataRaw, isLoading: drLoading, refetch: refetchDrafts } = useDrafts();
  const { data: summaryData, isLoading: sumLoading, refetch: refetchSummary } = useDraftSummary();

  const loading = ptLoading || ctLoading || drLoading || sumLoading;

  // Derive canonical data shape from React Query results
  const _pendingTasks  = Array.isArray(pendingTasksData) ? pendingTasksData : (pendingTasksData?.items || []);
  const _completedTasksList = Array.isArray(completedTasksData) ? completedTasksData : (completedTasksData?.items || []);
  const _pendingMessages = Array.isArray(draftsDataRaw) ? draftsDataRaw : (draftsDataRaw?.pending_messages || []);
  const _upcomingFollowups = summaryData?.upcoming_followups || [];
  const _recentlySent = (() => {
    const fromSummary = summaryData?.recently_sent || summaryData?.sent || [];
    return [...fromSummary, ..._completedTasksList];
  })();

  const data = { pending_messages: _pendingMessages, upcoming_followups: _upcomingFollowups, tasks: _pendingTasks, recently_sent: _recentlySent };
  const summary = summaryData || {};

  const loadData = useCallback(() => {
    refetchPending(); refetchCompleted(); refetchDrafts(); refetchSummary();
  }, [refetchPending, refetchCompleted, refetchDrafts, refetchSummary]);

  // Local state for optimistic mutations (setData/setSummary used by handlers below)
  const [dataOverride, setData] = useState(null);
  const [summaryOverride, setSummary] = useState(null);

  // Reset overrides when React Query data refreshes
  useEffect(() => { setData(null); setSummary(null); }, [pendingTasksData, completedTasksData, draftsDataRaw, summaryData]); // eslint-disable-line react-hooks/exhaustive-deps

  // Merge optimistic overrides on top of derived data
  const effectiveData = dataOverride ? { ...data, ...dataOverride } : data;
  const effectiveSummary = summaryOverride ? { ...summary, ...summaryOverride } : summary;

  // Ref so mutation handlers always see current effective data without stale closure
  const effectiveDataRef = { current: effectiveData };
  const effectiveSummaryRef = { current: effectiveSummary };

  useEffect(() => {
    if (!doctorId) return;
    if (origin === "review_finalize") {
      markOnboardingStep(doctorId, ONBOARDING_STEP.followupTask);
    }
  }, [doctorId, origin]);

  const pendingMessages = effectiveData?.pending_messages || [];
  const upcomingFollowups = effectiveData?.upcoming_followups || [];
  const pendingTasks = effectiveData?.tasks || [];
  const recentlySent = effectiveData?.recently_sent || [];

  // Merge followups + tasks
  const allPendingItems = [
    ...upcomingFollowups.map((f) => ({ ...f, _isFollowup: true, _sortDate: f.due_at || f.due_label || "" })),
    ...pendingTasks
      .filter((t) => !t.title?.startsWith("审阅"))
      .map((t) => ({ ...t, _isFollowup: false, _sortDate: t.due_at || t.due || "" })),
  ].sort((a, b) => {
    return (a._sortDate || "").localeCompare(b._sortDate || "");
  });

  // Group items by relative time buckets (local timezone)
  const _groupByDate = (items) => {
    const now = new Date();
    const localDate = (d) => `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}-${String(d.getDate()).padStart(2,"0")}`;
    const todayStr = localDate(now);
    const tomorrow = new Date(now);
    tomorrow.setDate(tomorrow.getDate() + 1);
    const tomorrowStr = localDate(tomorrow);
    const weekEnd = new Date(now);
    weekEnd.setDate(weekEnd.getDate() + (7 - now.getDay()));
    const weekEndStr = localDate(weekEnd);

    const groups = [];
    const buckets = { overdue: [], today: [], tomorrow: [], thisWeek: [], later: [] };

    items.forEach((item) => {
      const dueRaw = item.due_at || item._sortDate || "";
      // Backend stores naive UTC; normalize like relativeFuture() so that
      // bucketing and the right-side label always agree on the local date.
      const normalized = dueRaw && !dueRaw.includes("Z") && !dueRaw.includes("+")
        ? dueRaw + "Z"
        : dueRaw;
      const dueDate = normalized ? new Date(normalized) : null;
      const dueDateStr = dueDate ? localDate(dueDate) : "";

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

    if (buckets.overdue.length) groups.push({ label: "已逾期", color: COLOR.danger, items: buckets.overdue });
    if (buckets.today.length) groups.push({ label: "今天", color: COLOR.primary, items: buckets.today });
    if (buckets.tomorrow.length) groups.push({ label: "明天", color: COLOR.text3, items: buckets.tomorrow });
    if (buckets.thisWeek.length) groups.push({ label: "本周", color: COLOR.text4, items: buckets.thisWeek });
    if (buckets.later.length) groups.push({ label: "之后", color: COLOR.text4, items: buckets.later });
    return groups;
  };
  const dateGroups = _groupByDate(allPendingItems);

  const handleOpenSend = (item) => {
    setConfirmItem(item);
  };

  const handleConfirmSend = async () => {
    if (!confirmItem) return;
    setSending(true);
    try {
      await (api.sendDraft || (() => Promise.resolve()))(confirmItem.id, doctorId);
      // Invalidate badge caches after sending
      queryClient.invalidateQueries({ queryKey: QK.draftSummary(_doctorId) });
      queryClient.invalidateQueries({ queryKey: QK.drafts(_doctorId) });
      // Optimistic update — remove from pending, add to sent
      const cur = effectiveDataRef.current;
      setData({
        ...cur,
        pending_messages: (cur?.pending_messages || []).filter((m) => m.id !== confirmItem.id),
        recently_sent: [
          {
            id: confirmItem.id,
            patient_name: confirmItem.patient_name,
            task: "回复消息",
            read_status: "未读",
            time: "刚刚",
          },
          ...(cur?.recently_sent || []),
        ],
      });
      const curS = effectiveSummaryRef.current;
      setSummary({
        ...curS,
        pending_reply: Math.max(0, (curS?.pending_reply || 0) - 1),
      });
      setConfirmItem(null);
    } catch {
      // keep sheet open on error
    } finally {
      setSending(false);
    }
  };

  // Teaching prompt: save edit as knowledge rule
  const handleTeachPrompt = (editId) => {
    setTeachEditId(editId);
    setTeachSaved(false);
  };

  const handleTeachSave = async () => {
    if (!teachEditId || teachSaving) return;
    setTeachSaving(true);
    try {
      await (api.createRuleFromEdit || (() => Promise.resolve()))(teachEditId, doctorId);
      queryClient.invalidateQueries({ queryKey: QK.knowledge(_doctorId) });
      setTeachEditId(null);
      setTeachSaved(true);
    } catch {
      // silent
    } finally {
      setTeachSaving(false);
    }
  };

  const handleTeachDismiss = () => {
    setTeachEditId(null);
  };

  const tabFromUrl = new URLSearchParams(window.location.search).get("tab");
  const initialTab = tabFromUrl && VALID_TABS.has(tabFromUrl) ? tabFromUrl : "followups";
  const [filter, setFilter] = useState(initialTab);
  const totalCount = allPendingItems.length;
  const isEmpty = !loading && !error && totalCount === 0 && recentlySent.length === 0;

  const handleCompleteTask = async (item) => {
    // Move from pending to completed
    const completedItem = {
      id: item.id,
      patient_name: item.patient_name || item.task || "任务",
      task: item.task || item.title || "",
      read_status: "已完成",
      time: "刚刚",
      patient_id: item.patient_id,
    };
    const cur = effectiveDataRef.current;
    setData({
      ...cur,
      upcoming_followups: (cur?.upcoming_followups || []).filter((f) => f.id !== item.id),
      tasks: (cur?.tasks || []).filter((t) => t.id !== item.id),
      recently_sent: [completedItem, ...(cur?.recently_sent || [])],
    });
    // Call API if available
    try {
      const patchTask = api.patchTask || (() => Promise.resolve());
      await patchTask(item.id, doctorId, "completed");
      queryClient.invalidateQueries({ queryKey: QK.tasks(_doctorId, "pending") });
      queryClient.invalidateQueries({ queryKey: QK.tasks(_doctorId, "completed") });
    } catch { /* silent */ }
  };

  const handleUncompleteTask = async (item) => {
    // Move from completed back to pending tasks
    const pendingItem = {
      id: item.id,
      title: item.task || item.title || "任务",
      content: "",
      patient_name: item.patient_name,
      patient_id: item.patient_id,
      task_type: "general",
      due_at: null,
    };
    const cur = effectiveDataRef.current;
    setData({
      ...cur,
      tasks: [pendingItem, ...(cur?.tasks || [])],
      recently_sent: (cur?.recently_sent || []).filter((s) => s.id !== item.id),
    });
    try {
      const patchTask = api.patchTask || (() => Promise.resolve());
      await patchTask(item.id, doctorId, "pending");
      queryClient.invalidateQueries({ queryKey: QK.tasks(_doctorId, "pending") });
      queryClient.invalidateQueries({ queryKey: QK.tasks(_doctorId, "completed") });
    } catch { /* silent */ }
  };

  const handleFilter = (key) => {
    const next = filter === key ? "followups" : key;
    setFilter(next);
    const url = new URL(window.location);
    url.searchParams.set("tab", next);
    window.history.replaceState(null, "", url);
  };

  const showMessages = filter === "all" || filter === "messages";
  const showFollowups = filter === "all" || filter === "followups";
  const showSent = filter === "all" || filter === "completed" || filter === "sent";

  const showDetail = !!urlSubpage && urlSubpage !== "tasks";
  const mobileSubpage = showDetail ? (
    <TaskDetailSubpage
      taskId={urlSubpage}
      doctorId={doctorId}
      onBack={() => navigate(-1)}
      isMobile={isMobile}
    />
  ) : null;

  return (
    <>
    <PageSkeleton
      title="任务"
      isMobile={isMobile}
      mobileView={mobileSubpage}
      listPane={
      <PullToRefresh sx={{ flex: 1 }} pb="80px">
        {origin === "patient_submit" && (
          <Box sx={{ mt: 1, bgcolor: COLOR.white, borderTop: `0.5px solid ${COLOR.border}`, borderBottom: `0.5px solid ${COLOR.border}`, px: 2, py: 1.5 }}>
            <Typography sx={{ fontSize: TYPE.heading.fontSize, fontWeight: 600, color: COLOR.text1 }}>
              已创建审核任务
            </Typography>
            <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text3, mt: 0.45, lineHeight: 1.6 }}>
              患者完成预问诊后，系统会先创建一条审核任务，提醒医生查看新病例。
            </Typography>
          </Box>
        )}
        {origin === "review_finalize" && (
          <Box sx={{ mt: 1, bgcolor: COLOR.white, borderTop: `0.5px solid ${COLOR.border}`, borderBottom: `0.5px solid ${COLOR.border}`, px: 2, py: 1.5 }}>
            <Typography sx={{ fontSize: TYPE.heading.fontSize, fontWeight: 600, color: COLOR.text1 }}>
              已生成随访任务
            </Typography>
            <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text3, mt: 0.45, lineHeight: 1.6 }}>
              医生完成审核后，系统会根据最终确认的医嘱和随访计划生成后续任务。
            </Typography>
          </Box>
        )}

        {/* Loading */}
        {loading && (
          <SectionLoading py={6} />
        )}

        {/* Error */}
        {!loading && error && (
          <Box sx={{ py: 6, textAlign: "center" }}>
            <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text4 }}>
              {error}
            </Typography>
            <Typography
              onClick={loadData}
              sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.primary, mt: 1, cursor: "pointer" }}
            >
              重试
            </Typography>
          </Box>
        )}

        {/* Content */}
        {!loading && !error && (
          <>
            {/* ── Filter stat bar — always visible ── */}
            <FilterBar
              items={[
                { key: "followups", label: "待完成", activeColor: COLOR.warning },
                { key: "completed", label: "已完成", activeColor: COLOR.text4 },
              ]}
              active={filter}
              counts={{ followups: allPendingItems.length, completed: recentlySent.length }}
              onChange={handleFilter}
              dividers
            />

            <NewItemCard title="新建任务" subtitle="添加待办提醒或随访任务" onClick={() => setCreateOpen(true)} />

            {/* ── Date-grouped task list ── */}
            {showFollowups && allPendingItems.length > 0 && (() => {
              const renderRow = (item, urgency) => {
                const title = item._isFollowup
                  ? `${item.patient_name} · ${item.task}`
                  : (item.title || "任务");
                const subtitle = item._isFollowup ? item.detail : item.content;
                const dueLabel = item.due_at ? (relativeFuture(item.due_at) || "") : "";
                const isOverdue = urgency === "overdue";

                // When overdue, wrap the label in a tappable element to open the snooze sheet
                const rightContent = isOverdue && dueLabel ? (
                  <Box
                    component="span"
                    onClick={(e) => {
                      e.stopPropagation();
                      setSnoozeTaskId(item.id);
                    }}
                    sx={{
                      color: COLOR.danger,
                      fontWeight: 500,
                      fontSize: TYPE.caption.fontSize,
                      cursor: "pointer",
                      textDecoration: "underline",
                      textDecorationStyle: "dashed",
                      textUnderlineOffset: "2px",
                      "&:active": { opacity: 0.6 },
                    }}
                  >
                    {dueLabel}
                  </Box>
                ) : dueLabel;

                return (
                  <ActionRow
                    key={`${item._isFollowup ? "f" : "t"}-${item.id}`}
                    title={title}
                    subtitle={subtitle}
                    right={rightContent}
                    overdue={isOverdue}
                    onToggle={() => handleCompleteTask(item)}
                    onClick={() => navigate(`${dp("tasks")}/${item.id}`)}
                    sx={highlightTaskIds.has(String(item.id)) ? HIGHLIGHT_ROW_SX : {}}
                  />
                );
              };

              return (
                <>
                  {dateGroups.map((group) => (
                    <Box key={group.label}>
                      <SectionLabel sx={{ color: group.color }}>{group.label}</SectionLabel>
                      <Box sx={{ bgcolor: COLOR.white, borderTop: `0.5px solid ${COLOR.border}`, borderBottom: `0.5px solid ${COLOR.border}` }}>
                        {group.items.map((item) => renderRow(item, group.label === "已逾期" ? "overdue" : group.label === "今天" ? "today" : "upcoming"))}
                      </Box>
                    </Box>
                  ))}
                </>
              );
            })()}

            {/* ── Section: 已完成 ── */}
            {showSent && recentlySent.length > 0 && (
              <>
                <SectionLabel>已完成</SectionLabel>
                <Box sx={{ bgcolor: COLOR.white, borderTop: `0.5px solid ${COLOR.border}`, borderBottom: `0.5px solid ${COLOR.border}` }}>
                  {recentlySent.map((s) => (
                    <Box key={s.id}
                      sx={{
                        display: "flex", alignItems: "center", gap: 1, px: 2, py: 1.5,
                        borderBottom: `0.5px solid ${COLOR.borderLight}`,
                        "&:last-child": { borderBottom: "none" },
                        ...(highlightTaskIds.has(String(s.id)) ? HIGHLIGHT_ROW_SX : {}),
                      }}>
                      <CheckCircleOutlineIcon
                        onClick={(e) => { e.stopPropagation(); handleUncompleteTask(s); }}
                        sx={{
                          fontSize: 24, color: COLOR.primary, flexShrink: 0, cursor: "pointer",
                          "&:active": { opacity: 0.6 },
                        }}
                      />
                      <Box
                        onClick={() => navigate(`${dp("tasks")}/${s.id}`)}
                        sx={{ flex: 1, minWidth: 0, cursor: "pointer", "&:active": { opacity: 0.8 } }}>
                        <Typography sx={{ fontSize: TYPE.action.fontSize, color: COLOR.text4, textDecoration: "line-through", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                          {s.patient_name} · {s.task || s.title}
                        </Typography>
                      </Box>
                      <Typography onClick={() => navigate(`${dp("tasks")}/${s.id}`)} sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.text4, cursor: "pointer" }}>{s.time}</Typography>
                    </Box>
                  ))}
                </Box>
              </>
            )}

            {/* Empty state for active tab */}
            {isEmpty && (
              <EmptyState
                icon={<MailOutlineIcon />}
                title="暂无待处理项目"
                subtitle="患者消息会自动出现在这里"
              />
            )}
          </>
        )}
      </PullToRefresh>
      }
    />

      {/* Send confirmation sheet */}
      <SendConfirmSheet
        open={!!confirmItem}
        onClose={() => !sending && setConfirmItem(null)}
        item={confirmItem}
        onConfirm={handleConfirmSend}
        sending={sending}
      />

      {/* Create task sheet */}
      <CreateTaskSheet
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        doctorId={doctorId}
        onCreated={() => loadData()}
      />

      {/* Snooze / reschedule sheet */}
      <SnoozeSheet
        open={!!snoozeTaskId}
        onClose={() => setSnoozeTaskId(null)}
        taskId={snoozeTaskId}
        doctorId={doctorId}
        onSnoozed={() => loadData()}
      />

      {/* Teaching prompt: save edited draft as knowledge rule */}
      <Snackbar
        open={!!teachEditId}
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
        message="您的修改已记录。要将这个回复模式保存为知识条目吗？"
        action={
          <Box sx={{ display: "flex", gap: 1 }}>
            <Typography
              onClick={handleTeachDismiss}
              sx={{
                fontSize: TYPE.secondary.fontSize, color: COLOR.white,
                cursor: "pointer", opacity: 0.8,
                "&:active": { opacity: 0.5 },
              }}
            >
              跳过
            </Typography>
            <Typography
              onClick={handleTeachSave}
              sx={{
                fontSize: TYPE.secondary.fontSize, color: COLOR.primaryLight,
                cursor: teachSaving ? "default" : "pointer",
                fontWeight: 500, opacity: teachSaving ? 0.5 : 1,
                "&:active": teachSaving ? {} : { opacity: 0.5 },
              }}
            >
              {teachSaving ? "保存中..." : "保存"}
            </Typography>
          </Box>
        }
      />

      {/* Success toast after saving as knowledge rule */}
      <Snackbar
        open={teachSaved}
        autoHideDuration={2000}
        onClose={() => setTeachSaved(false)}
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
        message="已保存为知识条目"
      />
    </>
  );
}
