/**
 * @route /doctor/review
 *
 * ReviewQueuePage — queue-style overview of all pending AI diagnosis suggestions.
 *
 * Shows:
 *  - Summary stats bar (pending / confirmed / modified)
 *  - Pending review items with diagnosis preview, citation, inline actions
 *  - Recently completed section (greyed-out)
 *
 * Tapping a pending item can either act inline (confirm/reject/edit) or
 * navigate to the full ReviewPage for that record.
 */
import { useCallback, useEffect, useState } from "react";
import { Box, CircularProgress, Typography } from "@mui/material";
import AssignmentOutlinedIcon from "@mui/icons-material/AssignmentOutlined";
import ChevronRightOutlinedIcon from "@mui/icons-material/ChevronRightOutlined";
import MailOutlineIcon from "@mui/icons-material/MailOutline";
import { useApi } from "../../api/ApiContext";
import { useAppNavigate } from "../../hooks/useAppNavigate";
import EmptyState from "../../components/EmptyState";
import PatientAvatar from "../../components/PatientAvatar";
import SectionLabel from "../../components/SectionLabel";
import ActionRow from "../../components/ActionRow";
import SubpageHeader from "../../components/SubpageHeader";
import SheetDialog from "../../components/SheetDialog";
import AppButton from "../../components/AppButton";
import ReplyCard from "../../components/doctor/ReplyCard";
import { TYPE, COLOR } from "../../theme";

/* ── Case memory helpers ──────────────────────────────────────────────────── */

function extractCaseText(detail) {
  if (!detail) return "";
  // Find text after 【类似病例参考】 or lines containing "相似度"
  const lines = detail.split("\n");
  const caseLines = lines.filter(l => l.includes("相似度") || l.includes("类似病例"));
  if (caseLines.length > 0) return caseLines.join("\n");
  // Fallback: look for numbered case references
  const numbered = lines.filter(l => /^\d+\.\s*相似度/.test(l.trim()));
  return numbered.join("\n") || "";
}

/* ── Section label map ────────────────────────────────────────────────────── */

const SECTION_LABEL = {
  differential: "鉴别诊断",
  workup: "检查建议",
  treatment: "治疗方向",
};

/* ── Summary bar ──────────────────────────────────────────────────────────── */

