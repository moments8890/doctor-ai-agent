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
import EditOutlinedIcon from "@mui/icons-material/EditOutlined";
import CheckOutlinedIcon from "@mui/icons-material/CheckOutlined";
import AssignmentOutlinedIcon from "@mui/icons-material/AssignmentOutlined";
import ChevronRightOutlinedIcon from "@mui/icons-material/ChevronRightOutlined";
import { useApi } from "../../api/ApiContext";
import { useAppNavigate } from "../../hooks/useAppNavigate";
import EmptyState from "../../components/EmptyState";
import PatientAvatar from "../../components/PatientAvatar";
import SectionLabel from "../../components/SectionLabel";
import SubpageHeader from "../../components/SubpageHeader";
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
    { key: "pending", label: "待审核", count: summary.pending, activeColor: COLOR.warning },
    { key: "confirmed", label: "已确认", count: summary.confirmed, activeColor: COLOR.primary },
    { key: "modified", label: "已修改", count: summary.modified, activeColor: COLOR.text1 },
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
        <ChevronRightOutlinedIcon sx={{ fontSize: 18, color: COLOR.text4, flexShrink: 0 }} />
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

/* ── Completed row ────────────────────────────────────────────────────────── */

function CompletedRow({ item, onClick }) {
  const isEdited = item.decision === "edited";
  const checkColor = isEdited ? COLOR.warning : COLOR.primary;
  const CheckIcon = isEdited ? EditOutlinedIcon : CheckOutlinedIcon;

  const detailText = (() => {
    if (isEdited && item.detail) return `已修改 · ${item.detail}`;
    if (item.rule_count > 0) return `已确认 · 引用了你的 ${item.rule_count} 条规则`;
    return "已确认";
  })();

  return (
    <Box
      onClick={onClick}
      sx={{
        display: "flex", alignItems: "center", gap: 1.25,
        px: 2, py: 1.25,
        borderBottom: `0.5px solid ${COLOR.borderLight}`,
        cursor: onClick ? "pointer" : "default",
        "&:active": onClick ? { bgcolor: COLOR.surface } : {},
        "&:last-child": { borderBottom: "none" },
      }}
    >
      <CheckIcon sx={{ fontSize: TYPE.body.fontSize, color: checkColor, flexShrink: 0 }} />
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Typography sx={{ fontSize: TYPE.body.fontSize, color: COLOR.text3 }}>
          {item.patient_name} · {item.content}
        </Typography>
        <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4, mt: 0.15 }}>
          {detailText}
        </Typography>
      </Box>
      <ChevronRightOutlinedIcon sx={{ fontSize: 16, color: COLOR.text4, flexShrink: 0 }} />
    </Box>
  );
}

/* ── Main ─────────────────────────────────────────────────────────────────── */

const REVIEW_TABS = new Set(["pending", "confirmed", "modified"]);

export default function ReviewQueuePage({ doctorId, urlSubpage }) {
  const navigate = useAppNavigate();
  const { getReviewQueue } = useApi();
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

  function handleNavigate(item) {
    navigate(`/doctor/review/${item.record_id}`);
  }

  /* ── Render ─────────────────────────────────────────────────────────────── */

  const pending = queue?.pending || [];
  const completed = queue?.completed || [];
  const confirmedItems = completed.filter((c) => c.decision !== "edited");
  const modifiedItems = completed.filter((c) => c.decision === "edited");
  const summary = { pending: pending.length, confirmed: confirmedItems.length, modified: modifiedItems.length };
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
  const filteredCompleted = filter === "confirmed" ? confirmedItems : filter === "modified" ? modifiedItems : [];

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%", bgcolor: COLOR.surfaceAlt }}>
      <SubpageHeader title="门诊" />

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
                <PendingReviewCard
                  key={item.id}
                  item={item}
                  onNavigate={handleNavigate}
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

        {/* Completed items */}
        {!loading && !showPending && filteredCompleted.length > 0 && (
          <>
            <SectionLabel>{filter === "confirmed" ? "已确认" : "已修改"}</SectionLabel>
            <Box sx={{
              bgcolor: COLOR.white,
              borderTop: `0.5px solid ${COLOR.border}`,
              borderBottom: `0.5px solid ${COLOR.border}`,
            }}>
              {filteredCompleted.map((item) => (
                <CompletedRow key={item.id} item={item} onClick={() => item.record_id ? navigate(`/doctor/review/${item.record_id}`) : undefined} />
              ))}
            </Box>
          </>
        )}

        {!loading && !showPending && filteredCompleted.length === 0 && (
          <EmptyState
            icon={<AssignmentOutlinedIcon />}
            title={filter === "confirmed" ? "暂无已确认项" : "暂无已修改项"}
          />
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
