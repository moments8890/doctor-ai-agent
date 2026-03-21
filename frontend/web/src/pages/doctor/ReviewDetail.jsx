/**
 * 审核详情：结构化病历字段 + AI诊断建议chips + 问诊对话记录。
 * 确认/修改 按钮在顶栏。
 */
import { useCallback, useEffect, useState } from "react";
import {
  Alert, Box, CircularProgress, Collapse, Stack, TextField, Typography,
} from "@mui/material";
import { getReviewDetail, confirmReview, updateReviewField, getDiagnosis, decideDiagnosisItem, confirmDiagnosis } from "../../api";
import BarButton from "../../components/BarButton";
import PatientAvatar from "./PatientAvatar";
import DiagnosisSection from "./DiagnosisSection";
import { STRUCTURED_FIELD_LABELS } from "./constants";
import SubpageHeader from "./SubpageHeader";
import { TYPE, COLOR } from "../../theme";

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
/**
 * Build structured suggestions from diagnosis AI output.
 * Each suggestion = { brief: "chip label", detail: "patient-readable explanation" }
 */
function buildSuggestions(diagnosis) {
  if (!diagnosis?.ai_output) return {};
  const out = diagnosis.ai_output;
  const suggestions = {};

  // 初步诊断 ← differentials
  if (out.differentials?.length) {
    suggestions.diagnosis = out.differentials
      .filter((d) => d.condition)
      .map((d) => ({
        brief: d.confidence ? `${d.condition}（${d.confidence}）` : d.condition,
        detail: d.reasoning || d.condition,
      }));
  }

  // 治疗方案 ← treatment
  if (out.treatment?.length) {
    suggestions.treatment_plan = out.treatment
      .filter((t) => t.drug_class || t.description)
      .map((t) => ({
        brief: [t.intervention, t.drug_class].filter(Boolean).join(" · ") || t.description,
        detail: t.description || [t.intervention, t.drug_class].filter(Boolean).join("，"),
      }));
  }

  // 辅助检查 ← workup
  if (out.workup?.length) {
    suggestions.auxiliary_exam = out.workup
      .filter((w) => w.test)
      .map((w) => ({
        brief: w.urgency ? `${w.test}（${w.urgency}）` : w.test,
        detail: w.rationale || w.test,
      }));
  }

  // 医嘱及随访
  const followups = [];
  if (out.workup?.length) {
    out.workup.filter((w) => w.test && w.urgency !== "常规").forEach((w) => {
      followups.push({ brief: `${w.urgency}：${w.test}`, detail: `${w.urgency}安排${w.test}${w.rationale ? "，" + w.rationale : ""}` });
    });
  }
  if (out.treatment?.length) {
    out.treatment.filter((t) => t.description).forEach((t) => {
      followups.push({ brief: t.drug_class || t.intervention || "医嘱", detail: t.description });
    });
  }
  if (followups.length) suggestions.orders_followup = followups;

  return suggestions;
}