function FilterStatBar({ summary, filter, onFilter }) {
  const tabs = [
    { key: "pending", label: "门诊", count: summary.pending, activeColor: COLOR.warning },
    { key: "replies", label: "回复", count: summary.replies, activeColor: COLOR.danger },
    { key: "completed", label: "完成", count: summary.completed, activeColor: COLOR.primary },
  ];
  return (
    <Box sx={{
      display: "flex",
      bgcolor: COLOR.white,
      borderBottom: `0.5px solid ${COLOR.border}`,
      borderTop: `0.5px solid ${COLOR.border}`,
    }}>
      {tabs.map((tab, i) => {
        const active = filter === tab.key;
        return (
          <Box key={tab.key} sx={{ display: "contents" }}>
            <Box
              onClick={() => onFilter(tab.key)}
              sx={{
                flex: 1, textAlign: "center", py: 1.25,
                cursor: "pointer", userSelect: "none",
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
                {tab.count ?? 0}
              </Typography>
              <Typography sx={{
                fontSize: TYPE.micro.fontSize, mt: 0.25,
                color: active ? COLOR.text2 : COLOR.text4,
                fontWeight: active ? 500 : 400,
              }}>
                {tab.label}
              </Typography>
            </Box>
            {i < tabs.length - 1 && (
              <Box sx={{ width: "0.5px", bgcolor: COLOR.borderLight, my: 0.8 }} />
            )}
          </Box>
        );
      })}
    </Box>
  );
}

/* ── Pending review item card ─────────────────────────────────────────────── */

function PendingReviewCard({ item, onNavigate }) {
  const hasCitation = !!item.rule_cited;
  const hasCaseMemory = (item.detail || "").includes("相似度") || (item.detail || "").includes("类似病例");

  const urgencyLabel = item.urgency === "urgent" ? "紧急" : "待处理";
  const urgencyColor = item.urgency === "urgent" ? COLOR.danger : COLOR.warning;

  return (
    <Box sx={{
      px: 2, py: 1.5,
      borderBottom: `0.5px solid ${COLOR.borderLight}`,
      bgcolor: COLOR.white,
      "&:last-child": { borderBottom: "none" },
    }}>
      {/* Header: avatar + name + badge + time — same layout as ReplyCard */}
      <Box
        onClick={() => onNavigate?.(item)}
        sx={{
          display: "flex", alignItems: "center", gap: 1.2, mb: 1,
          cursor: "pointer",
        }}
      >
        <PatientAvatar name={item.patient_name || "?"} size={36} />
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 0.8 }}>
            <Typography sx={{ fontSize: TYPE.action.fontSize, fontWeight: 500, color: COLOR.text1 }}>
              {item.patient_name}
            </Typography>
            <Box
              component="span"
              sx={{
                fontSize: 10, fontWeight: 600,
                borderRadius: "3px", px: 0.6, py: 0.1,
                bgcolor: urgencyColor, color: "#fff",
                lineHeight: 1.5,
              }}
            >
              {urgencyLabel}
            </Box>
          </Box>
          <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4, mt: 0.1 }}>
            {item.time}
          </Typography>
        </Box>
        <ChevronRightOutlinedIcon sx={{ fontSize: 18, color: COLOR.text4, flexShrink: 0 }} />
      </Box>

      {/* Diagnosis preview — same card style as ReplyCard's message bubble */}
      <Box
        onClick={() => onNavigate?.(item)}
        sx={{
          px: 1.5, py: 1,
          bgcolor: COLOR.surface,
          borderRadius: "6px",
          cursor: "pointer",
          mb: 0.75,
        }}
      >
        <Typography sx={{ fontSize: TYPE.secondary.fontSize, fontWeight: 400, color: COLOR.text1, mb: 0.5 }}>
          {SECTION_LABEL[item.section] || item.section}：{item.content}
        </Typography>
        <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text3, lineHeight: 1.4, overflow: "hidden", textOverflow: "ellipsis", display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical" }}>
          {item.detail}
        </Typography>
      </Box>

      {/* Citation line */}
      <Box sx={{ px: 2, mb: 0.75 }}>
        {hasCitation ? (
          <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text4 }}>
            引用了你的规则：
            <Box component="span" sx={{ color: COLOR.primary, fontWeight: 500 }}>
              {item.rule_cited}
            </Box>
          </Typography>
        ) : (
          <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
            <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text4 }}>
              未引用个人规则
            </Typography>
            <Box
              component="span"
              onClick={(e) => { e.stopPropagation(); onNavigate?.(item); }}
              sx={{
                fontSize: TYPE.secondary.fontSize,
                color: COLOR.primary,
                cursor: "pointer",
                "&:active": { opacity: 0.6 },
              }}
            >
              教AI一条 ›
            </Box>
          </Box>
        )}
      </Box>

      {/* Case memory card */}
      {hasCaseMemory && (
        <Box sx={{
          mx: 2, mb: 0.75,
          bgcolor: "#f0faf4", borderRadius: "6px",
          padding: "10px 12px",
        }}>
          <Typography sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.primary, fontWeight: 500, mb: 0.5 }}>
            你处理过类似病例
          </Typography>
          <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text2, lineHeight: 1.6 }}>
            {extractCaseText(item.detail)}
          </Typography>
        </Box>
      )}

      {/* Tap anywhere to go to diagnosis page */}
    </Box>
  );
}

/* ── Completed row — uses shared ActionRow ──────────────────────────────── */

function CompletedRow({ item, onClick }) {
  const isEdited = item.decision === "edited";
  const detailText = (() => {
    if (isEdited && item.detail) return `已修改 · ${item.detail}`;
    if (item.rule_count > 0) return `已确认 · 引用了你的 ${item.rule_count} 条规则`;
    return "已确认";
  })();

  return (
    <ActionRow
      title={`${item.patient_name} · ${item.content}`}
      subtitle={detailText}
      right={item.time}
      done
      edited={isEdited}
      onClick={onClick}
    />
  );
}

