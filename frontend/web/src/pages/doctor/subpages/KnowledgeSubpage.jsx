/**
 * KnowledgeSubpage — shared knowledge base UI for doctor settings.
 *
 * Displays knowledge items grouped by category with expand/collapse accordions.
 * Click an item → detail view with source, date, reference count, full content.
 * Used by both real SettingsPage (API data) and MockPages (static data).
 *
 * @see /debug/doctor-pages → Settings → 知识库
 */
import { useState, useMemo } from "react";
import { Box, Typography } from "@mui/material";
import { TYPE, ICON, COLOR } from "../../../theme";
import PageSkeleton from "../../../components/PageSkeleton";
import BarButton from "../../../components/BarButton";
import EmptyState from "../../../components/EmptyState";
import ConfirmDialog from "../../../components/ConfirmDialog";
import MenuBookOutlinedIcon from "@mui/icons-material/MenuBookOutlined";

const DEFAULT_CATEGORIES = [
  { key: "interview_guide", label: "问诊指导" },
  { key: "diagnosis_rule", label: "诊断规则" },
  { key: "red_flag", label: "危险信号" },
  { key: "treatment_protocol", label: "治疗方案" },
  { key: "custom", label: "自定义" },
];

function sourceBadge(source) {
  const isAuto = source === "agent_auto" || source === "AI学习";
  return (
    <Box sx={{
      display: "inline-flex", px: 0.8, py: 0.2, borderRadius: "4px",
      fontSize: TYPE.micro.fontSize, fontWeight: 500, flexShrink: 0,
      bgcolor: isAuto ? "#E8F5E9" : "#E8F0FE",
      color: isAuto ? COLOR.primary : "#1B6EF3",
    }}>
      {isAuto ? "AI学习" : "医生"}
    </Box>
  );
}

function formatDate(dateStr) {
  if (!dateStr) return "";
  const d = new Date(dateStr);
  if (isNaN(d)) return dateStr;
  return `${d.getMonth() + 1}月${d.getDate()}日`;
}

/* ── Detail View ── */

function KnowledgeDetail({ item, categories, onBack, onDelete }) {
  const [deleteOpen, setDeleteOpen] = useState(false);
  const catLabel = (categories || DEFAULT_CATEGORIES).find(c => c.key === item.category)?.label || "自定义";

  const detailContent = (
    <Box sx={{ flex: 1, overflowY: "auto", p: 2 }}>
      <Box sx={{ bgcolor: COLOR.white, borderRadius: 1, p: 2, mb: 1 }}>
        <Box sx={{ display: "flex", justifyContent: "space-between", mb: 1.5 }}>
          <Typography sx={{ fontSize: TYPE.heading.fontSize, fontWeight: 600 }}>{catLabel}</Typography>
          {sourceBadge(item.source)}
        </Box>
        {[
          { label: "来源", value: item.source === "agent_auto" || item.source === "AI学习" ? "AI学习" : "医生" },
          { label: "添加时间", value: formatDate(item.created_at) },
          { label: "AI引用", value: `${item.reference_count || 0}次` },
        ].map(({ label, value }) => (
          <Box key={label} sx={{ display: "flex", justifyContent: "space-between", py: 0.8, borderTop: `0.5px solid ${COLOR.borderLight}` }}>
            <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text4 }}>{label}</Typography>
            <Typography sx={{ fontSize: TYPE.secondary.fontSize }}>{value}</Typography>
          </Box>
        ))}
      </Box>
      <Box sx={{ bgcolor: COLOR.white, borderRadius: 1, p: 2 }}>
        <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4, mb: 0.5 }}>内容</Typography>
        <Typography sx={{ fontSize: TYPE.secondary.fontSize, lineHeight: 1.8 }}>{item.text || item.content}</Typography>
      </Box>
    </Box>
  );

  return (
    <>
      <PageSkeleton
        title="知识详情"
        onBack={onBack}
        headerRight={onDelete ? <BarButton onClick={() => setDeleteOpen(true)} color={COLOR.danger}>删除</BarButton> : undefined}
        isMobile
        listPane={detailContent}
      />
      <ConfirmDialog
        open={deleteOpen}
        onClose={() => setDeleteOpen(false)}
        onCancel={() => setDeleteOpen(false)}
        onConfirm={() => { setDeleteOpen(false); onDelete?.(item.id); }}
        title="确认删除"
        message="删除后该知识将不再影响 AI 行为，确定要删除吗？"
        cancelLabel="保留"
        confirmLabel="删除"
        confirmTone="danger"
      />
    </>
  );
}

/* ── List View ── */

