/**
 * 审核详情：结构化病历字段 + 问诊对话记录 + 确认/修改操作。
 * Drill-down from TasksSection review queue items.
 */
import { useCallback, useEffect, useState } from "react";
import {
  Alert, Box, CircularProgress, Collapse, Stack, TextField, Typography,
} from "@mui/material";
import { getReviewDetail, confirmReview, updateReviewField } from "../../api";
import PatientAvatar from "./PatientAvatar";
import { STRUCTURED_FIELD_LABELS } from "./constants";
import DiagnosisSection from "./DiagnosisSection";
import SubpageHeader from "./SubpageHeader";

const FIELD_ORDER = [
  "department", "chief_complaint", "present_illness", "past_history",
  "allergy_history", "personal_history", "marital_reproductive", "family_history",
  "physical_exam", "specialist_exam", "auxiliary_exam", "diagnosis",
  "treatment_plan", "orders_followup",
];

function FieldCard({ fieldKey, value, editing, onStartEdit, onSave, onCancel }) {
  const [draft, setDraft] = useState(value || "");
  const label = STRUCTURED_FIELD_LABELS[fieldKey] || fieldKey;

  useEffect(() => { setDraft(value || ""); }, [value]);

  if (editing) {
    return (
      <Box sx={{ mb: 1, p: "10px 12px", bgcolor: "#fff", borderRadius: "6px", borderLeft: "3px solid #07C160" }}>
        <Typography sx={{ fontSize: 11, color: "#999", mb: 0.5 }}>{label}</Typography>
        <TextField
          fullWidth multiline size="small" value={draft}
          onChange={(e) => setDraft(e.target.value)}
          sx={{ "& .MuiOutlinedInput-root": { fontSize: 14 } }}
        />
        <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
          <Box onClick={() => onSave(fieldKey, draft)}
            sx={{ px: 2, py: 0.7, bgcolor: "#07C160", color: "#fff", borderRadius: "4px",
              fontSize: 13, fontWeight: 600, cursor: "pointer", "&:active": { opacity: 0.7 } }}>
            保存
          </Box>
          <Box onClick={onCancel}
            sx={{ px: 2, py: 0.7, bgcolor: "#f5f5f5", color: "#666", borderRadius: "4px",
              fontSize: 13, cursor: "pointer", "&:active": { opacity: 0.7 } }}>
            取消
          </Box>
        </Stack>
      </Box>
    );
  }

  return (
    <Box onClick={() => onStartEdit(fieldKey)}
      sx={{ mb: 1, p: "10px 12px", bgcolor: "#f7f7f7", borderRadius: "6px", cursor: "pointer" }}>
      <Typography sx={{ fontSize: 11, color: "#999", mb: 0.3 }}>{label}</Typography>
      {value ? (
        <Typography sx={{ fontSize: 14, color: "#333", lineHeight: 1.6 }}>
          {value} <Typography component="span" sx={{ color: "#ccc", fontSize: 12 }}>✏️</Typography>
        </Typography>
      ) : (
        <Typography sx={{ fontSize: 14, color: "#ccc", fontStyle: "italic" }}>患者未提供</Typography>
      )}
    </Box>
  );
}

function ConversationHistory({ conversation }) {
  const [open, setOpen] = useState(false);
  if (!conversation || conversation.length === 0) return null;
  const turnCount = Math.ceil(conversation.length / 2);

  return (
    <Box sx={{ bgcolor: "#fff", borderRadius: 2, p: 2.5, mb: 1 }}>
      <Box onClick={() => setOpen(!open)} sx={{ display: "flex", alignItems: "center", gap: 0.8, cursor: "pointer" }}>
        <Typography sx={{ fontSize: 12, color: "#999" }}>{open ? "▼" : "▶"}</Typography>
        <Typography sx={{ fontSize: 14, fontWeight: 600, color: "#333" }}>问诊对话记录</Typography>
        <Typography sx={{ fontSize: 12, color: "#bbb" }}>({turnCount}轮)</Typography>
      </Box>
      <Collapse in={open}>
        <Box sx={{ mt: 1.5 }}>
          {conversation.map((msg, i) => (
            <Box key={i} sx={{ mb: 1, display: "flex", flexDirection: "column",
              alignItems: msg.role === "assistant" ? "flex-start" : "flex-end" }}>
              <Typography sx={{ fontSize: 11, color: "#bbb", mb: 0.3 }}>
                {msg.role === "assistant" ? "AI问诊" : "患者"}
              </Typography>
              <Box sx={{
                maxWidth: "85%", p: "8px 12px", borderRadius: "8px", fontSize: 13, lineHeight: 1.6,
                bgcolor: msg.role === "assistant" ? "#f0f0f0" : "#e8f5e9",
                color: "#333",
              }}>
                {msg.content}
              </Box>
            </Box>
          ))}
        </Box>
      </Collapse>
      {!open && (
        <Typography sx={{ fontSize: 13, color: "#999", mt: 0.8 }}>点击展开查看完整对话...</Typography>
      )}
    </Box>
  );
}

