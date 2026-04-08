/**
 * KnowledgeSubpage — flat list with rich cards sorted by activity.
 *
 * Each row shows title, summary, usage count + recency, and navigates
 * to the detail page on tap. No inline expand/collapse or delete.
 *
 * @see /mock/doctor/settings/knowledge
 */
import { useState } from "react";
import { Box, InputAdornment, TextField, Typography } from "@mui/material";
import MenuBookOutlinedIcon from "@mui/icons-material/MenuBookOutlined";
import SearchIcon from "@mui/icons-material/Search";
import { TYPE, COLOR, RADIUS } from "../../../theme";
import PageSkeleton from "../../../components/PageSkeleton";
import KnowledgeCard from "../../../components/KnowledgeCard";
import StatColumn from "../../../components/StatColumn";
import EmptyState from "../../../components/EmptyState";
import NewItemCard from "../../../components/NewItemCard";
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

/* ── PersonaCard ── */

function PersonaCard({ persona, onClick }) {
  if (!persona) return null;

  const isActive = persona.persona_status === "active";
  const isDraftReady = persona.persona_status === "draft"
    && persona.content
    && !persona.content.includes("（AI会根据你的回复逐渐学习");

  let subtitle = `待学习 · 已收集 ${persona.edit_count || 0} 条回复`;
  let accentColor = COLOR.text4;

  if (isDraftReady) {
    subtitle = "AI已分析你的风格 · 点击查看";
    accentColor = COLOR.accent;
  } else if (isActive) {
    const date = persona.updated_at ? formatRelativeDate(persona.updated_at) : "";
    subtitle = `已启用 · 基于 ${persona.edit_count || 0} 条回复${date ? ` · ${date}` : ""}`;
    accentColor = COLOR.primary;
  }

  return (
    <Box
      onClick={onClick}
      sx={{
        mx: 1.5, mt: 1.5, mb: 0.5, px: 2, py: 1.5,
        bgcolor: COLOR.white,
        borderRadius: RADIUS.md,
        border: `1px solid ${isDraftReady ? COLOR.accent : COLOR.borderLight}`,
        cursor: "pointer",
        "&:active": { opacity: 0.8 },
      }}
    >
      <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
        <Typography sx={{ fontSize: TYPE.action.fontSize, fontWeight: 600 }}>
          我的AI人设
        </Typography>
        <Box
          component="span"
          sx={{
            fontSize: 10, fontWeight: 600,
            borderRadius: RADIUS.sm, px: 0.5, py: 0.25,
            bgcolor: isActive ? COLOR.primaryLight : (isDraftReady ? COLOR.amberLight : COLOR.surface),
            color: accentColor,
          }}
        >
          {isActive ? "已启用" : isDraftReady ? "待确认" : "学习中"}
        </Box>
      </Box>
      <Typography sx={{ fontSize: TYPE.caption.fontSize, color: accentColor, mt: 0.5 }}>
        {subtitle}
      </Typography>
    </Box>
  );
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
  persona,
  onPersonaClick,
}) {
  const regularItems = items.filter(item => item.category !== "persona");
  const sorted = mergeAndSort(regularItems, stats);
  const [search, setSearch] = useState("");

  // Compute weekly citation total
  const weekCitations = Array.isArray(stats)
    ? stats.reduce((sum, s) => sum + (s.total_count || 0), 0)
    : sorted.reduce((sum, it) => sum + (it._usageCount || 0), 0);

  const unusedCount = sorted.filter(item => (item._usageCount || 0) === 0).length;

  // Filter sorted items by search
  const filtered = search.trim()
    ? sorted.filter(item => {
        const q = search.trim();
        const titleText = item.title || extractShortTitle(item.text || item.content || "");
        return titleText.includes(q) || (item.text || "").includes(q) || (item.content || "").includes(q);
      })
    : sorted;

  const listContent = (
    <Box sx={{ flex: 1, overflowY: "auto" }}>
      {loading && (
        <Box sx={{ textAlign: "center", py: 4 }}>
          <Typography sx={{ color: COLOR.text4 }}>加载中...</Typography>
        </Box>
      )}

      {!loading && regularItems.length === 0 && (
        <>
          <PersonaCard persona={persona} onClick={onPersonaClick} />
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
        </>
      )}

      {!loading && regularItems.length > 0 && (
        <>
          <PersonaCard persona={persona} onClick={onPersonaClick} />
          {/* Search bar */}
          <Box sx={{ px: 1.5, py: 1, bgcolor: COLOR.surfaceAlt }}>
            <TextField size="small" fullWidth
              placeholder={`搜索知识规则${regularItems.length > 0 ? ` (共${regularItems.length}条)` : ""}`}
              value={search} onChange={(e) => setSearch(e.target.value)}
              InputProps={{ startAdornment: <InputAdornment position="start"><SearchIcon fontSize="small" /></InputAdornment> }}
              sx={{ "& .MuiOutlinedInput-root": { borderRadius: RADIUS.sm, bgcolor: COLOR.white } }}
            />
          </Box>

          {/* Stats bar */}
          <Box sx={{ display: "flex", py: 1.5, px: 2, bgcolor: COLOR.white, borderBottom: `0.5px solid ${COLOR.borderLight}` }}>
            <StatColumn value={regularItems.length} label="条规则" />
            <Box sx={{ width: "0.5px", bgcolor: COLOR.borderLight }} />
            <StatColumn value={weekCitations} label="本周引用" color={COLOR.primary} />
            <Box sx={{ width: "0.5px", bgcolor: COLOR.borderLight }} />
            <StatColumn value={unusedCount} label="未引用" color={unusedCount > 0 ? COLOR.warning : COLOR.text4} />
          </Box>

          {onAdd && <NewItemCard title="添加知识" subtitle="上传文件、网址导入或手动输入" onClick={onAdd} />}

          {/* Knowledge rows */}
          <Box sx={{ bgcolor: COLOR.white, borderTop: `0.5px solid ${COLOR.borderLight}` }}>
            {filtered.map((item) => (
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
      isMobile
      listPane={listContent}
    />
  );
}