export default function KnowledgeSubpage({
  items = [],
  categories = DEFAULT_CATEGORIES,
  loading = false,
  onBack,
  onAdd,
  onDelete,
  title = "知识库",
}) {
  const [expandedCat, setExpandedCat] = useState(null);
  const [detailItem, setDetailItem] = useState(null);

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

  function handleDelete(itemId) {
    setDetailItem(null);
    onDelete?.(itemId);
  }

  if (detailItem) {
    return (
      <KnowledgeDetail
        item={detailItem}
        categories={categories}
        onBack={() => setDetailItem(null)}
        onDelete={onDelete ? handleDelete : undefined}
      />
    );
  }

  const listContent = (
    <Box sx={{ flex: 1, overflowY: "auto" }}>
      {loading && (
          <Box sx={{ textAlign: "center", py: 4 }}>
            <Typography sx={{ color: COLOR.text4 }}>加载中...</Typography>
          </Box>
        )}

        {!loading && (
          <>
            {/* Summary */}
            <Box sx={{ px: 2, py: 1.5 }}>
              <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4 }}>
                共 {items.length} 条知识
              </Typography>
            </Box>

            {/* Category accordions */}
            <Box sx={{ bgcolor: COLOR.white, borderTop: `0.5px solid ${COLOR.border}`, borderBottom: `0.5px solid ${COLOR.border}` }}>
              {categories.map((cat, i) => {
                const catItems = grouped[cat.key] || [];
                const isExpanded = expandedCat === cat.key;
                return (
                  <Box key={cat.key}>
                    {/* Category header */}
                    <Box onClick={() => setExpandedCat(isExpanded ? null : cat.key)}
                      sx={{
                        display: "flex", alignItems: "center", px: 2, py: 1.5,
                        cursor: "pointer", userSelect: "none",
                        borderTop: i > 0 ? `0.5px solid ${COLOR.borderLight}` : "none",
                        "&:active": { bgcolor: COLOR.surfaceAlt },
                      }}>
                      <Box sx={{ flex: 1 }}>
                        <Typography component="span" sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text3 }}>
                          {cat.label}
                        </Typography>
                        <Typography component="span" sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4, ml: 0.8 }}>
                          ({catItems.length})
                        </Typography>
                      </Box>
                      <Typography sx={{ fontSize: ICON.lg, color: COLOR.text4 }}>
                        {isExpanded ? "▾" : "›"}
                      </Typography>
                    </Box>

                    {/* Expanded items */}
                    {isExpanded && catItems.map(item => (
                      <Box key={item.id} onClick={() => setDetailItem(item)}
                        sx={{
                          display: "flex", alignItems: "center", px: 2, py: 1.2, pl: 2,
                          borderTop: `0.5px solid ${COLOR.borderLight}`,
                          borderLeft: `3px solid ${COLOR.primary}`,
                          bgcolor: COLOR.white,
                          cursor: "pointer", "&:active": { bgcolor: COLOR.surfaceAlt },
                        }}>
                        <Box sx={{ flex: 1, minWidth: 0, mr: 1 }}>
                          <Typography sx={{
                            fontSize: TYPE.secondary.fontSize, color: COLOR.text2, lineHeight: 1.5,
                            overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                          }}>
                            {item.text || item.content}
                          </Typography>
                          <Box sx={{ display: "flex", alignItems: "center", gap: 0.8, mt: 0.3 }}>
                            {sourceBadge(item.source)}
                            <Typography sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.text4 }}>
                              {formatDate(item.created_at)}
                            </Typography>
                            <Typography sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.text4 }}>
                              · AI引用 {item.reference_count || 0}次
                            </Typography>
                          </Box>
                        </Box>
                        <Typography sx={{ color: COLOR.text4 }}>›</Typography>
                      </Box>
                    ))}

                    {isExpanded && catItems.length === 0 && (
                      <Box sx={{ px: 2, py: 1.5, borderTop: `0.5px solid ${COLOR.borderLight}`, borderLeft: `3px solid ${COLOR.borderLight}` }}>
                        <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4 }}>暂无条目</Typography>
                      </Box>
                    )}
                  </Box>
                );
              })}
            </Box>

            {/* Empty state */}
            {items.length === 0 && (
              <EmptyState
                icon={<MenuBookOutlinedIcon />}
                title="暂无知识条目"
                subtitle="点击右上角「添加」开始构建您的知识库"
              />
            )}

            <Box sx={{ height: 24 }} />
          </>
        )}
      </Box>
  );

  return (
    <PageSkeleton
      title={title}
      onBack={onBack}
      headerRight={onAdd ? <BarButton onClick={onAdd}>添加</BarButton> : undefined}
      isMobile
      listPane={listContent}
    />
  );
}
