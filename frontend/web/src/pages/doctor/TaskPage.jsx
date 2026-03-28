/**
 * @route /doctor/followup
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
import AccessTimeOutlinedIcon from "@mui/icons-material/AccessTimeOutlined";
import AssignmentOutlinedIcon from "@mui/icons-material/AssignmentOutlined";
import BiotechOutlinedIcon from "@mui/icons-material/BiotechOutlined";
import CheckOutlinedIcon from "@mui/icons-material/CheckOutlined";
import EventRepeatOutlinedIcon from "@mui/icons-material/EventRepeatOutlined";
import MailOutlineIcon from "@mui/icons-material/MailOutline";
import MedicationOutlinedIcon from "@mui/icons-material/MedicationOutlined";
import MicIcon from "@mui/icons-material/Mic";
import { useApi } from "../../api/ApiContext";
import { useAppNavigate } from "../../hooks/useAppNavigate";
import SubpageHeader from "../../components/SubpageHeader";
import EmptyState from "../../components/EmptyState";
import PatientAvatar from "../../components/PatientAvatar";
import SectionLabel from "../../components/SectionLabel";
import StatusBadge from "../../components/StatusBadge";
import AppButton from "../../components/AppButton";
import SheetDialog from "../../components/SheetDialog";
import VoiceInput, { isVoiceSupported } from "../../components/VoiceInput";
import { TYPE, COLOR } from "../../theme";

// ── Task type icon/color mapping ──
const TASK_TYPE_ICON = {
  follow_up: EventRepeatOutlinedIcon,
  medication: MedicationOutlinedIcon,
  checkup: BiotechOutlinedIcon,
  general: AssignmentOutlinedIcon,
};
const TASK_TYPE_COLOR = {
  follow_up: "#07C160",
  medication: "#5b9bd5",
  checkup: "#e8833a",
  general: "#8e44ad",
};

// ── Badge color mapping ──
const BADGE_COLOR_MAP = {
  "新消息": COLOR.warning,
  "紧急": COLOR.danger,
};
const BADGE_LABEL = { new: "新消息", urgent: "紧急" };

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

// ── Pending message item ──
function MessageItem({ item, onSend, onEdit, onTeachPrompt }) {
  const [editing, setEditing] = useState(false);
  const [editText, setEditText] = useState(item.draft_text || "");
  const [saving, setSaving] = useState(false);
  const [showVoice, setShowVoice] = useState(false);
  const api = useApi();

  const badgeLabel = BADGE_LABEL[item.badge];

  const handleStartEdit = () => {
    setEditText(item.draft_text || "");
    setEditing(true);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const result = await (api.editDraft || (() => Promise.resolve({})))(item.id, null, editText);
      item.draft_text = editText;
      setEditing(false);
      // If backend signals teach_prompt, surface it to the page
      if (result?.teach_prompt && result?.edit_id && onTeachPrompt) {
        onTeachPrompt(result.edit_id);
      }
    } catch {
      // silently fail in mock
    } finally {
      setSaving(false);
    }
  };

  const handleCancel = () => {
    setEditText(item.draft_text || "");
    setEditing(false);
  };

  return (
    <Box sx={{ px: 2, py: 1.5, borderBottom: `0.5px solid ${COLOR.borderLight}`, "&:last-child": { borderBottom: "none" } }}>
      {/* Header: avatar + name + time + badge */}
      <Box sx={{ display: "flex", alignItems: "center", gap: 1.2, mb: 1 }}>
        <PatientAvatar name={item.patient_name} size={32} />
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography sx={{ fontSize: TYPE.body.fontSize, color: COLOR.text1 }}>
            {item.patient_name}
          </Typography>
          <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4 }}>
            {item.time}
          </Typography>
        </Box>
        {badgeLabel && (
          <StatusBadge label={badgeLabel} colorMap={BADGE_COLOR_MAP} sx={{ ml: "auto" }} />
        )}
      </Box>

      {/* Patient message bubble */}
      {item.patient_message && (
        <Box sx={{
          bgcolor: COLOR.surface,
          borderRadius: "6px",
          px: 1.5, py: 1.2, mb: 1,
          fontSize: TYPE.secondary.fontSize,
          color: COLOR.text2,
          lineHeight: 1.5,
        }}>
          {item.patient_message}
        </Box>
      )}

      {/* AI draft card */}
      {item.draft_text && (
        <Box sx={{
          bgcolor: COLOR.white,
          border: `0.5px solid ${COLOR.border}`,
          borderRadius: "6px",
          px: 1.5, py: 1.2, mb: 1,
        }}>
          <Typography sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.primary, fontWeight: 500, mb: 0.5 }}>
            AI按你的话术起草
          </Typography>

          {editing ? (
            <Box>
              <Box sx={{ display: "flex", gap: 0.5, alignItems: "flex-start" }}>
                <Box
                  component="textarea"
                  value={editText}
                  onChange={(e) => setEditText(e.target.value)}
                  sx={{
                    flex: 1,
                    minHeight: 80,
                    border: `1px solid ${COLOR.border}`,
                    borderRadius: "4px",
                    p: 1,
                    fontSize: TYPE.secondary.fontSize,
                    color: COLOR.text2,
                    lineHeight: 1.5,
                    resize: "vertical",
                    fontFamily: "inherit",
                    outline: "none",
                    "&:focus": { borderColor: COLOR.primary },
                  }}
                />
                {isVoiceSupported() && (
                  <Box
                    onClick={() => setShowVoice(!showVoice)}
                    sx={{
                      width: 32, height: 32, borderRadius: "50%",
                      display: "flex", alignItems: "center", justifyContent: "center",
                      cursor: "pointer", flexShrink: 0, mt: 0.5,
                      bgcolor: showVoice ? COLOR.primaryLight : COLOR.surface,
                      "&:active": { opacity: 0.6 },
                    }}
                  >
                    <MicIcon sx={{ fontSize: 18, color: showVoice ? COLOR.primary : COLOR.text4 }} />
                  </Box>
                )}
              </Box>
              {showVoice && (
                <Box sx={{ mt: 0.8 }}>
                  <VoiceInput
                    onResult={(text) => {
                      setEditText((prev) => prev ? prev + text : text);
                      setShowVoice(false);
                    }}
                    onCancel={() => setShowVoice(false)}
                  />
                </Box>
              )}
              <Box sx={{ display: "flex", justifyContent: "flex-end", gap: 1, mt: 0.8 }}>
                <Typography
                  onClick={handleCancel}
                  sx={{
                    fontSize: TYPE.secondary.fontSize, color: COLOR.text4,
                    cursor: "pointer", "&:active": { opacity: 0.5 },
                  }}
                >
                  取消
                </Typography>
                <Typography
                  onClick={!saving ? handleSave : undefined}
                  sx={{
                    fontSize: TYPE.secondary.fontSize, color: COLOR.primary, fontWeight: 500,
                    cursor: saving ? "default" : "pointer",
                    opacity: saving ? 0.5 : 1,
                    "&:active": saving ? {} : { opacity: 0.5 },
                  }}
                >
                  {saving ? "保存中..." : "保存"}
                </Typography>
              </Box>
            </Box>
          ) : (
            <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text2, lineHeight: 1.5 }}>
              {item.draft_text}
            </Typography>
          )}

          {item.rule_cited && !editing && (
            <Typography sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.text4, mt: 0.6 }}>
              引用：<Box component="span" sx={{ color: COLOR.primary }}>{item.rule_cited}</Box>
            </Typography>
          )}
        </Box>
      )}

      {/* Action row */}
      {!editing && (
        <Box sx={{ display: "flex", justifyContent: "flex-end", gap: 2 }}>
          <Typography
            onClick={handleStartEdit}
            sx={{
              fontSize: TYPE.secondary.fontSize, color: COLOR.accent,
              cursor: "pointer", userSelect: "none",
              "&:active": { opacity: 0.5 },
            }}
          >
            ✎ 修改
          </Typography>
          <Typography
            onClick={() => onSend(item)}
            sx={{
              fontSize: TYPE.secondary.fontSize, color: COLOR.primary,
              cursor: "pointer", userSelect: "none",
              "&:active": { opacity: 0.5 },
            }}
          >
            发送 ›
          </Typography>
        </Box>
      )}
    </Box>
  );
}

