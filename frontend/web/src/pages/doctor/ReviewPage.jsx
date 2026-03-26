/**
 * @route /doctor/review/:recordId
 *
 * ReviewPage — full-page review subpage.
 *
 * Shows AI diagnosis suggestions for a medical record, grouped into three
 * sections (differential, workup, treatment). Each suggestion is rendered
 * as a DiagnosisCard with inline confirm/reject/edit actions.
 *
 * States:
 *  - Loading / polling: record is pending_review and no suggestions yet
 *  - Trigger button: record is completed but no suggestions
 *  - Review mode: suggestions exist, grouped by section
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Box, Button, Skeleton, TextField, Typography } from "@mui/material";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import ExpandLessIcon from "@mui/icons-material/ExpandLess";
import {
  getSuggestions, decideSuggestion, addSuggestion,
  triggerDiagnosis, finalizeReview, getTaskRecord,
} from "../../api";
import { useDoctorStore } from "../../store/doctorStore";
import SubpageHeader from "../../components/SubpageHeader";
import DiagnosisCard from "./components/DiagnosisCard";
import { STRUCTURED_FIELD_LABELS } from "./components/constants";
import { TYPE, COLOR } from "../../theme";

/* ── NHC field order for collapsible record summary ────────────────────────── */

const SUMMARY_FIELD_ORDER = [
  "department", "chief_complaint", "present_illness", "past_history",
  "allergy_history", "family_history", "personal_history", "marital_reproductive",
  "physical_exam", "specialist_exam", "auxiliary_exam",
  "diagnosis", "treatment_plan", "orders_followup",
];

/* ── Section config ────────────────────────────────────────────────────────── */

const SECTIONS = [
  { key: "differential", label: "鉴别诊断" },
  { key: "workup",       label: "检查建议" },
  { key: "treatment",    label: "治疗方向" },
];

/* ── Collapsible record summary ────────────────────────────────────────────── */

function RecordSummary({ record }) {
  const [expanded, setExpanded] = useState(false);
  if (!record) return null;

  const structured = record.structured || {};
  const filledFields = SUMMARY_FIELD_ORDER.filter((k) => structured[k]);
  const preview = structured.chief_complaint || record.content || "(无记录)";
  const patientName = record.patient_name || "";
  const date = record.created_at ? record.created_at.slice(0, 10) : "";

  return (
    <Box sx={{ mx: 1.5, mt: 1.5, bgcolor: COLOR.white, borderRadius: 1.5, border: `1px solid ${COLOR.borderLight}`, overflow: "hidden" }}>
      <Box
        onClick={() => setExpanded((v) => !v)}
        sx={{ display: "flex", alignItems: "center", px: 1.5, py: 1, cursor: "pointer", "&:active": { bgcolor: COLOR.surface } }}
      >
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 0.3 }}>
            {patientName && (
              <Typography sx={{ fontSize: TYPE.heading.fontSize, fontWeight: 600, color: COLOR.text2 }}>
                {patientName}
              </Typography>
            )}
            {date && (
              <Typography sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.text4, fontFamily: "monospace" }}>
                {date}
              </Typography>
            )}
          </Box>
          {!expanded && (
            <Typography sx={{
              fontSize: TYPE.secondary.fontSize, color: COLOR.text3,
              overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
            }}>
              {preview}
            </Typography>
          )}
        </Box>
        {expanded
          ? <ExpandLessIcon sx={{ fontSize: 18, color: COLOR.text4, flexShrink: 0, ml: 1 }} />
          : <ExpandMoreIcon sx={{ fontSize: 18, color: COLOR.text4, flexShrink: 0, ml: 1 }} />}
      </Box>

      {expanded && filledFields.length > 0 && (
        <Box sx={{ px: 1.5, pb: 1.5 }}>
          <Box sx={{ bgcolor: "#fafafa", borderRadius: 1, border: `1px solid ${COLOR.borderLight}`, overflow: "hidden" }}>
            {filledFields.map((key, i) => (
              <Box key={key} sx={{ display: "flex", gap: 1, px: 1.2, py: 0.7, borderTop: i > 0 ? `1px solid ${COLOR.borderLight}` : "none" }}>
                <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4, fontWeight: 500, flexShrink: 0, minWidth: 56 }}>
                  {STRUCTURED_FIELD_LABELS[key]}
                </Typography>
                <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text2, whiteSpace: "pre-wrap", lineHeight: 1.6 }}>
                  {structured[key]}
                </Typography>
              </Box>
            ))}
          </Box>
        </Box>
      )}

      {expanded && filledFields.length === 0 && record.content && (
        <Box sx={{ px: 1.5, pb: 1.5 }}>
          <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text2, whiteSpace: "pre-wrap", lineHeight: 1.6 }}>
            {record.content}
          </Typography>
        </Box>
      )}
    </Box>
  );
}

