/**
 * @route /doctor/followup
 *
 * FollowupPage -- "随访" tab. Shows AI-drafted follow-up messages
 * for the doctor to review, edit, and send. Three sections:
 *   1. 患者消息 · 待回复  (pending messages with AI drafts)
 *   2. 即将到期的随访     (upcoming scheduled follow-ups)
 *   3. 最近已发送         (recently sent messages)
 */
import { useEffect, useState, useCallback } from "react";
import { Box, CircularProgress, Typography } from "@mui/material";
import { useApi } from "../../api/ApiContext";
import SubpageHeader from "../../components/SubpageHeader";
import PatientAvatar from "../../components/PatientAvatar";
import SectionLabel from "../../components/SectionLabel";
import StatusBadge from "../../components/StatusBadge";
import AppButton from "../../components/AppButton";
import SheetDialog from "../../components/SheetDialog";
import { TYPE, COLOR } from "../../theme";

// ── Badge color mapping ──
const BADGE_COLOR_MAP = {
  "新消息": COLOR.warning,
  "紧急": COLOR.danger,
};
const BADGE_LABEL = { new: "新消息", urgent: "紧急" };

// ── Summary stat component ──
function SummaryStat({ value, label, color }) {
  return (
    <Box sx={{ flex: 1, textAlign: "center" }}>
      <Typography sx={{ fontSize: TYPE.title.fontSize, fontWeight: 600, color: color || COLOR.text1 }}>
        {value}
      </Typography>
      <Typography sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.text4, mt: "2px" }}>
        {label}
      </Typography>
    </Box>
  );
}

// ── Pending message item ──
function MessageItem({ item, onSend, onEdit }) {
  const [editing, setEditing] = useState(false);
  const [editText, setEditText] = useState(item.draft_text || "");
  const [saving, setSaving] = useState(false);
  const api = useApi();

  const badgeLabel = BADGE_LABEL[item.badge];

  const handleStartEdit = () => {
    setEditText(item.draft_text || "");
    setEditing(true);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await (api.editDraft || (() => Promise.resolve()))(item.id, null, editText);
      item.draft_text = editText;
      setEditing(false);
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
              <Box
                component="textarea"
                value={editText}
                onChange={(e) => setEditText(e.target.value)}
                sx={{
                  width: "100%",
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
  return (
    <Box sx={{
      display: "flex", alignItems: "center", gap: 1.2,
      px: 2, py: 1.2,
      borderBottom: `0.5px solid ${COLOR.borderLight}`,
      "&:last-child": { borderBottom: "none" },
    }}>
      <Typography sx={{ fontSize: TYPE.body.fontSize, color: COLOR.text4, flexShrink: 0 }}>◷</Typography>
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

// ── Recently sent row ──
function SentRow({ item }) {
  return (
    <Box sx={{
      display: "flex", alignItems: "center", gap: 1.2,
      px: 2, py: 1.2,
      borderBottom: `0.5px solid ${COLOR.borderLight}`,
      "&:last-child": { borderBottom: "none" },
    }}>
      <Typography sx={{ fontSize: TYPE.body.fontSize, color: COLOR.primary, flexShrink: 0 }}>✓</Typography>
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
export default function FollowupPage({ doctorId }) {
  const api = useApi();
  const [data, setData] = useState(null);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Send confirmation sheet state
  const [confirmItem, setConfirmItem] = useState(null);
  const [sending, setSending] = useState(false);

  const loadData = useCallback(async () => {
    if (!doctorId) return;
    setLoading(true);
    setError(null);
    try {
      const [draftsRes, summaryRes] = await Promise.all([
        (api.fetchDrafts || (() => Promise.resolve({})))(doctorId),
        (api.fetchDraftSummary || (() => Promise.resolve({})))(doctorId),
      ]);
      // Handle both old flat array format and new structured format
      if (Array.isArray(draftsRes)) {
        setData({ pending_messages: draftsRes, upcoming_followups: [], recently_sent: [] });
      } else {
        setData(draftsRes || {});
      }
      setSummary(summaryRes || {});
    } catch (err) {
      setError(err.message || "加载失败");
    } finally {
      setLoading(false);
    }
  }, [doctorId, api]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const pendingMessages = data?.pending_messages || [];
  const upcomingFollowups = data?.upcoming_followups || [];
  const recentlySent = data?.recently_sent || [];

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

  const isEmpty = !loading && !error && pendingMessages.length === 0 && upcomingFollowups.length === 0 && recentlySent.length === 0;

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%", bgcolor: COLOR.surfaceAlt }}>
      <SubpageHeader title="随访" />
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
          <Box sx={{ py: 6, textAlign: "center" }}>
            <Typography sx={{ fontSize: TYPE.title.fontSize, color: COLOR.text3, mb: 0.5 }}>
              暂无随访消息
            </Typography>
            <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text4 }}>
              AI会在需要随访时自动起草消息
            </Typography>
          </Box>
        )}

        {/* Content */}
        {!loading && !error && !isEmpty && (
          <>
            {/* ── Summary bar ── */}
            <Box sx={{
              display: "flex",
              px: 2, py: 1.5,
              bgcolor: COLOR.white,
              borderBottom: `0.5px solid ${COLOR.border}`,
              borderTop: `0.5px solid ${COLOR.border}`,
            }}>
              <SummaryStat value={summary?.pending_reply ?? pendingMessages.length} label="待回复" color={COLOR.danger} />
              <Box sx={{ width: "0.5px", bgcolor: COLOR.borderLight, my: 0.5 }} />
              <SummaryStat value={summary?.ai_drafted ?? 0} label="AI已起草" color={COLOR.warning} />
              <Box sx={{ width: "0.5px", bgcolor: COLOR.borderLight, my: 0.5 }} />
              <SummaryStat value={summary?.upcoming ?? upcomingFollowups.length} label="即将到期" />
            </Box>

            {/* ── Section: 患者消息 · 待回复 ── */}
            {pendingMessages.length > 0 && (
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
                    />
                  ))}
                </Box>
              </>
            )}

            {/* ── Section: 即将到期的随访 ── */}
            {upcomingFollowups.length > 0 && (
              <>
                <SectionLabel>即将到期的随访</SectionLabel>
                <Box sx={{
                  bgcolor: COLOR.white,
                  borderTop: `0.5px solid ${COLOR.border}`,
                  borderBottom: `0.5px solid ${COLOR.border}`,
                }}>
                  {upcomingFollowups.map((f) => (
                    <ScheduledRow key={f.id} item={f} />
                  ))}
                </Box>
              </>
            )}

            {/* ── Section: 最近已发送 ── */}
            {recentlySent.length > 0 && (
              <>
                <SectionLabel>最近已发送</SectionLabel>
                <Box sx={{
                  bgcolor: COLOR.white,
                  borderTop: `0.5px solid ${COLOR.border}`,
                  borderBottom: `0.5px solid ${COLOR.border}`,
                }}>
                  {recentlySent.map((s) => (
                    <SentRow key={s.id} item={s} />
                  ))}
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
    </Box>
  );
}