// ── Scheduled follow-up row ──
function ScheduledRow({ item }) {
  const navigate = useAppNavigate();
  return (
    <Box
      onClick={() => item.patient_id ? navigate(`/doctor/patients/${item.patient_id}`) : undefined}
      sx={{
        display: "flex", alignItems: "center", gap: 1.2,
        px: 2, py: 1.2,
        borderBottom: `0.5px solid ${COLOR.borderLight}`,
        "&:last-child": { borderBottom: "none" },
        cursor: "pointer",
        "&:active": { bgcolor: "#f5f5f5" },
      }}>
      <AccessTimeOutlinedIcon sx={{ fontSize: TYPE.body.fontSize, color: COLOR.text4, flexShrink: 0 }} />
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Typography sx={{ fontSize: TYPE.body.fontSize, color: COLOR.text1 }}>
          {item.patient_name} · {item.task}
        </Typography>
        <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4, mt: "1px" }}>
          {item.detail}
        </Typography>
      </Box>
      <Typography sx={{
        fontSize: TYPE.caption.fontSize,
        color: item.soon ? COLOR.warning : COLOR.text4,
        fontWeight: item.soon ? 500 : 400,
        flexShrink: 0,
      }}>
        {item.due_label}
      </Typography>
    </Box>
  );
}

