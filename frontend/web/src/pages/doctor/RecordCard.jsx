/**
 * 病历卡片组件：可展开查看详情，支持编辑和删除操作。
 */
import { useState } from "react";
import { Box, Typography } from "@mui/material";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import ExpandLessIcon from "@mui/icons-material/ExpandLess";
import EditOutlinedIcon from "@mui/icons-material/EditOutlined";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import { deleteRecord } from "../../api";
import { RECORD_TYPE_LABEL } from "./constants";
import RecordEditDialog from "./RecordEditDialog";
import { TYPE, ICON } from "../../theme";

const RECORD_DOT_COLORS = {
  visit: "#07C160", dictation: "#5b9bd5", import: "#e8833a",
  lab: "#9b59b6", imaging: "#1890ff", surgery: "#FA5151",
  referral: "#16a085", interview_summary: "#8e44ad",
};

function RecordCardHeader({ current, expanded, dotColor }) {
  const date = current.created_at ? current.created_at.slice(0, 10) : "—";
  return (
    <Box sx={{ display: "flex", alignItems: "flex-start", px: 2, py: 1.3, cursor: "pointer", "&:active": { bgcolor: "#f9f9f9" } }}>
      <Box sx={{ width: 8, height: 8, borderRadius: "50%", bgcolor: dotColor, flexShrink: 0, mt: 0.7, mr: 1.4 }} />
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 1, mb: 0.3 }}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 0.8, flexWrap: "wrap" }}>
            {current.record_type && (
              <Typography sx={{ fontSize: TYPE.caption.fontSize, color: dotColor, fontWeight: 600 }}>
                {RECORD_TYPE_LABEL[current.record_type] || current.record_type}
              </Typography>
            )}
            {(Array.isArray(current.tags) ? current.tags : []).map((tag, i) => (
              <Typography key={i} sx={{ fontSize: TYPE.micro.fontSize, color: "#999", bgcolor: "#f5f5f5", px: 0.6, borderRadius: 0.5 }}>
                {tag}
              </Typography>
            ))}
          </Box>
          <Typography sx={{ fontSize: TYPE.micro.fontSize, color: "#bbb", flexShrink: 0, fontFamily: "monospace" }}>{date}</Typography>
        </Box>
        <Typography sx={{
          fontSize: TYPE.secondary.fontSize, color: current.content ? "text.primary" : "#bbb",
          overflow: "hidden", display: "-webkit-box",
          WebkitLineClamp: expanded ? "unset" : 2,
          WebkitBoxOrient: "vertical", whiteSpace: "pre-wrap",
        }}>
          {current.content || "（无记录内容）"}
        </Typography>
      </Box>
      <Box sx={{ ml: 1, flexShrink: 0, display: "flex", alignItems: "center", mt: 0.2 }}>
        {expanded ? <ExpandLessIcon sx={{ fontSize: ICON.md, color: "#bbb" }} /> : <ExpandMoreIcon sx={{ fontSize: ICON.md, color: "#bbb" }} />}
      </Box>
    </Box>
  );
}

function DeleteConfirmRow({ deleting, onConfirm, onCancel }) {
  return (
    <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
      <Typography sx={{ fontSize: TYPE.caption.fontSize, color: "#FA5151" }}>确认删除？</Typography>
      <Box onClick={!deleting ? onConfirm : undefined}
        sx={{ fontSize: TYPE.caption.fontSize, color: "#fff", bgcolor: "#FA5151", px: 1, py: 0.3, borderRadius: 1, cursor: deleting ? "default" : "pointer", "&:active": { opacity: 0.7 } }}>
        {deleting ? "删除中…" : "确认"}
      </Box>
      <Box onClick={onCancel} sx={{ fontSize: TYPE.caption.fontSize, color: "#666", cursor: "pointer", "&:active": { opacity: 0.7 } }}>
        取消
      </Box>
    </Box>
  );
}

function RecordExpandedBody({ current, confirmingDelete, deleting, onConfirmDelete, onCancelDelete, onOpenDelete, onOpenEdit }) {
  return (
    <Box sx={{ px: 2, pb: 1.5, pt: 0 }}>
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 0.5 }}>
        {confirmingDelete ? (
          <DeleteConfirmRow deleting={deleting} onConfirm={onConfirmDelete} onCancel={onCancelDelete} />
        ) : (
          <Box onClick={(e) => { e.stopPropagation(); onOpenDelete(); }}
            sx={{ fontSize: TYPE.caption.fontSize, color: "#FA5151", cursor: "pointer", display: "flex", alignItems: "center", gap: 0.4 }}>
            <DeleteOutlineIcon sx={{ fontSize: ICON.xs }} />删除
          </Box>
        )}
        <Box onClick={(e) => { e.stopPropagation(); onOpenEdit(); }}
          sx={{ fontSize: TYPE.caption.fontSize, color: "#07C160", cursor: "pointer", display: "flex", alignItems: "center", gap: 0.4 }}>
          <EditOutlinedIcon sx={{ fontSize: ICON.xs }} />编辑
        </Box>
      </Box>
      <Box sx={{ bgcolor: "#f9f9f9", borderRadius: 1.5, p: 1.5 }}>
        <Typography variant="body2" sx={{ whiteSpace: "pre-wrap", fontSize: TYPE.secondary.fontSize, color: "#333" }}>{current.content || "（无记录内容）"}</Typography>
      </Box>
    </Box>
  );
}

export default function RecordCard({ record, doctorId, onUpdated, onDeleted }) {
  const [expanded, setExpanded] = useState(false);
  const [editing, setEditing] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [current, setCurrent] = useState(record);

  async function handleDelete() {
    setDeleting(true);
    try { await deleteRecord(doctorId, current.id); onDeleted?.(current.id); }
    finally { setDeleting(false); setConfirmingDelete(false); }
  }

  return (
    <Box sx={{ borderBottom: "1px solid #f2f2f2" }}>
      <Box onClick={() => setExpanded((v) => !v)}>
        <RecordCardHeader current={current} expanded={expanded} dotColor={RECORD_DOT_COLORS[current.record_type] || "#bbb"} />
      </Box>
      {expanded && <RecordExpandedBody current={current} confirmingDelete={confirmingDelete} deleting={deleting} onConfirmDelete={handleDelete} onCancelDelete={() => setConfirmingDelete(false)} onOpenDelete={() => setConfirmingDelete(true)} onOpenEdit={() => setEditing(true)} />}
      <RecordEditDialog record={current} doctorId={doctorId} open={editing} onClose={() => setEditing(false)} onSaved={(updated) => { setCurrent(updated); onUpdated?.(updated); }} />
    </Box>
  );
}
