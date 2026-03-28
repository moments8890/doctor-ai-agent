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
import { useApi } from "../../api/ApiContext";
import { useAppNavigate } from "../../hooks/useAppNavigate";
import PatientAvatar from "../../components/PatientAvatar";
import SectionLabel from "../../components/SectionLabel";
import SubpageHeader from "../../components/SubpageHeader";
import { TYPE, COLOR } from "../../theme";

/* ── Section label map ────────────────────────────────────────────────────── */

const SECTION_LABEL = {
  differential: "鉴别诊断",
  workup: "检查建议",
  treatment: "治疗方向",
};

/* ── Summary bar ──────────────────────────────────────────────────────────── */

function StatColumn({ value, label, color }) {
  return (
    <Box sx={{ flex: 1, textAlign: "center", py: 1.25 }}>
      <Typography sx={{ fontSize: TYPE.title.fontSize, fontWeight: 600, color: color || COLOR.text1 }}>
        {value ?? 0}
      </Typography>
      <Typography sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.text4, mt: 0.25 }}>
        {label}
      </Typography>
    </Box>
  );
}

function SummaryBar({ summary }) {
  return (
    <Box sx={{
      display: "flex",
      bgcolor: COLOR.white,
      borderBottom: `0.5px solid ${COLOR.border}`,
      borderTop: `0.5px solid ${COLOR.border}`,
    }}>
      <StatColumn value={summary.pending} label="待审核" color={COLOR.warning} />
      <Box sx={{ width: "0.5px", bgcolor: COLOR.borderLight, my: 1 }} />
      <StatColumn value={summary.confirmed} label="已确认" />
      <Box sx={{ width: "0.5px", bgcolor: COLOR.borderLight, my: 1 }} />
      <StatColumn value={summary.modified} label="已修改" />
    </Box>
  );
}

/* ── Pending review item card ─────────────────────────────────────────────── */

function PendingReviewCard({ item, onConfirm, onReject, onEdit, onNavigate }) {
  const hasCitation = !!item.rule_cited;
  const borderLeft = hasCitation
    ? `3px solid ${COLOR.primary}`
    : `3px dashed ${COLOR.border}`;

  const urgencyLabel = item.urgency === "urgent" ? "紧急" : "待处理";
  const urgencyColor = item.urgency === "urgent" ? COLOR.danger : COLOR.warning;

  return (
    <Box sx={{
      borderLeft,
      borderBottom: `0.5px solid ${COLOR.borderLight}`,
      bgcolor: COLOR.white,
      "&:last-child": { borderBottom: "none" },
    }}>
      {/* Header: avatar + name + time + urgency */}
      <Box
        onClick={() => onNavigate?.(item)}
        sx={{
          display: "flex", alignItems: "center", gap: 1.25,
          px: 2, pt: 1.5, pb: 0.5,
          cursor: "pointer",
        }}
      >
        <PatientAvatar name={item.patient_name || "?"} size={32} />
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography sx={{ fontSize: TYPE.body.fontSize, fontWeight: 400, color: COLOR.text1 }}>
            {item.patient_name}
          </Typography>
          <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4 }}>
            {item.time}
          </Typography>
        </Box>
        <Box
          component="span"
          sx={{
            fontSize: TYPE.micro.fontSize,
            fontWeight: 500,
            borderRadius: "3px",
            px: 0.6,
            border: `0.5px solid ${urgencyColor}`,
            color: urgencyColor,
            lineHeight: 1.6,
            flexShrink: 0,
          }}
        >
          {urgencyLabel}
        </Box>
      </Box>

      {/* Diagnosis preview gray card */}
      <Box
        onClick={() => onNavigate?.(item)}
        sx={{
          mx: 2, mt: 0.75, mb: 0.75,
          px: 1.5, py: 1,
          bgcolor: COLOR.surface,
          borderRadius: "6px",
          cursor: "pointer",
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

      {/* Action row */}
      <Box sx={{ display: "flex", justifyContent: "flex-end", gap: 2, px: 2, pb: 1.25 }}>
        <Typography
          component="span"
          onClick={(e) => { e.stopPropagation(); onReject?.(item); }}
          sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.danger, cursor: "pointer", "&:active": { opacity: 0.5 } }}
        >
          ✗ 排除
        </Typography>
        <Typography
          component="span"
          onClick={(e) => { e.stopPropagation(); onEdit?.(item); }}
          sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.accent, cursor: "pointer", "&:active": { opacity: 0.5 } }}
        >
          ✎ 修改
        </Typography>
        <Typography
          component="span"
          onClick={(e) => { e.stopPropagation(); onConfirm?.(item); }}
          sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.primary, cursor: "pointer", fontWeight: 500, "&:active": { opacity: 0.5 } }}
        >
          ✓ 确认
        </Typography>
      </Box>
    </Box>
  );
}

