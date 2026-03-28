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
import AddCircleOutlineIcon from "@mui/icons-material/AddCircleOutline";
import ChevronRightOutlinedIcon from "@mui/icons-material/ChevronRightOutlined";
import { TYPE, ICON, COLOR } from "../../../theme";
import PageSkeleton from "../../../components/PageSkeleton";
import ListCard from "../../../components/ListCard";
import EmptyState from "../../../components/EmptyState";
import AppButton from "../../../components/AppButton";

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
  const usageCount = item._usageCount || 0;
  const lastUsed = item._lastUsed;

  // Build meta parts
  const metaParts = [];
  if (usageCount > 0) metaParts.push(`引用${usageCount}次`);
  if (lastUsed) metaParts.push(`最近${formatRelativeDate(lastUsed)}`);
  const metaText = metaParts.join(" \u00B7 ");

  return (
    <Box
      onClick={onClick}
      sx={{
        display: "flex",
        alignItems: "flex-start",
        gap: 1,
        px: 2,
        py: 1.5,
        bgcolor: COLOR.white,
        borderBottom: `0.5px solid ${COLOR.borderLight}`,
        cursor: "pointer",
        userSelect: "none",
        WebkitUserSelect: "none",
        minHeight: 44,
        "&:active": { bgcolor: COLOR.surface },
      }}
    >
      {/* Green active dot */}
      <Box sx={{ pt: 0.7, flexShrink: 0 }}>
        <Box sx={{ width: 8, height: 8, borderRadius: "50%", bgcolor: COLOR.primary, flexShrink: 0 }} />
      </Box>

      {/* Content */}
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Typography
          sx={{
            fontSize: TYPE.body.fontSize,
            fontWeight: 500,
            color: COLOR.text1,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {title || "untitled"}
        </Typography>
        {summary && (
          <Typography
            sx={{
              fontSize: TYPE.secondary.fontSize,
              color: COLOR.text3,
              mt: 0.25,
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
          >
            {summary}
          </Typography>
        )}
        {metaText && (
          <Typography
            sx={{
              fontSize: TYPE.caption.fontSize,
              color: COLOR.text4,
              mt: 0.25,
            }}
          >
            {metaText}
          </Typography>
        )}
      </Box>

      {/* Chevron */}
      <Box sx={{ pt: 0.5, flexShrink: 0 }}>
        <ChevronRightOutlinedIcon sx={{ fontSize: ICON.sm, color: COLOR.text4 }} />
      </Box>
    </Box>
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
                avatar={<AddCircleOutlineIcon sx={{ fontSize: 22, color: COLOR.primary }} />}
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