// ── Task reminder row ──
function TaskRow({ item }) {
  const navigate = useAppNavigate();
  const TaskIcon = TASK_TYPE_ICON[item.task_type] || AssignmentOutlinedIcon;
  const iconColor = TASK_TYPE_COLOR[item.task_type] || "#8e44ad";
  const dueLabel = item.due_at
    ? item.due_at.replace("T", " ").slice(0, 10)
    : "";
  return (
    <Box
      onClick={() => item.patient_id ? navigate(`/doctor/patients/${item.patient_id}`) : undefined}
      sx={{
        display: "flex", alignItems: "center", gap: 1.2,
        px: 2, py: 1.2,
        borderBottom: `0.5px solid ${COLOR.borderLight}`,
        "&:last-child": { borderBottom: "none" },
        cursor: item.patient_id ? "pointer" : "default",
        "&:active": item.patient_id ? { bgcolor: "#f5f5f5" } : {},
      }}>
      <Box sx={{
        width: 28, height: 28, borderRadius: "4px", bgcolor: iconColor,
        display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0,
      }}>
        <TaskIcon sx={{ fontSize: 16, color: "#fff" }} />
      </Box>
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Typography sx={{ fontSize: TYPE.body.fontSize, color: COLOR.text1 }}>
          {item.title || "任务"}
        </Typography>
        {item.content && (
          <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4, mt: "1px" }} noWrap>
            {item.content}
          </Typography>
        )}
      </Box>
      {dueLabel && (
        <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4, flexShrink: 0 }}>
          {dueLabel}
        </Typography>
      )}
    </Box>
  );
}

// ── Recently sent row ──
function SentRow({ item }) {
  const navigate = useAppNavigate();
  return (
    <Box
      onClick={() => item.patient_id ? navigate(`/doctor/patients/${item.patient_id}`) : undefined}
      sx={{
        display: "flex", alignItems: "center", gap: 1.2,
        px: 2, py: 1.2,
        borderBottom: `0.5px solid ${COLOR.borderLight}`,
        "&:last-child": { borderBottom: "none" },
        cursor: "pointer",
        "&:active": { bgcolor: "#f5f5f5" },
      }}>
      <CheckOutlinedIcon sx={{ fontSize: TYPE.body.fontSize, color: COLOR.primary, flexShrink: 0 }} />
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Typography sx={{ fontSize: TYPE.body.fontSize, color: COLOR.text4 }}>
          {item.patient_name} · {item.task}
        </Typography>
        <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4, mt: "1px" }}>
          已发送 · 患者{item.read_status}
        </Typography>
      </Box>
      <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4, flexShrink: 0 }}>
        {item.time}
      </Typography>
    </Box>
  );
}