/* ── Completed row ────────────────────────────────────────────────────────── */

function CompletedRow({ item }) {
  const isEdited = item.decision === "edited";
  const checkColor = isEdited ? COLOR.warning : COLOR.primary;
  const checkIcon = isEdited ? "✎" : "✓";

  const detailText = (() => {
    if (isEdited && item.detail) return `已修改 · ${item.detail}`;
    if (item.rule_count > 0) return `已确认 · 引用了你的 ${item.rule_count} 条规则`;
    return "已确认";
  })();

  return (
    <Box sx={{
      display: "flex", alignItems: "center", gap: 1.25,
      px: 2, py: 1.25,
      borderBottom: `0.5px solid ${COLOR.borderLight}`,
      "&:last-child": { borderBottom: "none" },
    }}>
      <Typography sx={{ fontSize: TYPE.body.fontSize, color: checkColor, flexShrink: 0 }}>
        {checkIcon}
      </Typography>
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Typography sx={{ fontSize: TYPE.body.fontSize, color: COLOR.text4 }}>
          {item.patient_name} · {item.content}
        </Typography>
        <Typography sx={{ fontSize: TYPE.caption.fontSize, color: "#ccc", mt: 0.15 }}>
          {detailText}
        </Typography>
      </Box>
      <Typography sx={{ fontSize: TYPE.micro.fontSize, color: "#ccc", flexShrink: 0 }}>
        {item.time}
      </Typography>
    </Box>
  );
}

/* ── Empty state ──────────────────────────────────────────────────────────── */

function EmptyState() {
  return (
    <Box sx={{ display: "flex", flexDirection: "column", alignItems: "center", py: 5, gap: 0.5 }}>
      <Typography sx={{ fontSize: TYPE.body.fontSize, color: COLOR.text4 }}>暂无待审核项</Typography>
      <Typography sx={{ fontSize: TYPE.caption.fontSize, color: "#ccc" }}>
        新的诊断建议会自动出现在这里
      </Typography>
    </Box>
  );
}

/* ── Main ─────────────────────────────────────────────────────────────────── */