export default function ReviewDetail({ queueId, doctorId, onBack, onConfirmed }) {
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [editMode, setEditMode] = useState(false);
  const [editingField, setEditingField] = useState(null);
  const [confirming, setConfirming] = useState(false);
  const [saving, setSaving] = useState(false);

  const load = useCallback(() => {
    setLoading(true); setError("");
    getReviewDetail(queueId, doctorId)
      .then(setDetail)
      .catch((e) => setError(e.message || "加载失败"))
      .finally(() => setLoading(false));
  }, [queueId, doctorId]);

  useEffect(() => { load(); }, [load]);

  async function handleConfirm() {
    setConfirming(true);
    try {
      await confirmReview(queueId, doctorId);
      onConfirmed?.();
      onBack();
    } catch (e) { setError(e.message || "确认失败"); }
    finally { setConfirming(false); }
  }

  async function handleFieldSave(field, value) {
    setSaving(true);
    try {
      const result = await updateReviewField(queueId, doctorId, field, value);
      setDetail((prev) => ({
        ...prev,
        record: { ...prev.record, structured: result.structured },
      }));
      setEditingField(null);
    } catch (e) { setError(e.message || "保存失败"); }
    finally { setSaving(false); }
  }

  if (loading) {
    return (
      <Box sx={{ display: "flex", justifyContent: "center", alignItems: "center", height: "100%" }}>
        <CircularProgress size={24} sx={{ color: "#07C160" }} />
      </Box>
    );
  }

  const patient = detail?.patient;
  const structured = detail?.record?.structured || {};
  const age = patient?.year_of_birth ? new Date().getFullYear() - patient.year_of_birth : null;
  const isReviewed = detail?.status === "reviewed";

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%", bgcolor: "#f7f7f7" }}>
      <SubpageHeader title="审核详情" onBack={onBack} />

      {/* Content */}
      <Box sx={{ flex: 1, overflowY: "auto", p: 1 }}>
        {error && <Alert severity="error" sx={{ mb: 1 }} onClose={() => setError("")}>{error}</Alert>}

        {/* Patient header + structured fields */}
        <Box sx={{ bgcolor: "#fff", borderRadius: 2, p: 2.5, mb: 1 }}>
          {patient && (
            <Stack direction="row" alignItems="center" spacing={1.5} sx={{ mb: 2 }}>
              <PatientAvatar name={patient.name} size={44} />
              <Box>
                <Typography sx={{ fontWeight: 600, fontSize: 17 }}>{patient.name}</Typography>
                <Typography variant="caption" color="text.secondary">
                  {[
                    patient.gender ? ({ male: "男", female: "女" }[patient.gender] || patient.gender) : null,
                    age ? `${age}岁` : null,
                    "问诊总结",
                  ].filter(Boolean).join(" · ")}
                </Typography>
              </Box>
            </Stack>
          )}

          {FIELD_ORDER.map((key) => (
            <FieldCard
              key={key} fieldKey={key} value={structured[key]}
              editing={editMode && editingField === key}
              onStartEdit={(k) => { if (editMode) setEditingField(k); }}
              onSave={handleFieldSave}
              onCancel={() => setEditingField(null)}
            />
          ))}
        </Box>

        {/* Interview conversation */}
        <ConversationHistory conversation={detail?.conversation} />

        {/* Spacer for action bar */}
        <Box sx={{ height: 80 }} />
      </Box>

      {/* Sticky action bar */}
      {!isReviewed && (
        <Box sx={{ position: "fixed", bottom: 0, left: 0, right: 0, p: "12px 16px",
          bgcolor: "#fff", borderTop: "1px solid #e5e5e5", zIndex: 10 }}>
          <Stack direction="row" spacing={1.5}>
            <Box onClick={!confirming ? handleConfirm : undefined}
              sx={{ flex: 1, textAlign: "center", py: 1.3, borderRadius: "4px",
                bgcolor: confirming ? "#a5d6a7" : "#07C160", color: "#fff",
                fontWeight: 600, fontSize: 15, cursor: confirming ? "default" : "pointer",
                "&:active": confirming ? {} : { opacity: 0.7 } }}>
              {confirming ? "确认中..." : "✓ 确认审核"}
            </Box>
            <Box onClick={() => { setEditMode(!editMode); setEditingField(null); }}
              sx={{ flex: 1, textAlign: "center", py: 1.3, borderRadius: "4px",
                bgcolor: editMode ? "#e8f5e9" : "#fff", color: editMode ? "#07C160" : "#666",
                border: editMode ? "1px solid #07C160" : "1px solid #e5e5e5",
                fontWeight: 600, fontSize: 15, cursor: "pointer",
                "&:active": { opacity: 0.7 } }}>
              {editMode ? "退出修改" : "✏️ 修改"}
            </Box>
          </Stack>
        </Box>
      )}
    </Box>
  );
}
