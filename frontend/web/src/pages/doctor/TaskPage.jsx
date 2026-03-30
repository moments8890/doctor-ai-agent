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
import { useEffect, useState, useCallback } from "react";
import { Box, CircularProgress, Snackbar, Typography, useMediaQuery, useTheme } from "@mui/material";
import MailOutlineIcon from "@mui/icons-material/MailOutline";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";
import { useApi } from "../../api/ApiContext";
import { useAppNavigate } from "../../hooks/useAppNavigate";
import EmptyState from "../../components/EmptyState";
import SectionLoading from "../../components/SectionLoading";
import SectionLabel from "../../components/SectionLabel";
import AppButton from "../../components/AppButton";
import SheetDialog from "../../components/SheetDialog";
import PageSkeleton from "../../components/PageSkeleton";

import TaskDetailSubpage from "./subpages/TaskDetailSubpage";

import FilterBar from "../../components/FilterBar";
import NewItemCard from "../../components/NewItemCard";
import { TYPE, COLOR, RADIUS, HIGHLIGHT_ROW_SX } from "../../theme";
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
                  navigate(`/doctor/settings/knowledge/${rule.id}`);
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
  const [title, setTitle] = useState("");
  const [dueAt, setDueAt] = useState("");
  const [creating, setCreating] = useState(false);

  const handleCreate = async () => {
    if (!title.trim() || creating) return;
    setCreating(true);
    try {
      const task = await (api.createTask || (() => Promise.resolve({})))(doctorId, {
        task_type: "general",
        title: title.trim(),
        due_at: dueAt || undefined,
      });
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
      <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
        <Box>
          <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4, mb: 0.5 }}>任务标题</Typography>
          <Box
            component="input"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="例如：术后复查CT"
            sx={{
              width: "100%", p: 1.5, border: `0.5px solid ${COLOR.border}`,
              borderRadius: RADIUS.sm, fontSize: TYPE.body.fontSize,
              outline: "none", fontFamily: "inherit",
              "&:focus": { borderColor: COLOR.primary },
            }}
          />
        </Box>
        <Box>
          <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4, mb: 0.5 }}>截止日期（可选）</Typography>
          <Box
            component="input"
            type="date"
            value={dueAt}
            onChange={(e) => setDueAt(e.target.value)}
            sx={{
              width: "100%", p: 1.5, border: `0.5px solid ${COLOR.border}`,
              borderRadius: RADIUS.sm, fontSize: TYPE.body.fontSize,
              outline: "none", fontFamily: "inherit",
              "&:focus": { borderColor: COLOR.primary },
            }}
          />
        </Box>
      </Box>
    </SheetDialog>
  );
}