export default function ReviewQueuePage({ doctorId }) {
  const navigate = useAppNavigate();
  const { getReviewQueue, decideSuggestion } = useApi();
  const [queue, setQueue] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    if (!doctorId) return;
    setLoading(true);
    try {
      const data = typeof getReviewQueue === "function"
        ? await getReviewQueue(doctorId)
        : { summary: { pending: 0, confirmed: 0, modified: 0 }, pending: [], completed: [] };
      setQueue(data);
    } catch {
      setQueue({ summary: { pending: 0, confirmed: 0, modified: 0 }, pending: [], completed: [] });
    } finally {
      setLoading(false);
    }
  }, [doctorId, getReviewQueue]);

  useEffect(() => { load(); }, [load]);

  /* ── Inline actions ─────────────────────────────────────────────────────── */

  async function handleConfirm(item) {
    if (!item.suggestion_id) {
      // No suggestion_id — navigate to full review page
      navigate(`/doctor/review/${item.record_id}`);
      return;
    }
    try {
      if (typeof decideSuggestion === "function") {
        await decideSuggestion(item.suggestion_id, "confirmed", {});
      }
      // Optimistic update: remove from pending, bump confirmed count
      setQueue((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          summary: {
            ...prev.summary,
            pending: Math.max(0, prev.summary.pending - 1),
            confirmed: prev.summary.confirmed + 1,
          },
          pending: prev.pending.filter((p) => p.id !== item.id),
          completed: [
            { id: item.id, patient_name: item.patient_name, content: item.content, decision: "confirmed", rule_count: item.rule_cited ? 1 : 0, time: "刚刚" },
            ...(prev.completed || []),
          ],
        };
      });
    } catch {
      // On failure, navigate to full review page
      navigate(`/doctor/review/${item.record_id}`);
    }
  }

  async function handleReject(item) {
    if (!item.suggestion_id) {
      navigate(`/doctor/review/${item.record_id}`);
      return;
    }
    try {
      if (typeof decideSuggestion === "function") {
        await decideSuggestion(item.suggestion_id, "rejected", {});
      }
      setQueue((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          summary: {
            ...prev.summary,
            pending: Math.max(0, prev.summary.pending - 1),
          },
          pending: prev.pending.filter((p) => p.id !== item.id),
        };
      });
    } catch {
      navigate(`/doctor/review/${item.record_id}`);
    }
  }

  function handleEdit(item) {
    // Edit requires the full review page for the inline editor
    navigate(`/doctor/review/${item.record_id}`);
  }

  function handleNavigate(item) {
    navigate(`/doctor/review/${item.record_id}`);
  }

  /* ── Render ─────────────────────────────────────────────────────────────── */

  const summary = queue?.summary || { pending: 0, confirmed: 0, modified: 0 };
  const pending = queue?.pending || [];
  const completed = queue?.completed || [];

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%", bgcolor: COLOR.surfaceAlt }}>
      <SubpageHeader title="审核" />

      <Box sx={{ flex: 1, overflow: "auto" }}>
        {/* Summary bar */}
        <SummaryBar summary={summary} />

        {/* Loading */}
        {loading && (
          <Box sx={{ p: 3, textAlign: "center" }}>
            <CircularProgress size={20} />
          </Box>
        )}

        {/* Pending items */}
        {!loading && pending.length > 0 && (
          <>
            <SectionLabel>待审核 · {pending.length}条</SectionLabel>
            <Box sx={{
              bgcolor: COLOR.white,
              borderTop: `0.5px solid ${COLOR.border}`,
              borderBottom: `0.5px solid ${COLOR.border}`,
            }}>
              {pending.map((item) => (
                <PendingReviewCard
                  key={item.id}
                  item={item}
                  onConfirm={handleConfirm}
                  onReject={handleReject}
                  onEdit={handleEdit}
                  onNavigate={handleNavigate}
                />
              ))}
            </Box>
          </>
        )}

        {/* Empty state */}
        {!loading && pending.length === 0 && <EmptyState />}

        {/* Recently completed */}
        {!loading && completed.length > 0 && (
          <>
            <SectionLabel>最近已审核</SectionLabel>
            <Box sx={{
              bgcolor: COLOR.white,
              borderTop: `0.5px solid ${COLOR.border}`,
              borderBottom: `0.5px solid ${COLOR.border}`,
            }}>
              {completed.map((item) => (
                <CompletedRow key={item.id} item={item} />
              ))}
            </Box>
          </>
        )}

        {/* Bottom disclaimer */}
        <Box sx={{ py: 2, textAlign: "center" }}>
          <Typography sx={{ fontSize: 10, color: "#c0c0c0" }}>
            AI建议仅供参考，请结合临床判断
          </Typography>
        </Box>
      </Box>
    </Box>
  );
}