function FieldCard({ fieldKey, value, editing, suggestions, onStartEdit, onSave, onCancel, onApplySuggestion }) {
  const [draft, setDraft] = useState(value || "");
  // applied = [{ origIdx, detail (editable copy) }]
  const [applied, setApplied] = useState([]);
  const [expandedChip, setExpandedChip] = useState(null);
  const [editingTag, setEditingTag] = useState(null); // origIdx of tag being edited
  const [tagDraft, setTagDraft] = useState("");
  const [chipsOpen, setChipsOpen] = useState(false);
  const label = STRUCTURED_FIELD_LABELS[fieldKey] || fieldKey;

  useEffect(() => { setDraft(value || ""); }, [value]);

  const hasSuggestions = suggestions && suggestions.length > 0;
  const appliedIndices = applied.map((a) => a.origIdx);
  // Pool: unapplied, backfill to MAX_CHIPS
  const pool = hasSuggestions
    ? suggestions.map((s, i) => ({ ...s, _i: i })).filter((s) => !appliedIndices.includes(s._i)).slice(0, MAX_CHIPS)
    : [];

  function syncValue(newApplied) {
    const allDetails = newApplied.map((a) => a.detail);
    onApplySuggestion(fieldKey, allDetails.join("；") || "");
  }

  function handleApply(origIndex) {
    const s = suggestions[origIndex];
    const newApplied = [...applied, { origIdx: origIndex, detail: s.detail }];
    setApplied(newApplied);
    syncValue(newApplied);
    setExpandedChip(null);
    setTagDraft("");
  }

  function handleRemoveTag(origIndex) {
    const newApplied = applied.filter((a) => a.origIdx !== origIndex);
    setApplied(newApplied);
    syncValue(newApplied);
    if (editingTag === origIndex) setEditingTag(null);
  }

  function handleSaveTagEdit(origIndex) {
    const newApplied = applied.map((a) => a.origIdx === origIndex ? { ...a, detail: tagDraft } : a);
    setApplied(newApplied);
    syncValue(newApplied);
    setEditingTag(null);
  }

  // ── Editing mode (free text) ──
  if (editing) {
    const editPool = hasSuggestions ? suggestions.filter((s) => !draft.includes(s.detail)).slice(0, MAX_CHIPS) : [];
    return (
      <Box sx={{ py: 0.5, borderBottom: "0.5px solid #f0f0f0" }}>
        <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: "#999", mb: 0.3 }}>{label}</Typography>
        <TextField fullWidth multiline size="small" value={draft}
          onChange={(e) => setDraft(e.target.value)}
          sx={{ "& .MuiOutlinedInput-root": { fontSize: TYPE.body.fontSize } }} />
        {editPool.length > 0 && (
          <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.5, mt: 0.5 }}>
            {editPool.map((s, i) => (
              <Box key={i} onClick={() => setDraft((prev) => prev ? `${prev}；${s.detail}` : s.detail)}
                sx={{ px: 1, py: 0.3, borderRadius: "4px", fontSize: TYPE.caption.fontSize,
                  border: "1px solid #E5E5E5", bgcolor: "#fff", color: "#666",
                  cursor: "pointer", "&:active": { opacity: 0.7 } }}>
                {s.brief}
              </Box>
            ))}
          </Box>
        )}
        <Stack direction="row" spacing={1} sx={{ mt: 0.5 }}>
          <BarButton onClick={() => onSave(fieldKey, draft)}>保存</BarButton>
          <BarButton onClick={onCancel} color="#999">取消</BarButton>
        </Stack>
      </Box>
    );
  }

  // ── No suggestions ──
  if (!hasSuggestions) {
    return (
      <Box onClick={() => onStartEdit(fieldKey)}
        sx={{ py: 0.5, borderBottom: "0.5px solid #f0f0f0", cursor: "pointer",
          display: "flex", alignItems: "baseline", gap: 0.5 }}>
        <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: "#999", flexShrink: 0 }}>{label}：</Typography>
        <Typography sx={{ fontSize: TYPE.body.fontSize, color: value ? "#1A1A1A" : "#ccc", flex: 1, lineHeight: 1.6 }}>
          {value || "—"}
        </Typography>
      </Box>
    );
  }

  // ── Has suggestions ──
  return (
    <Box sx={{ py: 0.5, borderBottom: "0.5px solid #f0f0f0" }}>
      {/* Label row */}
      <Box sx={{ display: "flex", alignItems: "baseline", gap: 0.5 }}>
        <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: "#999", flexShrink: 0 }}>{label}：</Typography>
        {applied.length === 0 && !value && (
          <Typography onClick={() => setChipsOpen(!chipsOpen)}
            sx={{ fontSize: TYPE.caption.fontSize, color: "#F59E0B", fontWeight: 600, cursor: "pointer" }}>
            AI建议 ({suggestions.length}) {chipsOpen ? "▾" : "▸"}
          </Typography>
        )}
        {applied.length === 0 && value && (
          <Typography onClick={() => onStartEdit(fieldKey)}
            sx={{ fontSize: TYPE.body.fontSize, color: "#1A1A1A", flex: 1, lineHeight: 1.6, cursor: "pointer" }}>{value}</Typography>
        )}
      </Box>

      {/* Applied tags — tap to edit, × to remove */}
      {applied.length > 0 && (
        <Box sx={{ mt: 0.3, p: 0.5, bgcolor: "#fafafa", borderRadius: "4px", border: "1px solid #f0f0f0" }}>
          <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.5 }}>
            {applied.map((a) => (
              <Box key={a.origIdx}
                onClick={() => {
                  if (editingTag === a.origIdx) { setEditingTag(null); }
                  else { setEditingTag(a.origIdx); setTagDraft(a.detail); }
                }}
                sx={{ display: "inline-flex", alignItems: "center", gap: 0.3,
                  px: 0.8, py: 0.3, borderRadius: "4px", fontSize: TYPE.caption.fontSize,
                  bgcolor: editingTag === a.origIdx ? COLOR.success : COLOR.successLight,
                  color: editingTag === a.origIdx ? "#fff" : COLOR.success,
                  cursor: "pointer", "&:active": { opacity: 0.7 } }}>
                {suggestions[a.origIdx].brief}
                <Box component="span" onClick={(e) => { e.stopPropagation(); handleRemoveTag(a.origIdx); }}
                  sx={{ fontSize: 11, lineHeight: 1, ml: 0.3, opacity: 0.7 }}>×</Box>
              </Box>
            ))}
          </Box>
          {/* Inline edit for selected tag */}
          {editingTag != null && (
            <Box sx={{ mt: 0.5 }}>
              <TextField fullWidth multiline size="small" value={tagDraft}
                onChange={(e) => setTagDraft(e.target.value)}
                sx={{ "& .MuiOutlinedInput-root": { fontSize: TYPE.body.fontSize } }} />
              <Stack direction="row" spacing={1} sx={{ mt: 0.3 }}>
                <BarButton onClick={() => handleSaveTagEdit(editingTag)}>保存</BarButton>
                <BarButton onClick={() => setEditingTag(null)} color="#999">取消</BarButton>
              </Stack>
            </Box>
          )}
        </Box>
      )}

      {/* Chip pool — backfills to MAX_CHIPS */}
      {(chipsOpen || applied.length > 0) && pool.length > 0 && (
        <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.5, mt: 0.3 }}>
          {pool.map((s) => {
            const isExp = expandedChip === s._i;
            return (
              <Box key={s._i} onClick={() => setExpandedChip(isExp ? null : s._i)}
                sx={{ px: 1, py: 0.3, borderRadius: "4px", fontSize: TYPE.caption.fontSize,
                  border: isExp ? `1px solid ${COLOR.success}` : "1px solid #E5E5E5",
                  bgcolor: isExp ? COLOR.successLight : "#fff",
                  color: isExp ? COLOR.success : "#666",
                  cursor: "pointer", "&:active": { opacity: 0.7 } }}>
                {s.brief}
              </Box>
            );
          })}
        </Box>
      )}

      {/* Expanded detail — editable before adopting */}
      {expandedChip != null && suggestions[expandedChip] && (
        <Box sx={{ mt: 0.5, p: 1, bgcolor: "#f9f9f9", borderRadius: "4px", borderLeft: `3px solid ${COLOR.success}` }}>
          <TextField fullWidth multiline size="small"
            value={expandedChip != null ? (tagDraft || suggestions[expandedChip].detail) : ""}
            onChange={(e) => setTagDraft(e.target.value)}
            onFocus={() => { if (!tagDraft) setTagDraft(suggestions[expandedChip].detail); }}
            sx={{ "& .MuiOutlinedInput-root": { fontSize: TYPE.body.fontSize }, bgcolor: "#fff" }} />
          <Stack direction="row" spacing={1} sx={{ mt: 0.5 }}>
            <BarButton onClick={() => {
              const detail = tagDraft || suggestions[expandedChip].detail;
              const newApplied = [...applied, { origIdx: expandedChip, detail }];
              setApplied(newApplied);
              syncValue(newApplied);
              setExpandedChip(null);
              setTagDraft("");
            }}>采纳</BarButton>
            <BarButton onClick={() => { setExpandedChip(null); setTagDraft(""); }} color="#999">关闭</BarButton>
          </Stack>
        </Box>
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

  async function handleDiagnosisDecide(type, index, decision) {
    if (!diagnosis?.id) return;
    try {
      await decideDiagnosisItem(diagnosis.id, doctorId, type, index, decision);
      // Reload diagnosis to get updated doctor_decisions
      const updated = await getDiagnosis(detail.record.id, doctorId);
      setDiagnosis(updated);
    } catch (e) { setError(e.message || "操作失败"); }
  }

  async function handleConfirm() {
    setConfirming(true);
    try {
      // Confirm diagnosis first (if exists) to compute agreement_score
      if (diagnosis?.id && diagnosis?.status !== "confirmed") {
        try { await confirmDiagnosis(diagnosis.id, doctorId); } catch {}
      }
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
  async function handleApplySuggestion(field, newValue) {
    // Optimistic update — show immediately
    setDetail((prev) => {
      const structured = { ...(prev?.record?.structured || {}), [field]: newValue };
      return { ...prev, record: { ...prev.record, structured } };
    });
    // Persist to backend
    try {
      await updateReviewField(queueId, doctorId, field, newValue || "");
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

        {/* AI Diagnosis — confirm/reject each item */}
        {diagnosisLoading && (
          <Box sx={{ textAlign: "center", py: 1 }}>
            <CircularProgress size={16} sx={{ color: "#07C160" }} />
            <Typography sx={{ fontSize: TYPE.micro.fontSize, color: "#999", mt: 0.3 }}>AI诊断分析中...</Typography>
          </Box>
        )}
        {diagnosis && diagnosis.ai_output && !diagnosisLoading && (
          <Box sx={{ mb: 1 }}>
            <DiagnosisSection
              diagnosis={diagnosis}
              onDecide={handleDiagnosisDecide}
            />
          </Box>
        )}

        {/* Interview conversation */}
        <ConversationHistory conversation={detail?.conversation} />
      </Box>
    </Box>
  );
}