// ── Send confirmation sheet ──
function SendConfirmSheet({ open, onClose, item, onConfirm, sending }) {
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
      {item.rule_cited && (
        <Box sx={{ mb: 1.5 }}>
          <Typography sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.text4 }}>
            引用规则：
          </Typography>
          <Box sx={{
            display: "inline-block",
            mt: 0.5, px: 1, py: 0.3,
            bgcolor: COLOR.primaryLight,
            borderRadius: "4px",
            fontSize: TYPE.micro.fontSize,
            color: COLOR.primary,
            fontWeight: 500,
          }}>
            {item.rule_cited}
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
export default function TaskPage({ doctorId }) {
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
  const aiDraftedCount = pendingMessages.filter((m) => m.draft_text).length;

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

  const [filter, setFilter] = useState("messages");
  const totalCount = pendingMessages.length + upcomingFollowups.length + pendingTasks.length;
  const isEmpty = !loading && !error && totalCount === 0 && recentlySent.length === 0;

  const handleFilter = (key) => {
    setFilter((prev) => prev === key ? "all" : key);
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

        {/* Empty state */}
        {isEmpty && (
          <EmptyState
            icon={<MailOutlineIcon />}
            title="暂无随访消息"
            subtitle="患者消息会自动出现在这里"
          />
        )}

        {/* Content */}
        {!loading && !error && !isEmpty && (
          <>
            {/* ── Filter stat bar ── */}
            <Box sx={{
              display: "flex",
              bgcolor: COLOR.white,
              borderBottom: `0.5px solid ${COLOR.border}`,
              borderTop: `0.5px solid ${COLOR.border}`,
            }}>
              {[
                { key: "messages", label: "待回复", count: pendingMessages.length, activeColor: COLOR.danger },
                { key: "followups", label: "待完成", count: upcomingFollowups.length + pendingTasks.length, activeColor: COLOR.warning },
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

            {/* ── Section: 患者消息 · 待回复 ── */}
            {showMessages && pendingMessages.length > 0 && (
              <>
                <SectionLabel>患者消息 · 待回复</SectionLabel>
                  <Box sx={{
                    bgcolor: COLOR.white,
                    borderTop: `0.5px solid ${COLOR.border}`,
                    borderBottom: `0.5px solid ${COLOR.border}`,
                  }}>
                    {pendingMessages.map((msg) => (
                      <MessageItem
                        key={msg.id}
                        item={msg}
                        onSend={handleOpenSend}
                        onTeachPrompt={handleTeachPrompt}
                      />
                    ))}
                  </Box>
                  {aiDraftedCount > 0 && filter === "messages" && (
                    <Box sx={{ px: 1.5, py: 0.5 }}>
                      <Typography sx={{ fontSize: 11, color: COLOR.primary }}>
                        其中{aiDraftedCount}条AI已起草回复
                      </Typography>
                    </Box>
                  )}
                </>
            )}

            {/* ── Section: 随访 ── */}
            {showFollowups && upcomingFollowups.length > 0 && (
              <>
                <SectionLabel>随访</SectionLabel>
                <Box sx={{ bgcolor: COLOR.white, borderTop: `0.5px solid ${COLOR.border}`, borderBottom: `0.5px solid ${COLOR.border}` }}>
                  {upcomingFollowups.map((f) => <ScheduledRow key={f.id} item={f} />)}
                </Box>
              </>
            )}

            {/* ── Section: 任务 ── */}
            {showFollowups && pendingTasks.length > 0 && (
              <>
                <SectionLabel>任务</SectionLabel>
                <Box sx={{ bgcolor: COLOR.white, borderTop: `0.5px solid ${COLOR.border}`, borderBottom: `0.5px solid ${COLOR.border}` }}>
                  {pendingTasks.map((t) => <TaskRow key={t.id} item={t} />)}
                </Box>
              </>
            )}

            {/* ── Section: 已完成 ── */}
            {showSent && recentlySent.length > 0 && (
              <>
                <SectionLabel>已完成</SectionLabel>
                <Box sx={{ bgcolor: COLOR.white, borderTop: `0.5px solid ${COLOR.border}`, borderBottom: `0.5px solid ${COLOR.border}` }}>
                  {recentlySent.map((s) => <SentRow key={s.id} item={s} />)}
                </Box>
              </>
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
