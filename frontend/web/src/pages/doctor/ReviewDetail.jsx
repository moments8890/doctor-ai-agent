/**
 * 审核详情：结构化病历字段 + AI诊断建议chips + 问诊对话记录。
 * 确认/修改 按钮在顶栏。
 */
import { useCallback, useEffect, useState } from "react";
import {
  Alert, Box, CircularProgress, Collapse, Stack, TextField, Typography,
} from "@mui/material";
import { getReviewDetail, confirmReview, updateReviewField, getDiagnosis } from "../../api";
import BarButton from "../../components/BarButton";
import SuggestionChips from "../../components/SuggestionChips";
import PatientAvatar from "./PatientAvatar";
import { STRUCTURED_FIELD_LABELS } from "./constants";
import SubpageHeader from "./SubpageHeader";
import { TYPE } from "../../theme";

const FIELD_ORDER = [
  "department", "chief_complaint", "present_illness", "past_history",
  "allergy_history", "personal_history", "marital_reproductive", "family_history",
  "physical_exam", "specialist_exam", "auxiliary_exam", "diagnosis",
  "treatment_plan", "orders_followup",
];

// Max visible suggestion chips per field
const MAX_CHIPS = 3;

/**
 * Build suggestion map from diagnosis AI output.
 * Returns { diagnosis: string[], treatment_plan: string[] }
 */
function buildSuggestions(diagnosis) {
  if (!diagnosis?.ai_output) return {};
  const out = diagnosis.ai_output;
  const suggestions = {};

  // 初步诊断 ← top differentials
  if (out.differentials?.length) {
    suggestions.diagnosis = out.differentials
      .filter((d) => d.condition)
      .map((d) => d.confidence ? `${d.condition}（${d.confidence}）` : d.condition);
  }

  // 治疗方案 ← treatment descriptions
  if (out.treatment?.length) {
    suggestions.treatment_plan = out.treatment
      .filter((t) => t.drug_class || t.description)
      .map((t) => {
        const parts = [t.intervention, t.drug_class, t.description].filter(Boolean);
        return parts.join(" · ");
      });
  }

  // 检查建议 → auxiliary_exam
  if (out.workup?.length) {
    suggestions.auxiliary_exam = out.workup
      .filter((w) => w.test)
      .map((w) => w.urgency ? `${w.test}（${w.urgency}）` : w.test);
  }

  // 医嘱及随访 ← combine urgent workup + treatment follow-up
  const followups = [];
  if (out.workup?.length) {
    out.workup.filter((w) => w.test && w.urgency !== "常规").forEach((w) => {
      followups.push(`${w.urgency}完成${w.test}`);
    });
  }
  if (out.treatment?.length) {
    out.treatment.filter((t) => t.description).forEach((t) => {
      followups.push(t.description);
    });
  }
  if (followups.length) suggestions.orders_followup = followups;

  return suggestions;
}

