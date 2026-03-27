/**
 * @route /doctor/review/:recordId
 *
 * ReviewPage — route-level wrapper that owns API calls + polling,
 * delegates the review UI to ReviewSubpage.
 *
 * States:
 *  - Loading / polling: record is pending_review and no suggestions yet
 *  - Trigger button: record is completed but no suggestions
 *  - Review mode: suggestions exist, grouped by section
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { Box, Skeleton, Typography } from "@mui/material";
import { useApi } from "../../api/ApiContext";
import { useAppNavigate } from "../../hooks/useAppNavigate";
import { useDoctorStore } from "../../store/doctorStore";
import { STRUCTURED_FIELD_LABELS } from "./constants";
import ReviewSubpage from "./subpages/ReviewSubpage";
import { TYPE, COLOR } from "../../theme";

/* ── NHC field order for collapsible record summary ────────────────────────── */

const SUMMARY_FIELD_ORDER = [
  "department", "chief_complaint", "present_illness", "past_history",
  "allergy_history", "family_history", "personal_history", "marital_reproductive",
  "physical_exam", "specialist_exam", "auxiliary_exam",
  "diagnosis", "treatment_plan", "orders_followup",
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
    <Box sx={{ mt: 1, bgcolor: COLOR.white, borderTop: `0.5px solid ${COLOR.border}`, borderBottom: `0.5px solid ${COLOR.border}` }}>
      <Box
        onClick={() => setExpanded((v) => !v)}
        sx={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 1.5, px: 2, py: 1.25, cursor: "pointer", "&:active": { bgcolor: COLOR.surface } }}
      >
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap" }}>
            {patientName && (
              <Typography sx={{ fontSize: TYPE.action.fontSize, fontWeight: 500, color: COLOR.text1 }}>
                {patientName}
              </Typography>
            )}
            {date && (
              <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4 }}>
                {date}
              </Typography>
            )}
          </Box>
          {!expanded && (
            <Typography sx={{
              mt: 0.45, fontSize: TYPE.secondary.fontSize, color: COLOR.text3, lineHeight: 1.5,
              overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
            }}>
              {preview}
            </Typography>
          )}
        </Box>
        <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4, whiteSpace: "nowrap", pt: 0.2 }}>
          {expanded ? "收起 ▴" : "展开 ▾"}
        </Typography>
      </Box>

      {expanded && filledFields.length > 0 && (
        <Box>
          {filledFields.map((key) => (
            <Box key={key} sx={{ display: "flex", gap: 1, px: 2, py: 1, borderTop: `0.5px solid ${COLOR.borderLight}` }}>
              <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4, fontWeight: 500, flexShrink: 0, minWidth: 56 }}>
                {STRUCTURED_FIELD_LABELS[key]}
              </Typography>
              <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text2, whiteSpace: "pre-wrap", lineHeight: 1.6 }}>
                {structured[key]}
              </Typography>
            </Box>
          ))}
        </Box>
      )}

      {expanded && filledFields.length === 0 && record.content && (
        <Box sx={{ px: 2, py: 1, borderTop: `0.5px solid ${COLOR.borderLight}` }}>
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
    <Box sx={{ mt: 1, bgcolor: COLOR.white, borderTop: `0.5px solid ${COLOR.border}`, borderBottom: `0.5px solid ${COLOR.border}`, px: 2, py: 1.5 }}>
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

/* ── Main component ────────────────────────────────────────────────────────── */

export default function ReviewPage({ recordId }) {
  const navigate = useAppNavigate();
  const { getSuggestions, decideSuggestion, addSuggestion, triggerDiagnosis, finalizeReview, getTaskRecord } = useApi();
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

  /* ── Render ──────────────────────────────────────────────────────────────── */

  return (
    <>
      <ReviewSubpage
        record={record}
        suggestions={hasSuggestions ? suggestions : []}
        expandedId={expandedId}
        onToggle={handleToggle}
        onDecide={handleDecide}
        onAdd={handleAdd}
        onFinalize={handleFinalize}
        onBack={() => navigate(-1)}
        finalizing={finalizing}
      >
        {/* Record summary — always shown if record loaded */}
        <RecordSummary record={record} />

        {/* Loading state */}
        {loading && <LoadingSkeleton />}

        {/* Polling state: no suggestions yet, record pending review */}
        {!loading && !hasSuggestions && isPendingReview && <LoadingSkeleton />}

        {/* Trigger button: no suggestions, record NOT pending review */}
        {!loading && !hasSuggestions && !isPendingReview && (
          <Box sx={{ mt: 1, bgcolor: COLOR.white, borderTop: `0.5px solid ${COLOR.border}`, borderBottom: `0.5px solid ${COLOR.border}`, px: 2, py: 2.25, textAlign: "center" }}>
            <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text3, mb: 1 }}>
              可生成 AI 诊断建议
            </Typography>
            <Box
              onClick={handleTriggerDiagnosis}
              sx={{ display: "inline-flex", alignItems: "center", minHeight: 32, fontSize: TYPE.body.fontSize, color: COLOR.primary, cursor: "pointer", "&:active": { opacity: 0.6 } }}
            >
              请 AI 分析此病历
            </Box>
          </Box>
        )}
      </ReviewSubpage>

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
    </>
  );
}
