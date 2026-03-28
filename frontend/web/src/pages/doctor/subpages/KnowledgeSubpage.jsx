/**
 * KnowledgeSubpage — flat chronological list with source-type avatars.
 *
 * Uses ListCard pattern (same as PatientsPage). Items expand on tap
 * to show full text + delete button. No inline edit until PATCH endpoint exists.
 *
 * @see /debug/doctor/settings/knowledge
 */
import { useState } from "react";
import { Avatar, Box, Typography } from "@mui/material";
import EditNoteOutlinedIcon from "@mui/icons-material/EditNoteOutlined";
import DescriptionOutlinedIcon from "@mui/icons-material/DescriptionOutlined";
import SmartToyOutlinedIcon from "@mui/icons-material/SmartToyOutlined";
import MenuBookOutlinedIcon from "@mui/icons-material/MenuBookOutlined";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import { TYPE, COLOR } from "../../../theme";
import PageSkeleton from "../../../components/PageSkeleton";
import BarButton from "../../../components/BarButton";
import ListCard from "../../../components/ListCard";
import EmptyState from "../../../components/EmptyState";
import ConfirmDialog from "../../../components/ConfirmDialog";
import SectionLabel from "../../../components/SectionLabel";

/* ── Source config ── */

const SOURCE_CONFIG = {
  doctor: {
    label: "手动添加",
    icon: <EditNoteOutlinedIcon sx={{ fontSize: 18, color: "#fff" }} />,
    bg: COLOR.primary,
  },
  agent_auto: {
    label: "AI生成",
    icon: <SmartToyOutlinedIcon sx={{ fontSize: 18, color: "#fff" }} />,
    bg: COLOR.text3,
  },
};

function getSourceConfig(source) {
  if (!source) return SOURCE_CONFIG.doctor;
  if (source.startsWith("upload:")) {
    return {
      label: source.slice("upload:".length),
      icon: <DescriptionOutlinedIcon sx={{ fontSize: 18, color: "#fff" }} />,
      bg: COLOR.success,
    };
  }
  return SOURCE_CONFIG[source] || SOURCE_CONFIG.doctor;
}

/* ── Helpers ── */

function formatDate(dateStr) {
  if (!dateStr) return "";
  const d = new Date(dateStr);
  if (isNaN(d)) return dateStr;
  return `${d.getMonth() + 1}月${d.getDate()}日`;
}

function firstLine(text) {
  if (!text) return "";
  const lines = text.split("\n").filter((l) => l.trim());
  return lines[0] || "";
}

/* ── KnowledgeRow ── */

function KnowledgeRow({ item, expanded, onToggle, onDelete }) {
  const text = item.text || item.content || "";
  const cfg = getSourceConfig(item.source);

  const avatar = (
    <Avatar sx={{ width: 36, height: 36, bgcolor: cfg.bg, flexShrink: 0 }}>
      {cfg.icon}
    </Avatar>
  );

  const right = (
    <Box sx={{ textAlign: "right", flexShrink: 0 }}>
      {(item.reference_count || 0) > 0 && (
        <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4, whiteSpace: "nowrap" }}>
          引用{item.reference_count}次
        </Typography>
      )}
      <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4, whiteSpace: "nowrap" }}>
        {formatDate(item.created_at)}
      </Typography>
    </Box>
  );

  return (
    <Box>
      <ListCard
        avatar={avatar}
        title={firstLine(text)}
        subtitle={cfg.label}
        right={right}
        onClick={onToggle}
      />
      {expanded && (
        <Box sx={{ bgcolor: COLOR.surface, px: 2, py: 1.5, borderBottom: `0.5px solid ${COLOR.borderLight}` }}>
          <Typography sx={{
            fontSize: TYPE.body.fontSize, color: COLOR.text2, lineHeight: 1.6,
            whiteSpace: "pre-wrap", wordBreak: "break-word",
          }}>
            {text}
          </Typography>
          {onDelete && (
            <Box
              onClick={() => onDelete(item.id)}
              sx={{
                display: "inline-flex", alignItems: "center", gap: 0.5,
                mt: 1.5, cursor: "pointer", color: COLOR.danger,
                "&:active": { opacity: 0.6 },
              }}
            >
              <DeleteOutlineIcon sx={{ fontSize: 16 }} />
              <Typography sx={{ fontSize: TYPE.caption.fontSize }}>删除</Typography>
            </Box>
          )}
        </Box>
      )}
    </Box>
  );
}

/* ── Main ── */

export default function KnowledgeSubpage({
  items = [],
  loading = false,
  onBack,
  onAdd,
  onDelete,
  title = "知识库",
}) {
  const [expandedId, setExpandedId] = useState(null);
  const [deleteTarget, setDeleteTarget] = useState(null);

  function toggleExpand(id) {
    setExpandedId((prev) => (prev === id ? null : id));
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
          <SectionLabel>共 {items.length} 条知识</SectionLabel>
          {items.map((item) => (
            <KnowledgeRow
              key={item.id}
              item={item}
              expanded={expandedId === item.id}
              onToggle={() => toggleExpand(item.id)}
              onDelete={onDelete ? (id) => setDeleteTarget(id) : undefined}
            />
          ))}
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
