/**
 * KnowledgeSubpage — flat list with rich cards sorted by activity.
 *
 * Each row shows title, summary, usage count + recency, and navigates
 * to the detail page on tap. No inline expand/collapse or delete.
 *
 * @see /debug/doctor/settings/knowledge
 */
import { Box, Typography } from "@mui/material";
import MenuBookOutlinedIcon from "@mui/icons-material/MenuBookOutlined";
// ChevronRightOutlinedIcon removed — ListCard handles chevron
import { TYPE, COLOR } from "../../../theme";
import PageSkeleton from "../../../components/PageSkeleton";
import ListCard from "../../../components/ListCard";
import KnowledgeCard from "../../../components/KnowledgeCard";
import EmptyState from "../../../components/EmptyState";
import AppButton from "../../../components/AppButton";
import IconBadge from "../../../components/IconBadge";
import { ICON_BADGES } from "../constants";

/* ── Helpers ── */

function formatRelativeDate(dateStr) {
  if (!dateStr) return "";
  const d = new Date(dateStr);
  if (isNaN(d)) return dateStr;

  const now = new Date();
  const diffMs = now - d;
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  if (diffDays === 0) return "今天";
  if (diffDays === 1) return "昨天";
  if (diffDays < 7) return `${diffDays}天前`;
  return `${d.getMonth() + 1}月${d.getDate()}日`;
}

/**
 * Extract a short title from knowledge text (mirrors backend logic).
 * 1. Take first line  2. Split on ： or : (colon)  3. Split on 。 (period)  4. Cap at 20 chars
 */
function extractShortTitle(text, maxLen = 20) {
  if (!text) return "";
  let line = text.split("\n").filter((l) => l.trim())[0] || "";
  // Try colon first (strongest delimiter)
  for (const sep of ["：", ":"]) {
    if (line.includes(sep)) {
      const candidate = line.split(sep)[0].trim();
      if (candidate) { line = candidate; break; }
    }
  }
  // Then period
  if (line.length > maxLen && line.includes("。")) {
    line = line.split("。")[0].trim();
  }
  if (line.length > maxLen) {
    line = line.slice(0, maxLen) + "…";
  }
  return line;
}

/**
 * Merge items with per-item stats to produce sorted list.
 * Stats shape: [{ knowledge_item_id, total_count, last_used }]
 */
function mergeAndSort(items, stats) {
  const statsMap = new Map();
  if (Array.isArray(stats)) {
    stats.forEach((s) => statsMap.set(s.knowledge_item_id, s));
  }

  return [...items]
    .map((item) => {
      const s = statsMap.get(item.id);
      return {
        ...item,
        _usageCount: s?.total_count ?? item.reference_count ?? 0,
        _lastUsed: s?.last_used ?? item.created_at ?? "",
      };
    })
    .sort((a, b) => {
      // Primary: usage count desc
      if (b._usageCount !== a._usageCount) return b._usageCount - a._usageCount;
      // Secondary: created_at desc
      return (b.created_at || "").localeCompare(a.created_at || "");
    });
}

/* ── KnowledgeRow ── */

function KnowledgeRow({ item, onClick }) {
  const rawText = item.text || item.content || "";
  const title = item.title && item.title.length <= 25 ? item.title : extractShortTitle(rawText);
  const summary = item.summary || (rawText.startsWith(title) ? rawText.slice(title.length).replace(/^[：:\s]+/, "").slice(0, 50) : rawText.slice(0, 50));
  const usageCount = item._usageCount || item.reference_count || 0;
  const date = item.created_at ? formatRelativeDate(item.created_at) : "";

  return (
    <KnowledgeCard
      title={title || "untitled"}
      summary={summary}
      referenceCount={usageCount}
      source={item.source}
      date={date}
      onClick={onClick}
    />
  );
}

/* ── Main ── */

export default function KnowledgeSubpage({
  items = [],
  loading = false,
  onBack,
  onAdd,
  onDelete, // kept for interface compat, not used in list view
  title = "我的方法",
  stats,
  onItemClick,
}) {
  const sorted = mergeAndSort(items, stats);

  // Compute weekly citation total
  const weekCitations = Array.isArray(stats)
    ? stats.reduce((sum, s) => sum + (s.total_count || 0), 0)
    : sorted.reduce((sum, it) => sum + (it._usageCount || 0), 0);

  const listContent = (
    <Box sx={{ flex: 1, overflowY: "auto" }}>
      {loading && (
        <Box sx={{ textAlign: "center", py: 4 }}>
          <Typography sx={{ color: COLOR.text4 }}>加载中...</Typography>
        </Box>
      )}

      {!loading && items.length === 0 && (
        <Box sx={{ display: "flex", flexDirection: "column", alignItems: "center", py: 8, gap: 1.5, px: 2 }}>
          <EmptyState
            icon={<MenuBookOutlinedIcon />}
            title="暂无知识条目"
          />
          {onAdd && (
            <AppButton variant="primary" size="md" onClick={onAdd}>
              添加第一条规则
            </AppButton>
          )}
        </Box>
      )}

      {!loading && items.length > 0 && (
        <>
          {/* Stats summary */}
          <Box sx={{ px: 2, pt: 1.5, pb: 1 }}>
            <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4 }}>
              共 {items.length} 条 {"\u00B7"} 本周引用 {weekCitations} 次
            </Typography>
          </Box>

          {/* Add knowledge entry */}
          {onAdd && (
            <Box sx={{ bgcolor: COLOR.white, borderTop: `0.5px solid ${COLOR.borderLight}`, mb: 0.5 }}>
              <ListCard
                avatar={<IconBadge config={ICON_BADGES.kb_add} />}
                title="添加知识"
                subtitle="上传文件、粘贴网址或手动输入"
                chevron
                onClick={onAdd}
              />
            </Box>
          )}

          {/* Knowledge rows */}
          <Box sx={{ bgcolor: COLOR.white, borderTop: `0.5px solid ${COLOR.borderLight}` }}>
            {sorted.map((item) => (
              <KnowledgeRow
                key={item.id}
                item={item}
                onClick={() => onItemClick?.(item.id)}
              />
            ))}
          </Box>
          <Box sx={{ height: 24 }} />
        </>
      )}
    </Box>
  );

  return (
    <PageSkeleton
      title={title}
      onBack={onBack}
      headerRight={undefined}
      isMobile
      listPane={listContent}
    />
  );
}
