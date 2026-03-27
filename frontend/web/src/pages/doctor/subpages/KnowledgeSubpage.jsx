/**
 * KnowledgeSubpage — WeChat-inspired knowledge base with collapsible category sections.
 *
 * Each category renders as a white card with left color accent bar.
 * Items show 2-line text preview + metadata. Tap item → inline edit.
 * Swipe left → delete. Sections with ≤5 items expand by default.
 *
 * @see /debug/doctor/settings/knowledge
 */
import { useState, useMemo } from "react";
import { Box, Typography } from "@mui/material";
import { TYPE, COLOR } from "../../../theme";
import PageSkeleton from "../../../components/PageSkeleton";
import BarButton from "../../../components/BarButton";
import EmptyState from "../../../components/EmptyState";
import ConfirmDialog from "../../../components/ConfirmDialog";
import InlineEditor from "../../../components/InlineEditor";
import MenuBookOutlinedIcon from "@mui/icons-material/MenuBookOutlined";

// Category colors — single source of truth
export const KNOWLEDGE_CATEGORY_COLORS = {
  red_flag: "#E8533F",
  interview_guide: "#07C160",
  diagnosis_rule: "#1B6EF3",
  treatment_protocol: "#8e44ad",
  custom: "#999",
};

const DEFAULT_CATEGORIES = [
  { key: "red_flag", label: "危险信号" },
  { key: "interview_guide", label: "问诊指导" },
  { key: "diagnosis_rule", label: "诊断规则" },
  { key: "treatment_protocol", label: "治疗方案" },
  { key: "custom", label: "自定义" },
];

function formatDate(dateStr) {
  if (!dateStr) return "";
  const d = new Date(dateStr);
  if (isNaN(d)) return dateStr;
  return `${d.getMonth() + 1}月${d.getDate()}日`;
}

/* ── Item Row ── */

function KnowledgeItemRow({ item, color, onEdit, onDelete }) {
  const [editing, setEditing] = useState(false);
  const text = item.text || item.content || "";

  function handleSave(newText) {
    onEdit?.(item.id, newText);
    setEditing(false);
  }

  const content = (
    <Box onClick={!editing && onEdit ? () => setEditing(true) : undefined}
      sx={{
        display: "flex",
        borderTop: `0.5px solid ${COLOR.borderLight}`,
        cursor: !editing && onEdit ? "pointer" : "default",
        bgcolor: COLOR.white,
        "&:active": !editing && onEdit ? { bgcolor: COLOR.surfaceAlt } : {},
      }}>
      {/* Color accent bar */}
      <Box sx={{ width: "3px", flexShrink: 0, bgcolor: color || COLOR.borderLight, my: "6px", borderRadius: "1.5px" }} />
      <Box sx={{ flex: 1, minWidth: 0, px: 2, py: 1.2 }}>
      {editing ? (
        <InlineEditor value={text} onSave={handleSave} onCancel={() => setEditing(false)}
          onDelete={onDelete ? () => { setEditing(false); onDelete(item.id); } : undefined} />
      ) : (
        <>
          <Typography sx={{
            fontSize: TYPE.body.fontSize, color: COLOR.text2, lineHeight: 1.55,
            whiteSpace: "pre-wrap", wordBreak: "break-word",
          }}>
            {text}
          </Typography>
          <Typography sx={{ fontSize: 10, color: COLOR.text4, mt: 0.4 }}>
            引用{item.reference_count || 0}次
            {item.created_at ? ` · ${formatDate(item.created_at)}` : ""}
          </Typography>
        </>
      )}
      </Box>
    </Box>
  );

  return content;
}

/* ── Section Header ── */

function KnowledgeSectionHeader({ label, count, color, expanded, onToggle }) {
  return (
    <Box onClick={onToggle}
      sx={{
        display: "flex", alignItems: "center",
        cursor: "pointer", bgcolor: COLOR.white,
        "&:active": { bgcolor: COLOR.surfaceAlt },
      }}>
      <Box sx={{ width: "3px", alignSelf: "stretch", flexShrink: 0, bgcolor: color, my: "6px", borderRadius: "1.5px" }} />
      <Box sx={{ flex: 1, display: "flex", alignItems: "center", px: 2, py: 1.3 }}>
        <Box sx={{ flex: 1 }}>
          <Typography component="span" sx={{ fontSize: TYPE.action.fontSize, fontWeight: 600, color: COLOR.text1 }}>
            {label}
          </Typography>
          <Typography component="span" sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4, ml: 0.8 }}>
            {count}
          </Typography>
        </Box>
        <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4 }}>
          {expanded ? "▾" : "›"}
        </Typography>
      </Box>
    </Box>
  );
}

