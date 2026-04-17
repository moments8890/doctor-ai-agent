/**
 * KnowledgeSubpage — flat list with rich cards sorted by activity.
 *
 * Each row shows title, summary, usage count + recency, and navigates
 * to the detail page on tap. No inline expand/collapse or delete.
 *
 * @see /mock/doctor/settings/knowledge
 */
import { useState } from "react";
import { Box, Chip, InputAdornment, TextField, Typography } from "@mui/material";
import MenuBookOutlinedIcon from "@mui/icons-material/MenuBookOutlined";
import SearchIcon from "@mui/icons-material/Search";
import { TYPE, COLOR, ICON, RADIUS } from "../../../theme";
import HelpTip from "../../../components/HelpTip";
import { relativeDate } from "../../../utils/time";
import PageSkeleton from "../../../components/PageSkeleton";
import KnowledgeCard from "../../../components/KnowledgeCard";
import StatColumn from "../../../components/StatColumn";
import EmptyState from "../../../components/EmptyState";
import NewItemCard from "../../../components/NewItemCard";
import AppButton from "../../../components/AppButton";
import ListCard from "../../../components/ListCard";
import IconBadge from "../../../components/IconBadge";
import { ICON_BADGES, PAGE_HELP } from "../constants";
import { useKbPending, useKbHallucinations } from "../../../lib/doctorQueries";
import { useAppNavigate } from "../../../hooks/useAppNavigate";
import { dp } from "../../../utils/doctorBasePath";

/* ── Helpers ── */

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

/* ── Persona summary for KnowledgeCard ── */

function personaSummary(persona) {
  if (!persona) return "";
  const isActive = persona.persona_status === "active";
  const isDraftReady = persona.persona_status === "draft"
    && persona.content
    && !persona.content.includes("（待学习）");
  if (isDraftReady) return "AI已分析你的风格 · 点击查看";
  if (isActive) return `已启用 · 基于 ${persona.edit_count || 0} 条回复`;
  return `待学习 · 已收集 ${persona.edit_count || 0} 条回复`;
}

/* ── KnowledgeRow ── */

function KnowledgeRow({ item, onClick }) {
  const rawText = item.text || item.content || "";
  const title = item.title && item.title.length <= 25 ? item.title : extractShortTitle(rawText);
  const summary = item.summary || (rawText.startsWith(title) ? rawText.slice(title.length).replace(/^[：:\s]+/, "").slice(0, 50) : rawText.slice(0, 50));
  const usageCount = item._usageCount || item.reference_count || 0;
  const date = item.created_at ? relativeDate(item.created_at) : "";

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

  const { data: kbPendingData } = useKbPending();
  const kbPendingCount = kbPendingData?.count || 0;
  const { data: hallucinationData } = useKbHallucinations();
  const hallucinationCount = hallucinationData?.count || 0;
  const navigate = useAppNavigate();

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
      {kbPendingCount > 0 && (
        <Box
          onClick={() => navigate(dp("settings/knowledge/pending"))}
          sx={{
            p: 1.5, m: 1.5, cursor: "pointer",
            bgcolor: COLOR.surfaceAlt,
            borderRadius: RADIUS.md,
            display: "flex", alignItems: "center", gap: 1,
          }}
        >
          <Chip label="新" size="small" color="warning" />
          <Typography sx={{ fontSize: TYPE.body.fontSize }}>
            AI 从您的编辑中发现 {kbPendingCount} 条待确认临床规则
          </Typography>
        </Box>
      )}

      {hallucinationCount > 0 && (
        <Box
          sx={{
            p: 1.5, mx: 1.5, my: 1,
            bgcolor: "#fff3e0",
            borderRadius: RADIUS.md,
            display: "flex", alignItems: "center", gap: 1,
          }}
        >
          <Chip label="注意" size="small" color="warning" />
          <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text2 }}>
            AI 最近 7 天引用了 {hallucinationCount} 条不存在的规则 — 可能需要检查 prompt 或补充 KB
          </Typography>
        </Box>
      )}

      {loading && (
        <Box sx={{ textAlign: "center", py: 4 }}>
          <Typography sx={{ color: COLOR.text4 }}>加载中...</Typography>
        </Box>
      )}

      {!loading && regularItems.length === 0 && (
        <>
          {persona && (
            <Box sx={{ bgcolor: COLOR.white, borderTop: `0.5px solid ${COLOR.borderLight}` }}>
              <ListCard
                avatar={<IconBadge config={ICON_BADGES.persona} />}
                title="我的AI风格"
                subtitle={personaSummary(persona)}
                chevron
                onClick={onPersonaClick}
              />
            </Box>
          )}
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

          {/* Knowledge rows — persona pinned at top */}
          <Box sx={{ bgcolor: COLOR.white, borderTop: `0.5px solid ${COLOR.borderLight}` }}>
            {persona && (
              <ListCard
                avatar={<IconBadge config={ICON_BADGES.persona} />}
                title="我的AI风格"
                subtitle={personaSummary(persona)}
                chevron
                onClick={onPersonaClick}
              />
            )}
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
      headerRight={<HelpTip message={PAGE_HELP.knowledge} />}
      onBack={onBack}
      isMobile
      listPane={listContent}
    />
  );
}