function FieldCard({ fieldKey, value, editing, suggestions, onStartEdit, onSave, onCancel, onApplySuggestion }) {
  const [draft, setDraft] = useState(value || "");
  const label = STRUCTURED_FIELD_LABELS[fieldKey] || fieldKey;

  useEffect(() => { setDraft(value || ""); }, [value]);

  const hasSuggestions = suggestions && suggestions.length > 0;
  const unselected = hasSuggestions ? suggestions.filter((s) => !draft.includes(s)) : [];
  const visibleUnselected = unselected.slice(0, MAX_CHIPS);

  function handleChipAdd(text) {
    setDraft((prev) => prev ? `${prev}；${text}` : text);
  }

  // Editing mode — same for all fields
  if (editing) {
    return (
      <Box sx={{ py: 0.5, borderBottom: "0.5px solid #f0f0f0" }}>
        <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: "#999", mb: 0.3 }}>{label}</Typography>
        <TextField
          fullWidth multiline size="small" value={draft}
          onChange={(e) => setDraft(e.target.value)}
          sx={{ "& .MuiOutlinedInput-root": { fontSize: TYPE.body.fontSize } }}
        />
        {/* AI suggestion chips below the text field */}
        {visibleUnselected.length > 0 && (
          <SuggestionChips items={visibleUnselected} selected={[]} onToggle={handleChipAdd} />
        )}
        <Stack direction="row" spacing={1} sx={{ mt: 0.5 }}>
          <BarButton onClick={() => onSave(fieldKey, draft)} color="#07C160">保存</BarButton>
          <BarButton onClick={onCancel} color="#999">取消</BarButton>
        </Stack>
      </Box>
    );
  }

  // Read-only mode
  return (
    <Box onClick={() => onStartEdit(fieldKey)}
      sx={{ py: 0.5, borderBottom: "0.5px solid #f0f0f0", cursor: "pointer", display: "flex", alignItems: "baseline", gap: 0.5 }}>
      <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: "#999", flexShrink: 0 }}>{label}：</Typography>
      {value ? (
        <Typography sx={{ fontSize: TYPE.body.fontSize, color: "#1A1A1A", flex: 1, lineHeight: 1.6 }}>{value}</Typography>
      ) : hasSuggestions ? (
        <Typography sx={{ fontSize: TYPE.caption.fontSize, color: "#F59E0B", fontWeight: 600 }}>AI建议 ▸</Typography>
      ) : (
        <Typography sx={{ fontSize: TYPE.body.fontSize, color: "#ccc", flex: 1 }}>—</Typography>
      )}
    </Box>
  );
}

function ConversationHistory({ conversation }) {
  const [open, setOpen] = useState(false);
  if (!conversation || conversation.length === 0) return null;
  const turnCount = Math.ceil(conversation.length / 2);

  return (
    <Box sx={{ bgcolor: "#fff", borderRadius: "6px", p: 2, mb: 1 }}>
      <Box onClick={() => setOpen(!open)} sx={{ display: "flex", alignItems: "center", gap: 0.8, cursor: "pointer" }}>
        <Typography sx={{ fontSize: TYPE.caption.fontSize, color: "#999" }}>{open ? "▼" : "▶"}</Typography>
        <Typography sx={{ fontSize: TYPE.secondary.fontSize, fontWeight: 600, color: "#333" }}>问诊对话记录</Typography>
        <Typography sx={{ fontSize: TYPE.caption.fontSize, color: "#bbb" }}>({turnCount}轮)</Typography>
      </Box>
      <Collapse in={open}>
        <Box sx={{ mt: 1 }}>
          {conversation.map((msg, i) => (
            <Box key={i} sx={{ mb: 0.8, display: "flex", flexDirection: "column",
              alignItems: msg.role === "assistant" ? "flex-start" : "flex-end" }}>
              <Typography sx={{ fontSize: TYPE.micro.fontSize, color: "#bbb", mb: 0.2 }}>
                {msg.role === "assistant" ? "AI问诊" : "患者"}
              </Typography>
              <Box sx={{
                maxWidth: "85%", p: "6px 10px", borderRadius: "6px", fontSize: TYPE.caption.fontSize, lineHeight: 1.5,
                bgcolor: msg.role === "assistant" ? "#f0f0f0" : "#e8f5e9", color: "#333",
              }}>
                {msg.content}
              </Box>
            </Box>
          ))}
        </Box>
      </Collapse>
      {!open && (
        <Typography sx={{ fontSize: TYPE.caption.fontSize, color: "#999", mt: 0.5 }}>点击展开...</Typography>
      )}
    </Box>
  );
}

