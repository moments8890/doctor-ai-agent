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
import { Box, CircularProgress, Snackbar, Typography } from "@mui/material";
import MailOutlineIcon from "@mui/icons-material/MailOutline";
import { useApi } from "../../api/ApiContext";
import { useAppNavigate } from "../../hooks/useAppNavigate";
import SubpageHeader from "../../components/SubpageHeader";
import EmptyState from "../../components/EmptyState";
import SectionLabel from "../../components/SectionLabel";
import AppButton from "../../components/AppButton";
import SheetDialog from "../../components/SheetDialog";
import ActionRow from "../../components/ActionRow";
import { TYPE, COLOR } from "../../theme";

// ── Task type badge mapping ──
const TASK_TYPE_BADGE = {
  follow_up: ICON_BADGES.task_follow_up,
  medication: ICON_BADGES.task_medication,
  checkup: ICON_BADGES.task_checkup,
  general: ICON_BADGES.task_general,
};

// ── Summary stat component ──
function SummaryStat({ value, label, sublabel, color, onClick }) {
  return (
    <Box onClick={onClick} sx={{ flex: 1, textAlign: "center", cursor: onClick ? "pointer" : "default", "&:active": onClick ? { opacity: 0.5 } : {} }}>
      <Typography sx={{ fontSize: TYPE.title.fontSize, fontWeight: 600, color: color || COLOR.text1 }}>
        {value}
      </Typography>
      <Typography sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.text4, mt: "2px" }}>
        {label}
      </Typography>
      {sublabel && (
        <Typography sx={{ fontSize: 10, color: COLOR.primary, mt: "1px" }}>
          {sublabel}
        </Typography>
      )}
    </Box>
  );
}

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
        borderRadius: "6px",
        px: 1.5, py: 1.2, mb: 1.5,
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
                  bgcolor: "#e8f5e9",
                  px: 1,
                  py: 0.3,
                  borderRadius: "4px",
                  cursor: "pointer",
                  fontWeight: 500,
                  "&:hover": { bgcolor: "#c8e6c9" },
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

// ── Main page ──
const VALID_TABS = new Set(["followups", "sent"]);

export default function TaskPage({ doctorId, urlSubpage }) {
  const api = useApi();
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
      await patchTask(item.id, { status: "completed" });
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
      await patchTask(item.id, { status: "pending" });
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

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%", bgcolor: COLOR.surfaceAlt }}>
      <SubpageHeader title="任务" />
      <Box sx={{ flex: 1, overflow: "auto", pb: "80px" }}>

        {/* Loading */}
        {loading && (
          <Box sx={{ display: "flex", justifyContent: "center", py: 6 }}>
            <CircularProgress size={24} sx={{ color: COLOR.text4 }} />
          </Box>
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
            <Box sx={{
              display: "flex",
              bgcolor: COLOR.white,
              borderBottom: `0.5px solid ${COLOR.border}`,
              borderTop: `0.5px solid ${COLOR.border}`,
            }}>
              {[
                { key: "followups", label: "待完成", count: allPendingItems.length, activeColor: COLOR.warning },
                { key: "sent", label: "已完成", count: recentlySent.length, activeColor: COLOR.text4 },
              ].map((tab, i, arr) => {
                const active = filter === tab.key;
                return (
                  <Box key={tab.key} sx={{ display: "contents" }}>
                    <Box
                      onClick={() => handleFilter(tab.key)}
                      sx={{
                        flex: 1, textAlign: "center",
                        py: 1.2, cursor: "pointer", userSelect: "none",
                        borderBottom: active ? `2px solid ${tab.activeColor}` : "2px solid transparent",
                        transition: "border-color 0.15s ease",
                        "&:active": { opacity: 0.5 },
                      }}
                    >
                      <Typography sx={{
                        fontSize: TYPE.title.fontSize, fontWeight: 600,
                        color: active ? tab.activeColor : COLOR.text4,
                        transition: "color 0.15s ease",
                      }}>
                        {tab.count}
                      </Typography>
                      <Typography sx={{
                        fontSize: TYPE.micro.fontSize, mt: "2px",
                        color: active ? COLOR.text2 : COLOR.text4,
                        fontWeight: active ? 500 : 400,
                      }}>
                        {tab.label}
                      </Typography>
                    </Box>
                    {i < arr.length - 1 && (
                      <Box sx={{ width: "0.5px", bgcolor: COLOR.borderLight, my: 0.8 }} />
                    )}
                  </Box>
                );
              })}
            </Box>

            {/* ── Section: 待完成 (merged followups + tasks, sorted by due date) ── */}
            {showFollowups && allPendingItems.length > 0 && (
              <>
                <SectionLabel>待完成</SectionLabel>
                <Box sx={{ bgcolor: COLOR.white, borderTop: `0.5px solid ${COLOR.border}`, borderBottom: `0.5px solid ${COLOR.border}` }}>
                  {allPendingItems.map((item) => (
                    <ActionRow
                      key={`${item._isFollowup ? "f" : "t"}-${item.id}`}
                      title={item._isFollowup ? `${item.patient_name} · ${item.task}` : (item.title || "任务")}
                      subtitle={item._isFollowup ? item.detail : item.content}
                      right={item._isFollowup ? (item.due_label || "") : (item.due_at ? item.due_at.slice(0, 10) : "")}
                      urgent={item.soon}
                      onClick={() => item.patient_id ? navigate(`/doctor/patients/${item.patient_id}`) : undefined}
                      onToggle={() => handleCompleteTask(item)}
                    />
                  ))}
                </Box>
              </>
            )}

            {/* ── Section: 已完成 ── */}
            {showSent && recentlySent.length > 0 && (
              <>
                <SectionLabel>已完成</SectionLabel>
                <Box sx={{ bgcolor: COLOR.white, borderTop: `0.5px solid ${COLOR.border}`, borderBottom: `0.5px solid ${COLOR.border}` }}>
                  {recentlySent.map((s) => (
                    <ActionRow
                      key={s.id}
                      title={`${s.patient_name} · ${s.task}`}
                      subtitle={s.read_status || "已完成"}
                      right={s.time}
                      done
                      onClick={() => s.patient_id ? navigate(`/doctor/patients/${s.patient_id}`) : undefined}
                      onToggle={() => handleUncompleteTask(s)}
                    />
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

      {/* Send confirmation sheet */}
      <SendConfirmSheet
        open={!!confirmItem}
        onClose={() => !sending && setConfirmItem(null)}
        item={confirmItem}
        onConfirm={handleConfirmSend}
        sending={sending}
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
    </Box>
  );
}
