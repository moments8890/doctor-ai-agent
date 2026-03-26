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
import {
  getSuggestions, decideSuggestion, addSuggestion,
  triggerDiagnosis, finalizeReview, getTaskRecord,
} from "../../api";
import { useDoctorStore } from "../../store/doctorStore";
import SubpageHeader from "../../components/SubpageHeader";
import DiagnosisCard from "../../components/doctor/DiagnosisCard";
import { STRUCTURED_FIELD_LABELS } from "./constants";
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

/* ── Inline add form ───────────────────────────────────────────────────────── */

function InlineAddForm({ onSubmit, onCancel }) {
  const [content, setContent] = useState("");
  const [detail, setDetail] = useState("");

  return (
    <Box sx={{ px: 2, pb: 1.25, borderTop: `0.5px solid ${COLOR.borderLight}` }}>
      <TextField
        fullWidth
        size="small"
        placeholder="建议内容"
        value={content}
        onChange={(e) => setContent(e.target.value)}
        sx={{ mt: 1.1, mb: 0.8, "& .MuiInputBase-root": { fontSize: TYPE.secondary.fontSize, bgcolor: "#fafafa" } }}
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
        sx={{ mb: 0.8, "& .MuiInputBase-root": { fontSize: TYPE.caption.fontSize, bgcolor: "#fafafa" } }}
      />
      <Box sx={{ display: "flex", gap: 2.2, justifyContent: "flex-end" }}>
        <Box
          onClick={onCancel}
          sx={{ minHeight: 32, display: "inline-flex", alignItems: "center", fontSize: TYPE.body.fontSize, color: COLOR.text4, cursor: "pointer", "&:active": { opacity: 0.6 } }}
        >
          取消
        </Box>
        <Box
          onClick={() => { if (content.trim()) onSubmit(content.trim(), detail.trim()); }}
          sx={{
            minHeight: 32, display: "inline-flex", alignItems: "center", fontSize: TYPE.body.fontSize, color: COLOR.primary,
            cursor: content.trim() ? "pointer" : "default", opacity: content.trim() ? 1 : 0.35, "&:active": content.trim() ? { opacity: 0.7 } : {},
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
    <Box sx={{ mt: 1, bgcolor: COLOR.white, borderTop: `0.5px solid ${COLOR.border}`, borderBottom: `0.5px solid ${COLOR.border}` }}>
      {/* Section header */}
      <Box sx={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 1.5, px: 2, py: 1.2 }}>
        <Box sx={{ minWidth: 0 }}>
          <Typography sx={{ fontSize: TYPE.action.fontSize, fontWeight: 500, color: COLOR.text1 }}>
            {label}
          </Typography>
          <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4, mt: 0.2 }}>
            {decidedCount}/{total} 已处理
          </Typography>
        </Box>
        <Box
          onClick={() => setAdding((prev) => !prev)}
          sx={{ fontSize: TYPE.caption.fontSize, color: adding ? COLOR.text4 : COLOR.primary, cursor: "pointer", whiteSpace: "nowrap", pt: 0.2, "&:active": { opacity: 0.6 } }}
        >
          {adding ? "取消" : "添加"}
        </Box>
      </Box>

      {/* Add button / form */}
      {adding ? (
        <InlineAddForm
          onSubmit={(content, detail) => { onAdd(sectionKey, content, detail); setAdding(false); }}
          onCancel={() => setAdding(false)}
        />
      ) : null}

      {/* Cards */}
      {(items || []).map((s) => (
        <DiagnosisCard
          key={s.id}
          suggestion={s}
          expanded={expandedId === s.id}
          onToggle={() => onToggle(s.id)}
          onDecide={onDecide}
        />
      ))}
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
        right={null}
      />

      {/* Scrollable content */}
      <Box sx={{ flex: 1, overflow: "auto", pb: hasSuggestions ? "88px" : 2 }}>
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

        {/* Suggestion sections */}
        {hasSuggestions && (
          <Box sx={{ pb: 1 }}>
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
          bgcolor: COLOR.white, borderTop: `0.5px solid ${COLOR.border}`,
          px: 2, pt: 0.9, pb: 1,
          paddingBottom: "calc(8px + env(safe-area-inset-bottom))",
        }}>
          <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <Box>
              <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4 }}>
                已处理
              </Typography>
              <Typography sx={{ fontSize: TYPE.body.fontSize, color: COLOR.text2 }}>
                {decidedCount}/{totalCount}
              </Typography>
            </Box>
            <Button
              variant="contained"
              onClick={handleFinalize}
              disabled={finalizing}
              sx={{
                bgcolor: COLOR.primary, color: COLOR.white,
                fontSize: TYPE.body.fontSize, fontWeight: 600,
                minHeight: 36, px: 2.2, py: 0, borderRadius: 1,
                "&:hover": { bgcolor: COLOR.primary },
                "&:disabled": { bgcolor: COLOR.border, color: COLOR.text4 },
              }}
            >
              {finalizing ? "提交中..." : "完成审核"}
            </Button>
          </Box>
          <Typography sx={{ fontSize: 10, color: "#c0c0c0", textAlign: "center", mt: 0.6 }}>
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