export default function ReviewDetail({ queueId, doctorId, onBack, onConfirmed, isMobile: isMobileProp }) {
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [editMode, setEditMode] = useState(false);
  const [editingField, setEditingField] = useState(null);
  const [confirming, setConfirming] = useState(false);
  const [saving, setSaving] = useState(false);
  const [diagnosis, setDiagnosis] = useState(null);
  const [diagnosisLoading, setDiagnosisLoading] = useState(false);

  const load = useCallback(() => {
    setLoading(true); setError("");
    getReviewDetail(queueId, doctorId)
      .then(setDetail)
      .catch((e) => setError(e.message || "加载失败"))
      .finally(() => setLoading(false));
  }, [queueId, doctorId]);

  useEffect(() => { load(); }, [load]);

  // Fetch diagnosis when detail loads
  useEffect(() => {
    if (!detail?.record?.id || !doctorId) return;
    setDiagnosisLoading(true);
    getDiagnosis(detail.record.id, doctorId)
      .then(setDiagnosis)
      .catch(() => {})
      .finally(() => setDiagnosisLoading(false));
  }, [detail?.record?.id, doctorId]);

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

  // Apply suggestion chip → save to backend immediately
  async function handleApplySuggestion(field, value) {
    try {
      const result = await updateReviewField(queueId, doctorId, field, value);
      setDetail((prev) => ({
        ...prev,
        record: { ...prev.record, structured: result.structured },
      }));
    } catch (e) { setError(e.message || "保存失败"); }
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
  const suggestions = buildSuggestions(diagnosis);

  // Top bar actions
  const headerRight = (
    <Box sx={{ display: "flex", gap: 0.5 }}>
      {!isReviewed && !editMode && <BarButton onClick={handleConfirm} loading={confirming}>确认</BarButton>}
      <BarButton onClick={() => { setEditMode(!editMode); setEditingField(null); }}
        color={editMode ? "#FA5151" : "#999"}>
        {editMode ? "取消" : "修改"}
      </BarButton>
    </Box>
  );

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%", bgcolor: "#f7f7f7" }}>
      <SubpageHeader title={patient?.name || "审核详情"}
        onBack={isMobileProp ? onBack : undefined}
        right={headerRight}
      />

      {/* Content */}
      <Box sx={{ flex: 1, overflowY: "auto", p: 1 }}>
        {error && <Alert severity="error" sx={{ mb: 1 }} onClose={() => setError("")}>{error}</Alert>}

        {/* Patient info line */}
        {patient && (
          <Box sx={{ display: "flex", alignItems: "center", gap: 1, px: 1, py: 0.8 }}>
            <PatientAvatar name={patient.name} size={28} />
            <Typography sx={{ fontSize: TYPE.caption.fontSize, color: "#999" }}>
              {[
                patient.gender ? ({ male: "男", female: "女" }[patient.gender] || patient.gender) : null,
                age ? `${age}岁` : null,
                "问诊总结",
              ].filter(Boolean).join(" · ")}
            </Typography>
          </Box>
        )}

        {/* Structured fields with AI suggestions */}
        <Box sx={{ bgcolor: "#fff", px: 1.5, py: 0.5, mb: 1 }}>
          {FIELD_ORDER.map((key) => (
            <FieldCard
              key={key} fieldKey={key} value={structured[key]}
              editing={editMode && editingField === key}
              suggestions={suggestions[key]}
              onStartEdit={(k) => { if (editMode) setEditingField(k); }}
              onSave={handleFieldSave}
              onCancel={() => setEditingField(null)}
              onApplySuggestion={handleApplySuggestion}
            />
          ))}
        </Box>

        {/* Diagnosis loading indicator */}
        {diagnosisLoading && (
          <Box sx={{ textAlign: "center", py: 1 }}>
            <CircularProgress size={16} sx={{ color: "#07C160" }} />
            <Typography sx={{ fontSize: TYPE.micro.fontSize, color: "#999", mt: 0.3 }}>AI诊断分析中...</Typography>
          </Box>
        )}

        {/* Interview conversation */}
        <ConversationHistory conversation={detail?.conversation} />
      </Box>
    </Box>
  );
}