/* ── Main ── */

export default function KnowledgeSubpage({
  items = [],
  categories = DEFAULT_CATEGORIES,
  loading = false,
  onBack,
  onAdd,
  onDelete,
  onEdit,
  title = "知识库",
}) {
  const [deleteTarget, setDeleteTarget] = useState(null);

  const grouped = useMemo(() => {
    const groups = {};
    categories.forEach(c => { groups[c.key] = []; });
    items.forEach(item => {
      const cat = item.category || "custom";
      if (!groups[cat]) groups[cat] = [];
      groups[cat].push(item);
    });
    return groups;
  }, [items, categories]);

  // ≤5 items → expanded, >5 → collapsed by default
  // Track which sections the user has manually toggled
  const [manualToggles, setManualToggles] = useState({});

  const collapsed = useMemo(() => {
    const auto = {};
    categories.forEach(c => {
      const count = (grouped[c.key] || []).length;
      auto[c.key] = count > 5;
    });
    return { ...auto, ...manualToggles };
  }, [grouped, categories, manualToggles]);

  function toggleSection(key) {
    setManualToggles(prev => ({ ...prev, [key]: !collapsed[key] }));
  }

  const listContent = (
    <Box sx={{ flex: 1, overflowY: "auto" }}>
      {loading && (
        <Box sx={{ textAlign: "center", py: 4 }}>
          <Typography sx={{ color: COLOR.text4 }}>加载中...</Typography>
        </Box>
      )}

      {!loading && items.length === 0 && (
        <EmptyState
          icon={<MenuBookOutlinedIcon />}
          title="暂无知识条目"
          subtitle="点击右上角「添加」开始构建您的知识库"
        />
      )}

      {!loading && items.length > 0 && (
        <>
          {/* Total count */}
          <Box sx={{ px: 2, py: 1.2 }}>
            <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4 }}>
              共 {items.length} 条知识
            </Typography>
          </Box>

          {/* Category sections */}
          {categories.map((cat) => {
            const catItems = grouped[cat.key] || [];
            if (catItems.length === 0) return null;
            const isExpanded = !collapsed[cat.key];
            const catColor = cat.color || KNOWLEDGE_CATEGORY_COLORS[cat.key] || COLOR.borderLight;
            return (
              <Box key={cat.key} sx={{ bgcolor: COLOR.white, mb: 0.8 }}>
                <KnowledgeSectionHeader
                  label={cat.label}
                  count={catItems.length}
                  color={catColor}
                  expanded={isExpanded}
                  onToggle={() => toggleSection(cat.key)}
                />
                {isExpanded && catItems.map(item => (
                  <KnowledgeItemRow
                    key={item.id}
                    item={item}
                    color={catColor}
                    onEdit={onEdit}
                    onDelete={onDelete ? (id) => setDeleteTarget(id) : undefined}
                  />
                ))}
              </Box>
            );
          })}
          <Box sx={{ height: 24 }} />
        </>
      )}
    </Box>
  );

  return (
    <>
      <PageSkeleton
        title={title}
        onBack={onBack}
        headerRight={onAdd ? <BarButton onClick={onAdd}>添加</BarButton> : undefined}
        isMobile
        listPane={listContent}
      />
      <ConfirmDialog
        open={deleteTarget != null}
        onClose={() => setDeleteTarget(null)}
        onCancel={() => setDeleteTarget(null)}
        onConfirm={() => { onDelete?.(deleteTarget); setDeleteTarget(null); }}
        title="确认删除"
        message="删除后该知识将不再影响 AI 行为，确定要删除吗？"
        cancelLabel="保留"
        confirmLabel="删除"
        confirmTone="danger"
      />
    </>
  );
}