/* ── Main ─────────────────────────────────────────────────────────────────── */

const REVIEW_TABS = new Set(["pending", "replies", "completed"]);

export default function ReviewQueuePage({ doctorId, urlSubpage }) {
  const navigate = useAppNavigate();
  const api = useApi();
  const { getReviewQueue } = api;
  const [queue, setQueue] = useState(null);
  const [drafts, setDrafts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [confirmItem, setConfirmItem] = useState(null);
  const [sending, setSending] = useState(false);

  const load = useCallback(async () => {
    if (!doctorId) return;
    setLoading(true);
    try {
      const [reviewData, draftsData] = await Promise.all([
        typeof getReviewQueue === "function"
          ? getReviewQueue(doctorId)
          : Promise.resolve({ pending: [], completed: [] }),
        typeof api.fetchDrafts === "function"
          ? api.fetchDrafts(doctorId, { includeSent: true }).catch(() => ({}))
          : Promise.resolve({}),
      ]);
      setQueue(reviewData || { pending: [], completed: [] });
      const msgs = Array.isArray(draftsData) ? draftsData : (draftsData?.pending_messages || []);
      setDrafts(msgs);
    } catch {
      setQueue({ pending: [], completed: [] });
      setDrafts([]);
    } finally {
      setLoading(false);
    }
  }, [doctorId, getReviewQueue, api]);

  useEffect(() => { load(); }, [load]);

  function handleNavigate(item) {
    navigate(`/doctor/review/${item.record_id}`);
  }

  async function handleSendDraft() {
    if (!confirmItem) return;
    setSending(true);
    try {
      await (api.sendDraft || (() => Promise.resolve()))(confirmItem.id, doctorId);
      setDrafts((prev) => prev.filter((m) => m.id !== confirmItem.id));
      setConfirmItem(null);
    } catch {
      // keep dialog open on error
    } finally {
      setSending(false);
    }
  }

  /* ── Render ─────────────────────────────────────────────────────────────── */

  const pending = queue?.pending || [];
  const reviewCompleted = queue?.completed || [];
  // Merge sent drafts into the completed list
  const sentDrafts = drafts.filter(d => d.status === "sent").map(d => ({
    id: `draft_${d.id}`,
    type: "reply",
    patient_name: d.patient_name,
    patient_id: d.patient_id,
    patient_message: d.patient_message,
    draft_text: d.draft_text,
    content: d.patient_message ? d.patient_message.slice(0, 40) : "已回复",
    description: `已回复`,
    created_at: d.created_at,
  }));
  // Also include undrafted items that were handled (doctor replied manually)
  const completed = [...reviewCompleted, ...sentDrafts]
    .sort((a, b) => (b.created_at || "").localeCompare(a.created_at || ""));
  const activeDrafts = drafts.filter(d => d.status !== "sent");
  const summary = { pending: pending.length, replies: activeDrafts.length, completed: completed.length };
  const tabFromUrl = new URLSearchParams(window.location.search).get("tab");
  const initialTab = tabFromUrl && REVIEW_TABS.has(tabFromUrl) ? tabFromUrl : "pending";
  const [filter, setFilter] = useState(initialTab);

  const handleFilter = (key) => {
    const next = filter === key ? "pending" : key;
    setFilter(next);
    const url = new URL(window.location);
    url.searchParams.set("tab", next);
    window.history.replaceState(null, "", url);
  };

  const showPending = filter === "pending";
  const showReplies = filter === "replies";
  const showCompleted = filter === "completed";

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%", bgcolor: COLOR.surfaceAlt }}>
      <SubpageHeader title="审核" />

      <Box sx={{ flex: 1, overflow: "auto" }}>
        {/* Filter stat bar */}
        <FilterStatBar summary={summary} filter={filter} onFilter={handleFilter} />

        {/* Loading */}
        {loading && (
          <Box sx={{ p: 3, textAlign: "center" }}>
            <CircularProgress size={20} />
          </Box>
        )}

        {/* Pending items */}
        {!loading && showPending && pending.length > 0 && (
          <>
            <SectionLabel>待审核</SectionLabel>
            <Box sx={{
              bgcolor: COLOR.white,
              borderTop: `0.5px solid ${COLOR.border}`,
              borderBottom: `0.5px solid ${COLOR.border}`,
            }}>
              {pending.map((item) => (
                <ReplyCard
                  key={item.id}
                  item={{ ...item, section_label: SECTION_LABEL[item.section] || item.section }}
                  mode="diagnosis"
                  onClick={() => handleNavigate(item)}
                />
              ))}
            </Box>
          </>
        )}

        {/* Empty state */}
        {!loading && showPending && pending.length === 0 && (
          <EmptyState
            icon={<AssignmentOutlinedIcon />}
            title="暂无待审核项"
            subtitle="新的诊断建议会自动出现在这里"
          />
        )}

        {/* ── Section: 待回复 (patient messages with AI drafts) ── */}
        {!loading && showReplies && activeDrafts.length > 0 && (
          <>
            <SectionLabel>患者消息 · 待回复</SectionLabel>
            <Box sx={{
              bgcolor: COLOR.white,
              borderTop: `0.5px solid ${COLOR.border}`,
              borderBottom: `0.5px solid ${COLOR.border}`,
            }}>
              {activeDrafts.map((msg) => (
                <ReplyCard
                  key={msg.id}
                  item={msg}
                  mode="pending"
                  doctorId={doctorId}
                  onSent={(item) => setConfirmItem(item)}
                />
              ))}
            </Box>
          </>
        )}

        {!loading && showReplies && activeDrafts.length === 0 && (
          <EmptyState
            icon={<MailOutlineIcon />}
            title="暂无待回复消息"
            subtitle="患者消息会自动出现在这里"
          />
        )}

        {/* Completed items */}
        {!loading && showCompleted && completed.length > 0 && (
          <>
            <SectionLabel>已完成</SectionLabel>
            <Box sx={{
              bgcolor: COLOR.white,
              borderTop: `0.5px solid ${COLOR.border}`,
              borderBottom: `0.5px solid ${COLOR.border}`,
            }}>
              {completed.map((item) => (
                <CompletedRow key={item.id} item={item} onClick={() => {
                  if (item.type === "reply" && item.patient_id) {
                    navigate(`/doctor/patients/${item.patient_id}?expand=messages`);
                  } else if (item.patient_id) {
                    const params = item.record_id ? `?record=${item.record_id}` : "";
                    navigate(`/doctor/patients/${item.patient_id}${params}`);
                  } else if (item.record_id) {
                    navigate(`/doctor/review/${item.record_id}`);
                  }
                }} />
              ))}
            </Box>
          </>
        )}

        {!loading && showCompleted && completed.length === 0 && (
          <EmptyState
            icon={<AssignmentOutlinedIcon />}
            title="暂无已完成项"
          />
        )}

        {/* Bottom disclaimer */}
        <Box sx={{ py: 2, textAlign: "center" }}>
          <Typography sx={{ fontSize: 10, color: "#c0c0c0" }}>
            AI建议仅供参考，请结合临床判断
          </Typography>
        </Box>
      </Box>

      {/* Send confirmation dialog */}
      <SheetDialog
        open={!!confirmItem}
        onClose={() => setConfirmItem(null)}
        title="确认发送"
        desktopMaxWidth={400}
        footer={
          <Box sx={{ display: "flex", gap: 1 }}>
            <AppButton variant="secondary" size="md" sx={{ flex: 1 }} onClick={() => setConfirmItem(null)}>
              取消
            </AppButton>
            <AppButton variant="primary" size="md" sx={{ flex: 1 }} onClick={handleSendDraft} disabled={sending}>
              {sending ? "发送中..." : "发送"}
            </AppButton>
          </Box>
        }
      >
        {confirmItem && (
          <Box>
            <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text3, mb: 1 }}>
              将以下回复发送给 {confirmItem.patient_name}：
            </Typography>
            <Typography sx={{ fontSize: TYPE.body.fontSize, color: COLOR.text1, lineHeight: 1.6, whiteSpace: "pre-line" }}>
              {confirmItem.draft_text}
            </Typography>
          </Box>
        )}
      </SheetDialog>
    </Box>
  );
}