/* ── Loading skeleton ──────────────────────────────────────────────────────── */

function LoadingSkeleton() {
  return (
    <Box sx={{ px: 1.5, pt: 2 }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 2 }}>
        <Skeleton variant="circular" width={20} height={20} animation="wave" />
        <Typography sx={{ fontSize: TYPE.heading.fontSize, color: COLOR.text3 }}>
          AI 正在分析...
        </Typography>
      </Box>
      {[1, 2, 3].map((i) => (
        <Skeleton key={i} variant="rounded" height={48} sx={{ mb: 1, borderRadius: 1 }} animation="wave" />
      ))}
    </Box>
  );
}

/* ── Inline add form ───────────────────────────────────────────────────────── */

function InlineAddForm({ section, onSubmit, onCancel }) {
  const [content, setContent] = useState("");
  const [detail, setDetail] = useState("");

  return (
    <Box sx={{ mx: 1.5, mt: 1, p: 1.5, bgcolor: COLOR.white, borderRadius: 1, border: `1px dashed ${COLOR.border}` }}>
      <TextField
        fullWidth
        size="small"
        placeholder="建议内容"
        value={content}
        onChange={(e) => setContent(e.target.value)}
        sx={{ mb: 1, "& .MuiInputBase-root": { fontSize: TYPE.secondary.fontSize } }}
      />
      <TextField
        fullWidth
        size="small"
        placeholder="详细说明（可选）"
        value={detail}
        onChange={(e) => setDetail(e.target.value)}
        multiline
        minRows={1}
        maxRows={3}
        sx={{ mb: 1, "& .MuiInputBase-root": { fontSize: TYPE.caption.fontSize } }}
      />
      <Box sx={{ display: "flex", gap: 1, justifyContent: "flex-end" }}>
        <Box
          onClick={onCancel}
          sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4, cursor: "pointer", px: 1.5, py: 0.5, "&:active": { opacity: 0.6 } }}
        >
          取消
        </Box>
        <Box
          onClick={() => { if (content.trim()) onSubmit(content.trim(), detail.trim()); }}
          sx={{
            fontSize: TYPE.caption.fontSize, color: COLOR.white, bgcolor: COLOR.primary,
            borderRadius: "4px", cursor: "pointer", px: 1.5, py: 0.5,
            opacity: content.trim() ? 1 : 0.4, "&:active": { opacity: 0.7 },
          }}
        >
          添加
        </Box>
      </Box>
    </Box>
  );
}

/* ── Suggestion section ────────────────────────────────────────────────────── */

function SuggestionSection({ sectionKey, label, items, expandedId, onToggle, onDecide, onAdd }) {
  const [adding, setAdding] = useState(false);
  if (!items || items.length === 0) {
    if (!adding) return null;
  }

  const decidedCount = (items || []).filter((s) => s.decision).length;
  const total = (items || []).length;

  return (
    <Box sx={{ mb: 2 }}>
      {/* Section header */}
      <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", px: 1.5, mb: 0.5 }}>
        <Typography sx={{ fontSize: TYPE.heading.fontSize, fontWeight: 600, color: COLOR.text2 }}>
          {label}
          <Typography component="span" sx={{ fontSize: TYPE.caption.fontSize, fontWeight: 400, color: COLOR.text4, ml: 1 }}>
            {decidedCount}/{total}
          </Typography>
        </Typography>
      </Box>

      {/* Add button / form — always on top, prominent */}
      {adding ? (
        <InlineAddForm
          section={sectionKey}
          onSubmit={(content, detail) => { onAdd(sectionKey, content, detail); setAdding(false); }}
          onCancel={() => setAdding(false)}
        />
      ) : (
        <Box
          onClick={() => setAdding(true)}
          sx={{
            mx: 1.5, mb: 0.5, px: 1.5, py: 1,
            fontSize: TYPE.body.fontSize, color: COLOR.primary, fontWeight: 500,
            border: `1px dashed ${COLOR.primary}`, borderRadius: 1,
            textAlign: "center",
            cursor: "pointer", "&:active": { opacity: 0.6 },
          }}
        >
          + 添加
        </Box>
      )}

      {/* Cards */}
      <Box sx={{ mx: 1.5, borderRadius: 1, overflow: "hidden", border: items && items.length > 0 ? `0.5px solid ${COLOR.borderLight}` : "none" }}>
        {(items || []).map((s, i) => (
          <Box key={s.id} sx={{ borderTop: i > 0 ? `0.5px solid ${COLOR.borderLight}` : "none" }}>
            <DiagnosisCard
              suggestion={s}
              expanded={expandedId === s.id}
              onToggle={() => onToggle(s.id)}
              onDecide={onDecide}
            />
          </Box>
        ))}
      </Box>
    </Box>
  );
}

