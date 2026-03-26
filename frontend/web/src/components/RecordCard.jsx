/**
 * 病历卡片组件：可展开查看详情，支持编辑和删除操作。
 */
import { useState } from "react";
import { Box, Typography, useMediaQuery } from "@mui/material";
import { useTheme } from "@mui/material/styles";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import ExpandLessIcon from "@mui/icons-material/ExpandLess";
import EditOutlinedIcon from "@mui/icons-material/EditOutlined";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import { deleteRecord } from "../api";
import { RECORD_TYPE_LABEL, STRUCTURED_FIELD_LABELS } from "../pages/doctor/constants";
import RecordEditDialog from "./RecordEditDialog";
import { TYPE, ICON, COLOR } from "../theme";

const RECORD_DOT_COLORS = {
  visit: COLOR.primary, dictation: "#5b9bd5", import: "#e8833a",
  lab: "#9b59b6", imaging: "#1890ff", surgery: COLOR.danger,
  referral: "#16a085", interview_summary: "#8e44ad",
};

const SOAP_FIELD_ORDER = [
  "department", "chief_complaint", "present_illness", "past_history",
  "allergy_history", "family_history", "personal_history", "marital_reproductive",
  "physical_exam", "specialist_exam", "auxiliary_exam",
  "diagnosis", "treatment_plan", "orders_followup",
];

function StructuredFields({ structured }) {
  const filled = SOAP_FIELD_ORDER.filter(k => structured[k]);
  if (filled.length === 0) return null;
  return (
    <Box sx={{ mt: 0.8, bgcolor: COLOR.surfaceAlt, borderRadius: 1, border: `1px solid ${COLOR.borderLight}`, overflow: "hidden" }}>
      {filled.map((key, i) => (
        <Box key={key} sx={{ display: "flex", gap: 1.5, px: 1.5, py: 0.8,
          borderTop: i > 0 ? `1px solid ${COLOR.borderLight}` : "none" }}>
          <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text4, fontWeight: 400, flexShrink: 0, minWidth: 60 }}>
            {STRUCTURED_FIELD_LABELS[key]}
          </Typography>
          <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text2, whiteSpace: "pre-wrap", lineHeight: 1.6 }}>
            {structured[key]}
          </Typography>
        </Box>
      ))}
    </Box>
  );
}

function RecordCardHeader({ current, expanded, dotColor }) {
  const date = current.created_at ? current.created_at.slice(0, 10) : "—";
  const structured = current.structured || {};
  const hasStructured = Object.keys(structured).length > 0;
  // Collapsed preview: show chief_complaint or first line of content
  const preview = structured.chief_complaint || current.content || "（无记录内容）";
  return (
    <Box sx={{ display: "flex", alignItems: "flex-start", px: 2, py: 1.3, cursor: "pointer", "&:active": { bgcolor: COLOR.surfaceAlt } }}>
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
              <Typography key={i} sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.text4, bgcolor: COLOR.surfaceAlt, px: 0.6, borderRadius: 0.5 }}>
                {tag}
              </Typography>
            ))}
          </Box>
          <Typography sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.text4, flexShrink: 0, fontFamily: "monospace" }}>{date}</Typography>
        </Box>
        {!expanded ? (
          <Typography sx={{
            fontSize: TYPE.secondary.fontSize, color: preview !== "（无记录内容）" ? "text.primary" : COLOR.text4,
            overflow: "hidden", display: "-webkit-box",
            WebkitLineClamp: 2, WebkitBoxOrient: "vertical", whiteSpace: "pre-wrap",
          }}>
            {preview}
          </Typography>
        ) : hasStructured ? (
          <StructuredFields structured={structured} />
        ) : (
          <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: "text.primary", whiteSpace: "pre-wrap" }}>
            {current.content || "（无记录内容）"}
          </Typography>
        )}
      </Box>
      <Box sx={{ ml: 1, flexShrink: 0, display: "flex", alignItems: "center", mt: 0.2 }}>
        {expanded ? <ExpandLessIcon sx={{ fontSize: ICON.md, color: COLOR.text4 }} /> : <ExpandMoreIcon sx={{ fontSize: ICON.md, color: COLOR.text4 }} />}
      </Box>
    </Box>
  );
}

function DeleteConfirmRow({ deleting, onConfirm, onCancel }) {
  return (
    <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
      <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.danger }}>确认删除？</Typography>
      <Box onClick={!deleting ? onConfirm : undefined}
        sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.white, bgcolor: COLOR.danger, px: 1, py: 0.3, borderRadius: 1, cursor: deleting ? "default" : "pointer", "&:active": { opacity: 0.7 } }}>
        {deleting ? "删除中…" : "确认"}
      </Box>
      <Box onClick={onCancel} sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text3, cursor: "pointer", "&:active": { opacity: 0.7 } }}>
        取消
      </Box>
    </Box>
  );
}

function RecordExpandedBody({ current, confirmingDelete, deleting, onConfirmDelete, onCancelDelete, onOpenDelete, onOpenEdit }) {
  const structured = current.structured || {};
  const hasStructured = Object.keys(structured).length > 0;
  return (
    <Box sx={{ px: 2.5, pb: 1.5, pt: 0.5, borderTop: `0.5px solid ${COLOR.borderLight}` }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 2 }}>
        {confirmingDelete ? (
          <DeleteConfirmRow deleting={deleting} onConfirm={onConfirmDelete} onCancel={onCancelDelete} />
        ) : (
          <Box onClick={(e) => { e.stopPropagation(); onOpenDelete(); }}
            sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.danger, cursor: "pointer", display: "flex", alignItems: "center", gap: 0.5, "&:active": { opacity: 0.6 } }}>
            <DeleteOutlineIcon sx={{ fontSize: ICON.sm }} />删除
          </Box>
        )}
        <Box sx={{ flex: 1 }} />
        <Box onClick={(e) => { e.stopPropagation(); onOpenEdit(); }}
          sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.primary, cursor: "pointer", display: "flex", alignItems: "center", gap: 0.5, "&:active": { opacity: 0.6 } }}>
          <EditOutlinedIcon sx={{ fontSize: ICON.sm }} />编辑
        </Box>
      </Box>
    </Box>
  );
}

export default function RecordCard({ record, doctorId, onUpdated, onDeleted }) {
  const theme = useTheme();
  const isDesktop = useMediaQuery(theme.breakpoints.up("md"));
  const [expanded, setExpanded] = useState(isDesktop);
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
    <Box sx={{ borderBottom: `1px solid ${COLOR.borderLight}` }}>
      <Box onClick={() => setExpanded((v) => !v)}>
        <RecordCardHeader current={current} expanded={expanded} dotColor={RECORD_DOT_COLORS[current.record_type] || COLOR.text4} />
      </Box>
      {expanded && <RecordExpandedBody current={current} confirmingDelete={confirmingDelete} deleting={deleting} onConfirmDelete={handleDelete} onCancelDelete={() => setConfirmingDelete(false)} onOpenDelete={() => setConfirmingDelete(true)} onOpenEdit={() => setEditing(true)} />}
      <RecordEditDialog record={current} doctorId={doctorId} open={editing} onClose={() => setEditing(false)} onSaved={(updated) => { setCurrent(updated); onUpdated?.(updated); }} />
    </Box>
  );
}
