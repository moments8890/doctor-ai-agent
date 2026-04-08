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
import { useQueryClient } from "@tanstack/react-query";
import { useReviewQueue, useDrafts } from "../../lib/doctorQueries";
import { QK } from "../../lib/queryKeys";
import { Box, Typography } from "@mui/material";
import AssignmentOutlinedIcon from "@mui/icons-material/AssignmentOutlined";
import MailOutlineIcon from "@mui/icons-material/MailOutline";
import { useApi } from "../../api/ApiContext";
import { useAppNavigate } from "../../hooks/useAppNavigate";
import EmptyState from "../../components/EmptyState";
import SectionLoading from "../../components/SectionLoading";
import PullToRefresh from "../../components/PullToRefresh";
import NameAvatar from "../../components/NameAvatar";
import SectionLabel from "../../components/SectionLabel";
import ActionRow from "../../components/ActionRow";
import SubpageHeader from "../../components/SubpageHeader";
import FilterBar from "../../components/FilterBar";
import CitationPopover from "../../components/CitationPopover";
import { TYPE, COLOR, RADIUS, HIGHLIGHT_ROW_SX } from "../../theme";
import { dp } from "../../utils/doctorBasePath";
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

/* ── Pending review item card ─────────────────────────────────────────────── */

function PendingReviewCard({ item, onNavigate }) {
  const [citationAnchor, setCitationAnchor] = useState(null);
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
          display: "flex", alignItems: "center", gap: 1, mb: 1,
          cursor: "pointer",
        }}
      >
        <NameAvatar name={item.patient_name || "?"} size={36} />
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
            <Typography sx={{ fontSize: TYPE.action.fontSize, fontWeight: 500, color: COLOR.text1 }}>
              {item.patient_name}
            </Typography>
            <Box
              component="span"
              sx={{
                fontSize: 10, fontWeight: 600,
                borderRadius: RADIUS.sm, px: 0.5, py: 0.5,
                bgcolor: urgencyColor, color: COLOR.white,
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
          borderRadius: RADIUS.md,
          cursor: "pointer",
          mb: 1,
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
      <Box sx={{ px: 2, mb: 1 }}>
        {hasCitation ? (
          <>
            <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text4 }}>
              引用了你的规则：
              <Box component="span"
                onClick={(e) => { e.stopPropagation(); setCitationAnchor(e.currentTarget); }}
                sx={{ color: COLOR.primary, fontWeight: 500, cursor: "pointer", "&:active": { opacity: 0.6 } }}>
                {item.rule_cited}
              </Box>
            </Typography>
            <CitationPopover
              anchorEl={citationAnchor}
              open={Boolean(citationAnchor)}
              onClose={() => setCitationAnchor(null)}
              rule={{ title: item.rule_cited, summary: item.detail || "", reference_count: item.rule_count }}
              onViewFull={() => {}}
            />
          </>
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
          mx: 2, mb: 1,
          bgcolor: COLOR.primaryLight, borderRadius: RADIUS.md,
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
  const queryClient = useQueryClient();
  const params = new URLSearchParams(window.location.search);
  const highlightDraftId = params.get("highlight_draft") || "";

  const { data: queueData, isLoading: qLoading, refetch: refetchQueue } = useReviewQueue();
  const { data: draftsData, isLoading: dLoading, refetch: refetchDrafts } = useDrafts({ includeSent: true });

  const loading = qLoading || dLoading;
  const queue = queueData || { pending: [], completed: [] };
  const drafts = Array.isArray(draftsData) ? draftsData : (draftsData?.pending_messages || []);

  const load = useCallback(() => {
    refetchQueue();
    refetchDrafts();
  }, [refetchQueue, refetchDrafts]);

  function handleNavigate(item) {
    navigate(`${dp("review")}/${item.record_id}`);
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

      <PullToRefresh sx={{ flex: 1 }}>
        {/* Filter stat bar */}
        <FilterBar
          items={[
            { key: "pending", label: "待审核", activeColor: COLOR.warning },
            { key: "replies", label: "待回复", activeColor: COLOR.danger },
            { key: "completed", label: "已完成", activeColor: COLOR.primary },
          ]}
          active={filter}
          counts={summary}
          onChange={handleFilter}
          dividers
        />

        {/* Loading */}
        {loading && (
          <SectionLoading />
        )}

        {/* Pending items — 3-line enriched rows */}
        {!loading && showPending && pending.length > 0 && (
          <>
            <SectionLabel>待审核</SectionLabel>
            <Box sx={{ bgcolor: COLOR.white, borderTop: `0.5px solid ${COLOR.border}`, borderBottom: `0.5px solid ${COLOR.border}` }}>
              {pending.map((item) => {
                const chiefComplaint = item.chief_complaint || "";
                const sourceLabel = item.record_type === "interview_summary" ? "预问诊" : item.record_type === "import" ? "导入" : "门诊记录";
                const fieldCount = item.field_count;
                const aiSummary = item.detail ? `AI：${item.content || (SECTION_LABEL[item.section] || "")}` : "";
                return (
                  <Box key={item.id} onClick={() => handleNavigate(item)}
                    sx={{
                      display: "flex", alignItems: "flex-start", gap: 1.5, px: 2, py: 1.5, cursor: "pointer",
                      borderBottom: `0.5px solid ${COLOR.borderLight}`, "&:last-child": { borderBottom: "none" },
                      ...(item.urgency === "urgent" ? { bgcolor: COLOR.warningLight } : {}),
                      "&:active": { opacity: 0.8 },
                    }}>
                    <NameAvatar name={item.patient_name || "?"} size={36} />
                    <Box sx={{ flex: 1, minWidth: 0 }}>
                      <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                        <Typography sx={{ fontSize: TYPE.action.fontSize, fontWeight: 500 }}>{item.patient_name}</Typography>
                        {item.age && <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4 }}>{item.age}岁</Typography>}
                        {item.urgency === "urgent" && <Box component="span" sx={{ fontSize: 10, fontWeight: 600, bgcolor: COLOR.danger, color: COLOR.white, borderRadius: RADIUS.sm, px: 0.5, py: 0.5, lineHeight: 1.5 }}>紧急</Box>}
                        {item.urgency !== "urgent" && <Box component="span" sx={{ fontSize: 10, fontWeight: 600, bgcolor: COLOR.warning, color: COLOR.white, borderRadius: RADIUS.sm, px: 0.5, py: 0.5, lineHeight: 1.5 }}>待处理</Box>}
                      </Box>
                      {chiefComplaint && (
                        <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text2, mt: 0.5, lineHeight: 1.5, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                          主诉：{chiefComplaint}
                        </Typography>
                      )}
                      <Box sx={{ display: "flex", alignItems: "center", gap: 0.5, mt: 0.5, fontSize: TYPE.micro.fontSize, color: COLOR.text4, flexWrap: "wrap" }}>
                        <Typography sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.accent, fontWeight: 500 }}>{sourceLabel}</Typography>
                        {fieldCount && <><Typography sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.text4 }}>·</Typography><Typography sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.text4 }}>{fieldCount}</Typography></>}
                        {aiSummary && <><Typography sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.text4 }}>·</Typography><Typography sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.warning, fontWeight: 500 }}>{aiSummary}</Typography></>}
                      </Box>
                    </Box>
                    <Box sx={{ flexShrink: 0, textAlign: "right" }}>
                      <Typography sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.text4 }}>{item.time}</Typography>
                      <Typography sx={{ fontSize: 14, color: COLOR.text4, mt: 0.5 }}>›</Typography>
                    </Box>
                  </Box>
                );
              })}
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

        {/* ── Section: 待回复 — simple rows, tap navigates to patient chat subpage ── */}
        {!loading && showReplies && activeDrafts.length > 0 && (
          <>
            <SectionLabel>患者消息 · 待回复</SectionLabel>
            <Box sx={{ bgcolor: COLOR.white, borderTop: `0.5px solid ${COLOR.border}`, borderBottom: `0.5px solid ${COLOR.border}` }}>
              {activeDrafts.map((msg) => {
                const triageLabel = msg.badge === "urgent" ? "需紧急处理" : "常规咨询";
                const citedRule = msg.rule_cited || (msg.cited_rules?.[0]?.title) || "";
                return (
                  <Box key={msg.id}
                    onClick={() => navigate(`${dp("patients")}/${msg.patient_id}?view=chat`, { replace: false })}
                    sx={{
                      display: "flex", alignItems: "flex-start", gap: 1.5, px: 2, py: 1.5, cursor: "pointer",
                      borderBottom: `0.5px solid ${COLOR.borderLight}`, "&:last-child": { borderBottom: "none" },
                      ...(String(msg.id) === highlightDraftId ? HIGHLIGHT_ROW_SX : {}),
                      "&:active": { opacity: 0.8 },
                    }}>
                    <NameAvatar name={msg.patient_name || "?"} size={36} />
                    <Box sx={{ flex: 1, minWidth: 0 }}>
                      <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                        <Typography sx={{ fontSize: TYPE.action.fontSize, fontWeight: 500 }}>{msg.patient_name}</Typography>
                        {(msg.pending_count || 1) > 1 && <Box component="span" sx={{ fontSize: 10, fontWeight: 600, bgcolor: COLOR.accent, color: COLOR.white, borderRadius: RADIUS.round, minWidth: 18, height: 18, display: "inline-flex", alignItems: "center", justifyContent: "center", lineHeight: 1 }}>{msg.pending_count}</Box>}
                        {msg.badge === "urgent" && <Box component="span" sx={{ fontSize: 10, fontWeight: 600, bgcolor: COLOR.danger, color: COLOR.white, borderRadius: RADIUS.sm, px: 0.5, py: 0.5, lineHeight: 1.5 }}>紧急</Box>}
                      </Box>
                      <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text2, mt: 0.5, lineHeight: 1.5, overflow: "hidden", display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical" }}>
                        "{msg.patient_message || msg.content || ""}"
                      </Typography>
                      <Box sx={{ display: "flex", alignItems: "center", gap: 0.5, mt: 0.5, fontSize: TYPE.micro.fontSize, color: COLOR.text4 }}>
                        <Typography sx={{ fontSize: TYPE.micro.fontSize, color: msg.type === "undrafted" ? COLOR.text3 : COLOR.primary, fontWeight: 500 }}>{msg.type === "undrafted" ? "需手动回复" : "AI已起草"}</Typography>
                        <Typography sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.text4 }}>·</Typography>
                        <Typography sx={{ fontSize: TYPE.micro.fontSize, color: msg.badge === "urgent" ? COLOR.danger : COLOR.text4 }}>{triageLabel}</Typography>
                        {citedRule && <><Typography sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.text4 }}>·</Typography><Typography sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.text4 }}>引用: {citedRule}</Typography></>}
                      </Box>
                    </Box>
                    <Box sx={{ flexShrink: 0, textAlign: "right" }}>
                      <Typography sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.text4 }}>{msg.time || ""}</Typography>
                      <Typography sx={{ fontSize: 14, color: COLOR.text4, mt: 0.5 }}>›</Typography>
                    </Box>
                  </Box>
                );
              })}
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
                    navigate(`${dp("patients")}/${item.patient_id}?view=chat`);
                  } else if (item.patient_id) {
                    const params = item.record_id ? `?view=record&record=${item.record_id}` : "";
                    navigate(`${dp("patients")}/${item.patient_id}${params}`);
                  } else if (item.record_id) {
                    navigate(`${dp("review")}/${item.record_id}`);
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
          <Typography sx={{ fontSize: 10, color: COLOR.text4 }}>
            AI建议仅供参考，请结合临床判断
          </Typography>
        </Box>
      </PullToRefresh>

    </Box>
  );
}
