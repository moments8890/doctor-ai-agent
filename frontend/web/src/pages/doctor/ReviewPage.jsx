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
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Box, Skeleton, Typography } from "@mui/material";
import { useApi } from "../../api/ApiContext";
import { useAppNavigate } from "../../hooks/useAppNavigate";
import { useDoctorStore } from "../../store/doctorStore";
import {
  STRUCTURED_FIELD_LABELS,
  getOnboardingState,
  markOnboardingStep,
  ONBOARDING_STEP,
} from "./constants";
import { getPreferredOnboardingRule, resolveReplyProofDestination } from "./onboardingProofs";
import ReviewSubpage from "./subpages/ReviewSubpage";
import { TYPE, COLOR } from "../../theme";
import AppButton from "../../components/AppButton";

/* ── NHC field order for collapsible record summary ────────────────────────── */

const SUMMARY_FIELD_ORDER = [
  "department", "chief_complaint", "present_illness", "past_history",
  "allergy_history", "family_history", "personal_history", "marital_reproductive",
  "physical_exam", "specialist_exam", "auxiliary_exam",
  "diagnosis", "treatment_plan", "orders_followup",
];

/* ── Collapsible record summary ────────────────────────────────────────────── */

function RecordSummary({ record }) {
  const [expanded, setExpanded] = useState(true);
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
        sx={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 1.5, px: 2, py: 1.5, cursor: "pointer", "&:active": { bgcolor: COLOR.surface } }}
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

function FlowBanner({ title, subtitle }) {
  if (!title) return null;
  return (
    <Box sx={{ mt: 1, bgcolor: COLOR.white, borderTop: `0.5px solid ${COLOR.border}`, borderBottom: `0.5px solid ${COLOR.border}`, px: 2, py: 1.5 }}>
      <Typography sx={{ fontSize: TYPE.heading.fontSize, fontWeight: 600, color: COLOR.text1 }}>
        {title}
      </Typography>
      {subtitle && (
        <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text3, mt: 0.45, lineHeight: 1.6 }}>
          {subtitle}
        </Typography>
      )}
    </Box>
  );
}

function FlowBannerActions({ children }) {
  if (!children) return null;
  return (
    <Box sx={{ mt: 1, bgcolor: COLOR.white, borderTop: `0.5px solid ${COLOR.border}`, borderBottom: `0.5px solid ${COLOR.border}`, px: 2, py: 1 }}>
      {children}
    </Box>
  );
}

function InputProvenanceCard({ record }) {
  if (!record) return null;
  const structured = record.structured || {};
  const sourceLabel = record.record_type === "interview_summary"
    ? "患者预问诊摘要"
    : record.record_type === "import"
      ? "导入病历"
      : "医生病历记录";
  const summaryText = structured.chief_complaint || record.chief_complaint || record.content || "（无记录内容）";
  return (
    <Box sx={{ mt: 1, bgcolor: COLOR.white, borderTop: `0.5px solid ${COLOR.border}`, borderBottom: `0.5px solid ${COLOR.border}` }}>
      <Box sx={{ px: 2, py: 1, borderBottom: `0.5px solid ${COLOR.borderLight}` }}>
        <Typography sx={{ fontSize: TYPE.heading.fontSize, fontWeight: 600, color: COLOR.text1 }}>
          病例输入来源
        </Typography>
      </Box>
      <Box sx={{ px: 2, py: 1 }}>
        <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4, mb: 0.25 }}>
          来源
        </Typography>
        <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text2, lineHeight: 1.6 }}>
          {sourceLabel}
        </Typography>
      </Box>
      <Box sx={{ px: 2, py: 1, borderTop: `0.5px solid ${COLOR.borderLight}` }}>
        <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4, mb: 0.25 }}>
          关键信息
        </Typography>
        <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text2, lineHeight: 1.6 }}>
          {summaryText}
        </Typography>
      </Box>
    </Box>
  );
}

/* ── Main component ────────────────────────────────────────────────────────── */