/* ── Main component ────────────────────────────────────────────────────────── */

export default function ReviewPage({ recordId }) {
  const navigate = useNavigate();
  const { doctorId } = useDoctorStore();

  const [record, setRecord] = useState(null);
  const [suggestions, setSuggestions] = useState(null); // null = not loaded, [] = empty
  const [expandedId, setExpandedId] = useState(null);
  const [loading, setLoading] = useState(true);
  const [finalizing, setFinalizing] = useState(false);
  const [toast, setToast] = useState(null);
  const pollRef = useRef(null);

  /* ── Fetch record + suggestions on mount ─────────────────────────────────── */

  const fetchSuggestions = useCallback(async () => {
    try {
      const data = await getSuggestions(recordId, doctorId);
      const items = Array.isArray(data) ? data : (data.suggestions || data.items || []);
      if (items.length > 0) {
        setSuggestions(items);
        // Stop polling once we have suggestions
        if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
        return true;
      }
      setSuggestions([]);
      return false;
    } catch {
      setSuggestions([]);
      return false;
    }
  }, [recordId, doctorId]);

  useEffect(() => {
    if (!recordId || !doctorId) return;

    async function init() {
      setLoading(true);
      try {
        const rec = await getTaskRecord(recordId, doctorId);
        setRecord(rec);
      } catch {
        // record fetch failed
      }
      const hasSuggestions = await fetchSuggestions();
      setLoading(false);

      // Start polling if record is pending_review and no suggestions yet
      if (!hasSuggestions) {
        pollRef.current = setInterval(async () => {
          const found = await fetchSuggestions();
          if (found && pollRef.current) {
            clearInterval(pollRef.current);
            pollRef.current = null;
          }
        }, 3000);
      }
    }
    init();

    return () => { if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; } };
  }, [recordId, doctorId, fetchSuggestions]);

  /* ── Handlers ────────────────────────────────────────────────────────────── */

  function handleToggle(id) {
    setExpandedId((prev) => (prev === id ? null : id));
  }

  async function handleDecide(suggestionId, decision, opts) {
    try {
      await decideSuggestion(suggestionId, decision, opts);
      setSuggestions((prev) =>
        (prev || []).map((s) =>
          s.id === suggestionId
            ? { ...s, decision, ...(opts.edited_text ? { edited_text: opts.edited_text } : {}), ...(opts.reason ? { reason: opts.reason } : {}) }
            : s
        )
      );
    } catch {
      showToast("操作失败");
    }
  }

  async function handleAdd(section, content, detail) {
    try {
      const created = await addSuggestion(recordId, doctorId, section, content, detail || undefined);
      setSuggestions((prev) => [...(prev || []), created]);
    } catch {
      showToast("添加失败");
    }
  }

  async function handleTriggerDiagnosis() {
    try {
      await triggerDiagnosis(recordId, doctorId);
      showToast("已提交分析请求");
      // Start polling for results
      pollRef.current = setInterval(async () => {
        const found = await fetchSuggestions();
        if (found && pollRef.current) {
          clearInterval(pollRef.current);
          pollRef.current = null;
        }
      }, 3000);
    } catch {
      showToast("请求失败");
    }
  }

  async function handleFinalize() {
    if (finalizing) return;
    setFinalizing(true);
    try {
      await finalizeReview(recordId, doctorId);
      showToast("审核完成");
      setTimeout(() => navigate(-1), 600);
    } catch {
      showToast("提交失败");
      setFinalizing(false);
    }
  }

  function showToast(msg) {
    setToast(msg);
    setTimeout(() => setToast(null), 2000);
  }

  /* ── Derived state ───────────────────────────────────────────────────────── */

  const hasSuggestions = suggestions && suggestions.length > 0;
  const isPendingReview = record?.review_status === "pending_review" || record?.status === "pending_review";

  // Group suggestions by section
  const grouped = {};
  SECTIONS.forEach((s) => { grouped[s.key] = []; });
  (suggestions || []).forEach((s) => {
    if (grouped[s.section]) grouped[s.section].push(s);
  });

  const totalCount = (suggestions || []).length;
  const decidedCount = (suggestions || []).filter((s) => s.decision).length;

  /* ── Render ──────────────────────────────────────────────────────────────── */

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%", bgcolor: COLOR.surfaceAlt }}>
      {/* Header */}
      <SubpageHeader
        title="诊断审核"
        onBack={() => navigate(-1)}
        right={
          hasSuggestions ? (
            <Box
              onClick={handleFinalize}
              sx={{
                fontSize: TYPE.action.fontSize, fontWeight: 500, color: COLOR.primary,
                cursor: "pointer", px: 1, "&:active": { opacity: 0.5 },
              }}
            >
              {finalizing ? "提交中..." : "完成审核"}
            </Box>
          ) : null
        }
      />

      {/* Scrollable content */}
      <Box sx={{ flex: 1, overflow: "auto", pb: hasSuggestions ? "110px" : 2 }}>
        {/* Record summary — always shown if record loaded */}
        <RecordSummary record={record} />

        {/* Loading state */}
        {loading && <LoadingSkeleton />}

        {/* Polling state: no suggestions yet, record pending review */}
        {!loading && !hasSuggestions && isPendingReview && <LoadingSkeleton />}

        {/* Trigger button: no suggestions, record NOT pending review */}
        {!loading && !hasSuggestions && !isPendingReview && (
          <Box sx={{ display: "flex", justifyContent: "center", mt: 4 }}>
            <Button
              variant="outlined"
              onClick={handleTriggerDiagnosis}
              sx={{
                borderColor: COLOR.primary, color: COLOR.primary,
                fontSize: TYPE.body.fontSize, fontWeight: 500,
                px: 3, py: 1.2, borderRadius: 2,
                "&:hover": { borderColor: COLOR.primary, bgcolor: COLOR.primaryLight },
              }}
            >
              诊断建议 — 请AI分析此病历
            </Button>
          </Box>
        )}

        {/* Suggestion sections */}
        {hasSuggestions && (
          <Box sx={{ mt: 2 }}>
            {SECTIONS.map((sec) => (
              <SuggestionSection
                key={sec.key}
                sectionKey={sec.key}
                label={sec.label}
                items={grouped[sec.key]}
                expandedId={expandedId}
                onToggle={handleToggle}
                onDecide={handleDecide}
                onAdd={handleAdd}
              />
            ))}
          </Box>
        )}
      </Box>

      {/* Sticky bottom bar */}
      {hasSuggestions && (
        <Box sx={{
          position: "absolute", bottom: 0, left: 0, right: 0,
          bgcolor: COLOR.surface, borderTop: `1px solid ${COLOR.border}`,
          px: 2, pt: 1.2, pb: 1.5,
          paddingBottom: "calc(12px + env(safe-area-inset-bottom))",
        }}>
          <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text3 }}>
              {decidedCount}/{totalCount} 已处理
            </Typography>
            <Button
              variant="contained"
              onClick={handleFinalize}
              disabled={finalizing}
              sx={{
                bgcolor: COLOR.primary, color: COLOR.white,
                fontSize: TYPE.body.fontSize, fontWeight: 600,
                px: 3, py: 0.8, borderRadius: 1,
                "&:hover": { bgcolor: COLOR.primary },
                "&:disabled": { bgcolor: COLOR.border, color: COLOR.text4 },
              }}
            >
              {finalizing ? "提交中..." : "完成审核"}
            </Button>
          </Box>
          <Typography sx={{ fontSize: 10, color: "#ccc", textAlign: "center", mt: 0.8 }}>
            AI建议仅供参考
          </Typography>
        </Box>
      )}

      {/* Toast */}
      {toast && (
        <Box sx={{
          position: "fixed", top: "20%", left: "50%", transform: "translateX(-50%)",
          bgcolor: "rgba(0,0,0,0.7)", color: "#fff", px: 3, py: 1.5,
          borderRadius: 2, fontSize: TYPE.body.fontSize, zIndex: 9999,
          pointerEvents: "none",
        }}>
          {toast}
        </Box>
      )}
    </Box>
  );
}