// ── Main page ──
const VALID_TABS = new Set(["followups", "sent"]);

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
  const [data, setData] = useState(null);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Send confirmation sheet state
  const [confirmItem, setConfirmItem] = useState(null);
  const [sending, setSending] = useState(false);

  // Teaching prompt state (shown after doctor edits a draft)
  const [teachEditId, setTeachEditId] = useState(null);
  const [teachSaving, setTeachSaving] = useState(false);
  const [teachSaved, setTeachSaved] = useState(false);

  const loadData = useCallback(async () => {
    if (!doctorId) return;
    setLoading(true);
    setError(null);
    try {
      const [draftsRes, summaryRes, tasksRes] = await Promise.all([
        (api.fetchDrafts || (() => Promise.resolve({})))(doctorId),
        (api.fetchDraftSummary || (() => Promise.resolve({})))(doctorId),
        (api.getTasks || (() => Promise.resolve([])))(doctorId, "pending")
          .then((d) => Array.isArray(d) ? d : (d.items || []))
          .catch(() => []),
      ]);
      // Handle both old flat array format and new structured format
      if (Array.isArray(draftsRes)) {
        setData({ pending_messages: draftsRes, upcoming_followups: [], recently_sent: [], tasks: tasksRes });
      } else {
        setData({ ...(draftsRes || {}), tasks: tasksRes });
      }
      setSummary(summaryRes || {});
    } catch (err) {
      // 404 means no data yet — treat as empty, not as an error
      const is404 = err?.status === 404 || err?.response?.status === 404 || (err.message && /not found/i.test(err.message));
      if (is404) {
        setData({ pending_messages: [], upcoming_followups: [], recently_sent: [], tasks: [] });
        setSummary({});
      } else {
        setError(err.message || "加载失败");
      }
    } finally {
      setLoading(false);
    }
  }, [doctorId, api]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  useEffect(() => {
    if (!doctorId) return;
    if (origin === "review_finalize") {
      markOnboardingStep(doctorId, ONBOARDING_STEP.followupTask);
    }
  }, [doctorId, origin]);

  const pendingMessages = data?.pending_messages || [];
  const upcomingFollowups = data?.upcoming_followups || [];
  const pendingTasks = data?.tasks || [];
  const recentlySent = data?.recently_sent || [];

  // Merge followups + tasks into one sorted list
  const allPendingItems = [
    ...upcomingFollowups.map((f) => ({ ...f, _isFollowup: true, _sortDate: f.due_at || f.due_label || "" })),
    ...pendingTasks.map((t) => ({ ...t, _isFollowup: false, _sortDate: t.due_at || t.due || "" })),
  ].sort((a, b) => {
    // Urgent/soon items first
    if (a.soon && !b.soon) return -1;
    if (!a.soon && b.soon) return 1;
    return (a._sortDate || "").localeCompare(b._sortDate || "");
  });

  const handleOpenSend = (item) => {
    setConfirmItem(item);
  };

  const handleConfirmSend = async () => {
    if (!confirmItem) return;
    setSending(true);
    try {
      await (api.sendDraft || (() => Promise.resolve()))(confirmItem.id, doctorId);
      // Remove from pending list
      setData((prev) => ({
        ...prev,
        pending_messages: (prev?.pending_messages || []).filter((m) => m.id !== confirmItem.id),
        recently_sent: [
          {
            id: confirmItem.id,
            patient_name: confirmItem.patient_name,
            task: "回复消息",
            read_status: "未读",
            time: "刚刚",
          },
          ...(prev?.recently_sent || []),
        ],
      }));
      // Update summary counts
      setSummary((prev) => ({
        ...prev,
        pending_reply: Math.max(0, (prev?.pending_reply || 0) - 1),
      }));
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
    setData((prev) => ({
      ...prev,
      upcoming_followups: (prev?.upcoming_followups || []).filter((f) => f.id !== item.id),
      tasks: (prev?.tasks || []).filter((t) => t.id !== item.id),
      recently_sent: [completedItem, ...(prev?.recently_sent || [])],
    }));
    // Call API if available
    try {
      const patchTask = api.patchTask || (() => Promise.resolve());
      await patchTask(item.id, doctorId, "completed");
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
    setData((prev) => ({
      ...prev,
      tasks: [pendingItem, ...(prev?.tasks || [])],
      recently_sent: (prev?.recently_sent || []).filter((s) => s.id !== item.id),
    }));
    try {
      const patchTask = api.patchTask || (() => Promise.resolve());
      await patchTask(item.id, doctorId, "pending");
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
  const showSent = filter === "all" || filter === "sent";

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
      <Box sx={{ flex: 1, overflow: "auto", pb: "80px" }}>
        {origin === "patient_submit" && (
          <Box sx={{ mt: 1, bgcolor: COLOR.white, borderTop: `0.5px solid ${COLOR.border}`, borderBottom: `0.5px solid ${COLOR.border}`, px: 2, py: 15 }}>
            <Typography sx={{ fontSize: TYPE.heading.fontSize, fontWeight: 600, color: COLOR.text1 }}>
              已创建审核任务
            </Typography>
            <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text3, mt: 0.45, lineHeight: 1.6 }}>
              患者完成预问诊后，系统会先创建一条审核任务，提醒医生查看新病例。
            </Typography>
          </Box>
        )}
        {origin === "review_finalize" && (
          <Box sx={{ mt: 1, bgcolor: COLOR.white, borderTop: `0.5px solid ${COLOR.border}`, borderBottom: `0.5px solid ${COLOR.border}`, px: 2, py: 15 }}>
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
                { key: "sent", label: "已完成", activeColor: COLOR.text4 },
              ]}
              active={filter}
              counts={{ followups: allPendingItems.length, sent: recentlySent.length }}
              onChange={handleFilter}
              dividers
            />

            <NewItemCard title="新建任务" subtitle="添加待办提醒或随访任务" onClick={() => setCreateOpen(true)} />

            {/* ── Section: 待完成 (grouped by urgency) ── */}
            {showFollowups && allPendingItems.length > 0 && (() => {
              const urgent = allPendingItems.filter(item => item.soon);
              const upcoming = allPendingItems.filter(item => !item.soon);

              const renderRow = (item) => {
                const isUrgent = item.soon;
                const title = item._isFollowup ? `${item.patient_name} · ${item.task}` : (item.title || "任务");
                const subtitle = item._isFollowup ? item.detail : item.content;
                const dateStr = item._isFollowup ? (item.due_label || "") : (item.due_at ? item.due_at.slice(0, 10) : "");
                return (
                  <Box key={`${item._isFollowup ? "f" : "t"}-${item.id}`}
                    sx={{
                      display: "flex", alignItems: "center", gap: 1, px: 2, py: 1.5,
                      borderBottom: `0.5px solid ${COLOR.borderLight}`,
                      ...(isUrgent ? { bgcolor: COLOR.dangerLight } : {}),
                      "&:last-child": { borderBottom: "none" },
                      ...(highlightTaskIds.has(String(item.id)) ? HIGHLIGHT_ROW_SX : {}),
                    }}>
                    <Box
                      onClick={(e) => { e.stopPropagation(); handleCompleteTask(item); }}
                      sx={{
                        width: 22, height: 22, borderRadius: "50%",
                        border: `2px solid ${isUrgent ? COLOR.danger : COLOR.border}`,
                        flexShrink: 0, cursor: "pointer",
                        display: "flex", alignItems: "center", justifyContent: "center",
                        "&:active": { bgcolor: COLOR.primaryLight, borderColor: COLOR.primary },
                      }}
                    />
                    <Box
                      onClick={() => navigate(`/doctor/tasks/${item.id}`)}
                      sx={{ flex: 1, minWidth: 0, cursor: "pointer", "&:active": { opacity: 0.8 } }}>
                      <Typography sx={{ fontSize: TYPE.action.fontSize, fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {title}
                      </Typography>
                      {subtitle && (
                        <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text3, mt: 0.25, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                          {subtitle}
                        </Typography>
                      )}
                    </Box>
                    <Box onClick={() => navigate(`/doctor/tasks/${item.id}`)} sx={{ flexShrink: 0, textAlign: "right", cursor: "pointer" }}>
                      <Typography sx={{ fontSize: TYPE.micro.fontSize, color: isUrgent ? COLOR.danger : COLOR.text4, fontWeight: isUrgent ? 500 : 400 }}>
                        {dateStr}
                      </Typography>
                      <Typography sx={{ fontSize: 14, color: COLOR.text4, mt: 0.5 }}>›</Typography>
                    </Box>
                  </Box>
                );
              };

              return (
                <>
                  {urgent.length > 0 && (
                    <>
                      <SectionLabel sx={{ color: COLOR.danger }}>紧急 · 今天到期</SectionLabel>
                      <Box sx={{ bgcolor: COLOR.white, borderTop: `0.5px solid ${COLOR.border}`, borderBottom: `0.5px solid ${COLOR.border}` }}>
                        {urgent.map(renderRow)}
                      </Box>
                    </>
                  )}
                  {upcoming.length > 0 && (
                    <>
                      <SectionLabel>{urgent.length > 0 ? "即将到期" : "待完成"}</SectionLabel>
                      <Box sx={{ bgcolor: COLOR.white, borderTop: `0.5px solid ${COLOR.border}`, borderBottom: `0.5px solid ${COLOR.border}` }}>
                        {upcoming.map(renderRow)}
                      </Box>
                    </>
                  )}
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
                        onClick={() => navigate(`/doctor/tasks/${s.id}`)}
                        sx={{ flex: 1, minWidth: 0, cursor: "pointer", "&:active": { opacity: 0.8 } }}>
                        <Typography sx={{ fontSize: TYPE.action.fontSize, color: COLOR.text4, textDecoration: "line-through", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                          {s.patient_name} · {s.task || s.title}
                        </Typography>
                      </Box>
                      <Typography onClick={() => navigate(`/doctor/tasks/${s.id}`)} sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.text4, cursor: "pointer" }}>{s.time}</Typography>
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
      </Box>
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