export default function ReviewPage({ recordId }) {
  const navigate = useAppNavigate();
  const {
    getSuggestions,
    decideSuggestion,
    addSuggestion,
    triggerDiagnosis,
    finalizeReview,
    getTaskRecord,
    getKnowledgeBatch,
    fetchDrafts,
    ensureOnboardingExamples,
  } = useApi();
  const { doctorId } = useDoctorStore();

  const [record, setRecord] = useState(null);
  const [suggestions, setSuggestions] = useState(null); // null = not loaded, [] = empty
  const [expandedIds, setExpandedIds] = useState(new Set());
  const [loading, setLoading] = useState(true);
  const [finalizing, setFinalizing] = useState(false);
  const [openingReplyProof, setOpeningReplyProof] = useState(false);
  const [toast, showToast] = useToast();
  const [knowledgeMap, setKnowledgeMap] = useState({});
  const pollRef = useRef(null);
  const params = new URLSearchParams(window.location.search);
  const source = params.get("source") || "";
  const reviewTaskId = params.get("review_task_id") || "";
  const onboarding = getOnboardingState(doctorId);
  const savedRuleTitle = onboarding.lastSavedRuleTitle || "";

  /* ── Fetch cited knowledge items when suggestions change ─────────────────── */

  const citedIds = useMemo(() => {
    const ids = new Set();
    (suggestions || []).forEach((s) => {
      (s.cited_knowledge_ids || []).forEach((id) => ids.add(id));
    });
    return ids;
  }, [suggestions]);

  useEffect(() => {
    if (citedIds.size === 0 || !doctorId || !getKnowledgeBatch) return;
    getKnowledgeBatch(doctorId, [...citedIds])
      .then((data) => {
        const map = {};
        (data.items || []).forEach((item) => { map[item.id] = item; });
        setKnowledgeMap(map);
      })
      .catch(() => {}); // silent fail — citations will show as unresolved
  }, [citedIds, doctorId, getKnowledgeBatch]);

  useEffect(() => {
    if (!doctorId) return;
    if (source === "knowledge_proof") {
      markOnboardingStep(doctorId, ONBOARDING_STEP.diagnosis);
    }
  }, [doctorId, source]);

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
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
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
      const data = await finalizeReview(recordId, doctorId);
      const followUpTaskIds = data?.follow_up_task_ids || [];
      const isPreviewOnboardingFlow = source === "patient_preview";
      if (isPreviewOnboardingFlow && followUpTaskIds.length > 0) {
        markOnboardingStep(doctorId, ONBOARDING_STEP.followupTask, {
          lastFollowUpTaskIds: followUpTaskIds,
        });
      }
      showToast("审核完成");
      setTimeout(() => {
        if (isPreviewOnboardingFlow && followUpTaskIds.length > 0) {
          const highlight = followUpTaskIds.join(",");
          navigate(`/doctor/tasks?tab=followups&highlight_task_ids=${highlight}&origin=review_finalize`);
          return;
        }
        navigate(-1);
      }, 600);
    } catch {
      showToast("提交失败");
      setFinalizing(false);
    }
  }

  async function handleOpenReplyProof() {
    if (openingReplyProof) return;
    setOpeningReplyProof(true);
    try {
      const { preferredRuleId, preferredRuleTitle } = getPreferredOnboardingRule(doctorId, {
        preferredRuleTitle: savedRuleTitle,
      });
      const destination = await resolveReplyProofDestination({ fetchDrafts, ensureOnboardingExamples }, doctorId, {
        preferredRuleId,
        preferredRuleTitle,
      });
      navigate(destination);
    } finally {
      setOpeningReplyProof(false);
    }
  }


  /* ── Derived state ───────────────────────────────────────────────────────── */

  const hasSuggestions = suggestions && suggestions.length > 0;
  const isPendingReview = record?.review_status === "pending_review" || record?.status === "pending_review";
  const bannerTitle = source === "knowledge_proof"
    ? "示例诊断审核"
    : source === "patient_preview"
      ? "患者预问诊已提交"
      : "";
  const bannerSubtitle = source === "knowledge_proof"
    ? (savedRuleTitle ? `你刚保存的规则“${savedRuleTitle}”会在类似场景中影响 AI 的审核建议。` : "这里展示的是一个带来源信息的审核示例。")
    : source === "patient_preview"
      ? `该病例来自患者预问诊提交，审核完成后会生成随访任务。${reviewTaskId ? ` 当前审核任务 #${reviewTaskId}` : ""}`
      : "";

  /* ── Render ──────────────────────────────────────────────────────────────── */

  return (
    <>
      <ReviewSubpage
        record={record}
        suggestions={hasSuggestions ? suggestions : []}
        expandedIds={expandedIds}
        onToggle={handleToggle}
        onDecide={handleDecide}
        onAdd={handleAdd}
        onFinalize={handleFinalize}
        onBack={() => navigate(-1)}
        finalizing={finalizing}
        knowledgeMap={knowledgeMap}
      >
        <FlowBanner title={bannerTitle} subtitle={bannerSubtitle} />

        {source === "knowledge_proof" && (
          <FlowBannerActions>
            <AppButton
              variant="secondary"
              size="md"
              fullWidth
              disabled={openingReplyProof}
              loading={openingReplyProof}
              loadingLabel="打开中…"
              onClick={handleOpenReplyProof}
            >
              下一步：看回复示例
            </AppButton>
          </FlowBannerActions>
        )}

        <InputProvenanceCard record={record} />

        {/* Record summary — always shown if record loaded */}
        <RecordSummary record={record} />

        {/* Loading state */}
        {loading && <LoadingSkeleton />}

        {/* Polling state: no suggestions yet, record pending review */}
        {!loading && !hasSuggestions && isPendingReview && <LoadingSkeleton />}

        {/* Trigger button: no suggestions, record NOT pending review */}
        {!loading && !hasSuggestions && !isPendingReview && (
          <Box sx={{ mt: 1, bgcolor: COLOR.white, borderTop: `0.5px solid ${COLOR.border}`, borderBottom: `0.5px solid ${COLOR.border}`, px: 2, py: 2.5, textAlign: "center" }}>
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

      <Toast message={toast} />
    </>
  );
}
