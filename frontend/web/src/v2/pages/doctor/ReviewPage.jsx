/**
 * @route /doctor/review/:recordId
 *
 * v2 ReviewPage — antd-mobile rewrite.
 * Full-screen subpage (hides TabBar) for reviewing a single AI diagnosis record.
 * No MUI, no src/components, no src/theme.js.
 */
import { useState, useEffect, useMemo, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import {
  NavBar,
  Button,
  Dialog,
  Toast,
  SpinLoading,
  TextArea,
  Card,
  SafeArea,
  Tag,
} from "antd-mobile";
import { CheckOutline } from "antd-mobile-icons";
import { useTaskRecord, useSuggestions } from "../../../lib/doctorQueries";
import { QK } from "../../../lib/queryKeys";
import { useApi } from "../../../api/ApiContext";
import { useDoctorStore } from "../../../store/doctorStore";
import { dp } from "../../../utils/doctorBasePath";
import { APP, FONT, RADIUS } from "../../theme";
import {
  STRUCTURED_FIELD_LABELS,
  markOnboardingStep,
  ONBOARDING_STEP,
} from "../../../pages/doctor/constants";

// ── NHC field order ────────────────────────────────────────────────
const SUMMARY_FIELD_ORDER = [
  "department",
  "chief_complaint",
  "present_illness",
  "past_history",
  "allergy_history",
  "family_history",
  "personal_history",
  "marital_reproductive",
  "physical_exam",
  "specialist_exam",
  "auxiliary_exam",
  "diagnosis",
  "treatment_plan",
  "orders_followup",
];

const SECTIONS = [
  { key: "differential", label: "鉴别诊断" },
  { key: "workup", label: "检查建议" },
  { key: "treatment", label: "治疗方向" },
];

// ── Helpers ────────────────────────────────────────────────────────

function sourceLabel(recordType) {
  if (recordType === "interview_summary") return "患者预问诊摘要";
  if (recordType === "import") return "导入病历";
  return "医生病历记录";
}

// ── Record summary card ────────────────────────────────────────────

function RecordSummaryCard({ record }) {
  const [expanded, setExpanded] = useState(true);
  if (!record) return null;

  const structured = record.structured || {};
  const filledFields = SUMMARY_FIELD_ORDER.filter((k) => structured[k]);
  const preview =
    structured.chief_complaint || record.content || "(无记录)";
  const patientName = record.patient_name || "";
  const date = record.created_at ? record.created_at.slice(0, 10) : "";

  return (
    <Card
      style={{ margin: "8px 12px", borderRadius: RADIUS.md }}
      title={
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
          }}
          onClick={() => setExpanded((v) => !v)}
        >
          <div>
            <span style={{ fontWeight: 600, fontSize: FONT.md }}>{patientName}</span>
            {date && (
              <span style={{ fontSize: FONT.sm, color: APP.text4, marginLeft: 8 }}>
                {date}
              </span>
            )}
          </div>
          <span style={{ fontSize: FONT.sm, color: APP.text4 }}>
            {expanded ? "收起 ▴" : "展开 ▾"}
          </span>
        </div>
      }
    >
      {!expanded && (
        <div
          style={{
            fontSize: FONT.sm,
            color: APP.text3,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {preview}
        </div>
      )}
      {expanded &&
        (filledFields.length > 0 ? (
          filledFields.map((key) => (
            <div
              key={key}
              style={{
                display: "flex",
                gap: 8,
                padding: "6px 0",
                borderTop: `0.5px solid ${APP.borderLight}`,
              }}
            >
              <span
                style={{
                  fontSize: FONT.sm,
                  color: APP.text4,
                  fontWeight: 500,
                  flexShrink: 0,
                  minWidth: 56,
                }}
              >
                {STRUCTURED_FIELD_LABELS[key] || key}
              </span>
              <span
                style={{
                  fontSize: FONT.sm,
                  color: APP.text2,
                  whiteSpace: "pre-wrap",
                  lineHeight: 1.6,
                }}
              >
                {structured[key]}
              </span>
            </div>
          ))
        ) : record.content ? (
          <div
            style={{
              fontSize: FONT.sm,
              color: APP.text2,
              whiteSpace: "pre-wrap",
              lineHeight: 1.6,
              paddingTop: 6,
              borderTop: `0.5px solid ${APP.borderLight}`,
            }}
          >
            {record.content}
          </div>
        ) : null)}
    </Card>
  );
}

// ── Input provenance card ──────────────────────────────────────────

function ProvenanceCard({ record }) {
  if (!record) return null;
  const structured = record.structured || {};
  const summaryText =
    structured.chief_complaint ||
    record.chief_complaint ||
    record.content ||
    "（无记录内容）";

  return (
    <Card
      title="病例输入来源"
      style={{ margin: "8px 12px", borderRadius: RADIUS.md }}
    >
      <div style={{ marginBottom: 8 }}>
        <div style={{ fontSize: FONT.sm, color: APP.text4, marginBottom: 2 }}>
          来源
        </div>
        <div style={{ fontSize: FONT.sm, color: APP.text2, lineHeight: 1.6 }}>
          {sourceLabel(record.record_type)}
        </div>
      </div>
      <div style={{ borderTop: `0.5px solid ${APP.borderLight}`, paddingTop: 8 }}>
        <div style={{ fontSize: FONT.sm, color: APP.text4, marginBottom: 2 }}>
          关键信息
        </div>
        <div style={{ fontSize: FONT.sm, color: APP.text2, lineHeight: 1.6 }}>
          {summaryText}
        </div>
      </div>
    </Card>
  );
}

// ── Loading skeleton ───────────────────────────────────────────────

function LoadingCard() {
  return (
    <Card style={{ margin: "8px 12px", borderRadius: RADIUS.md }}>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 10,
          marginBottom: 12,
        }}
      >
        <SpinLoading color="primary" style={{ "--size": "20px" }} />
        <span style={{ fontSize: FONT.main, color: APP.text3 }}>AI 正在分析...</span>
      </div>
      {[1, 2, 3].map((i) => (
        <div
          key={i}
          style={{
            height: 40,
            borderRadius: RADIUS.sm,
          backgroundColor: APP.borderLight,
            marginBottom: 8,
          }}
        />
      ))}
    </Card>
  );
}

// ── Checklist suggestion item ──────────────────────────────────────

function SuggestionItem({ suggestion, onDecide, knowledgeMap }) {
  const [expanded, setExpanded] = useState(false);
  const [editing, setEditing] = useState(false);
  const [editText, setEditText] = useState("");
  const [editDetail, setEditDetail] = useState("");

  const s = suggestion;
  const isConfirmed = s.decision === "confirmed" || s.decision === "edited";
  const isRejected = s.decision === "rejected";
  const citedRules = (s.cited_knowledge_ids || [])
    .map((id) => knowledgeMap[id])
    .filter(Boolean);

  function startEdit() {
    setEditText(s.edited_text || s.content || "");
    setEditDetail(s.detail || "");
    setEditing(true);
    setExpanded(false);
  }

  function saveEdit() {
    if (editText.trim()) {
      onDecide(s.id, "edited", {
        edited_text: editText.trim(),
        detail: editDetail.trim(),
      });
    }
    setEditing(false);
  }

  return (
    <div
      style={{
        padding: "12px 16px",
        borderBottom: `0.5px solid ${APP.borderLight}`,
        backgroundColor: APP.surface,
        opacity: isRejected ? 0.4 : 1,
      }}
    >
      {editing ? (
        <div>
          <TextArea
            placeholder="建议内容"
            value={editText}
            onChange={setEditText}
            autoSize={{ minRows: 1, maxRows: 3 }}
            style={{ marginBottom: 8, fontSize: FONT.main }}
          />
          <TextArea
            placeholder="详细说明"
            value={editDetail}
            onChange={setEditDetail}
            autoSize={{ minRows: 2, maxRows: 6 }}
            style={{ fontSize: FONT.sm }}
          />
          <div style={{ display: "flex", gap: 16, marginTop: 8 }}>
            <span
              style={{
                fontSize: FONT.sm,
                color: APP.text4,
                cursor: "pointer",
              }}
              onClick={() => setEditing(false)}
            >
              取消
            </span>
            <span
              style={{
                fontSize: FONT.sm,
                color: APP.primary,
                fontWeight: 500,
                cursor: "pointer",
              }}
              onClick={saveEdit}
            >
              保存
            </span>
          </div>
        </div>
      ) : (
        <div style={{ display: "flex", gap: 12, alignItems: "flex-start" }}>
          {/* Checkbox */}
          <div
            style={{
              width: 20,
              height: 20,
              borderRadius: "50%",
              flexShrink: 0,
              marginTop: 2,
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              ...(isConfirmed
                ? { backgroundColor: APP.primary }
                : {
                    border: `1.5px solid ${APP.border}`,
                    backgroundColor: "transparent",
                  }),
            }}
            onClick={() =>
              onDecide(s.id, isConfirmed ? "rejected" : "confirmed", {})
            }
          >
            {isConfirmed && (
              <CheckOutline style={{ color: APP.white, fontSize: FONT.xs }} />
            )}
          </div>

          {/* Content */}
          <div
            style={{ flex: 1, minWidth: 0 }}
            onClick={() => !editing && setExpanded((v) => !v)}
          >
            <div
              style={{
                fontSize: FONT.md,
                fontWeight: 500,
                color: isRejected ? APP.text4 : APP.text1,
              }}
            >
              {s.edited_text || s.content}
              {!expanded && !isConfirmed && !isRejected && (
                <span style={{ fontSize: FONT.xs, color: APP.text4, marginLeft: 4 }}>
                  ▾
                </span>
              )}
            </div>

            {expanded && (
              <div style={{ marginTop: 8 }}>
                {s.detail && (
                  <div
                    style={{
                      fontSize: FONT.sm,
                      color: APP.text3,
                      lineHeight: 1.6,
                      marginBottom: 8,
                    }}
                  >
                    {s.detail}
                  </div>
                )}
                {citedRules.length > 0 && (
                  <div style={{ marginBottom: 8 }}>
                    {citedRules.map((rule) => (
                      <div
                        key={rule.id}
                        style={{
                          fontSize: FONT.sm,
                          color: APP.danger,
                        }}
                      >
                        引用: {rule.title}
                      </div>
                    ))}
                  </div>
                )}
                {s.rule_cited && citedRules.length === 0 && (
                  <div
                    style={{
                      fontSize: FONT.sm,
                      color: APP.danger,
                      marginBottom: 8,
                    }}
                  >
                    引用: {s.rule_cited}
                  </div>
                )}
                <div
                  style={{
                    display: "flex",
                    gap: 16,
                    paddingTop: 8,
                    borderTop: `0.5px solid ${APP.borderLight}`,
                  }}
                >
                  {!isConfirmed && (
                    <span
                      style={{
                        fontSize: FONT.sm,
                        color: APP.primary,
                        fontWeight: 500,
                        cursor: "pointer",
                      }}
                      onClick={(e) => {
                        e.stopPropagation();
                        onDecide(s.id, "confirmed", {});
                      }}
                    >
                      确认
                    </span>
                  )}
                  <span
                    style={{
                      fontSize: FONT.sm,
                      color: APP.text4,
                      cursor: "pointer",
                    }}
                    onClick={(e) => {
                      e.stopPropagation();
                      startEdit();
                    }}
                  >
                    修改
                  </span>
                  <span
                    style={{
                      fontSize: FONT.sm,
                      color: APP.text4,
                      cursor: "pointer",
                    }}
                    onClick={(e) => {
                      e.stopPropagation();
                      onDecide(s.id, "rejected", { reason: "removed" });
                    }}
                  >
                    移除
                  </span>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Checklist section ──────────────────────────────────────────────

function ChecklistSection({ sectionKey, label, items, onDecide, onAdd, knowledgeMap }) {
  const [adding, setAdding] = useState(false);
  const [newContent, setNewContent] = useState("");
  const [newDetail, setNewDetail] = useState("");

  if ((!items || items.length === 0) && !adding) return null;

  function submitAdd() {
    if (newContent.trim()) {
      onAdd(sectionKey, newContent.trim(), newDetail.trim());
      setNewContent("");
      setNewDetail("");
      setAdding(false);
    }
  }

  return (
    <div style={{ marginBottom: 4 }}>
      {/* Section header */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          padding: "8px 16px",
          backgroundColor: APP.surfaceAlt,
          borderTop: `0.5px solid ${APP.border}`,
          borderBottom: `0.5px solid ${APP.border}`,
        }}
      >
        <span style={{ fontSize: FONT.sm, fontWeight: 600, color: APP.text4, letterSpacing: 0.3 }}>
          {label}
        </span>
        <span
          style={{
            fontSize: FONT.sm,
            color: adding ? APP.text4 : APP.primary,
            cursor: "pointer",
          }}
          onClick={() => setAdding((v) => !v)}
        >
          {adding ? "取消" : "+ 添加"}
        </span>
      </div>

      {/* Add form */}
      {adding && (
        <div
          style={{
            backgroundColor: APP.surface,
            padding: "12px 16px",
            borderBottom: `0.5px solid ${APP.border}`,
          }}
        >
          <TextArea
            placeholder="建议内容"
            value={newContent}
            onChange={setNewContent}
            autoSize={{ minRows: 1, maxRows: 3 }}
            style={{ marginBottom: 8, fontSize: FONT.main }}
          />
          <TextArea
            placeholder="详细说明（可选）"
            value={newDetail}
            onChange={setNewDetail}
            autoSize={{ minRows: 1, maxRows: 3 }}
            style={{ fontSize: FONT.sm }}
          />
          <div
            style={{
              display: "flex",
              justifyContent: "flex-end",
              gap: 16,
              marginTop: 8,
            }}
          >
            <span
              style={{ fontSize: FONT.sm, color: APP.text4, cursor: "pointer" }}
              onClick={() => setAdding(false)}
            >
              取消
            </span>
            <span
              style={{
                fontSize: FONT.sm,
                color: APP.primary,
                fontWeight: 500,
                cursor: newContent.trim() ? "pointer" : "default",
                opacity: newContent.trim() ? 1 : 0.4,
              }}
              onClick={submitAdd}
            >
              添加
            </span>
          </div>
        </div>
      )}

      {/* Items */}
      <div style={{ backgroundColor: APP.surface }}>
        {(items || []).map((s) => (
          <SuggestionItem
            key={s.id}
            suggestion={s}
            onDecide={onDecide}
            knowledgeMap={knowledgeMap}
          />
        ))}
      </div>
    </div>
  );
}

// ── Main ───────────────────────────────────────────────────────────

export default function ReviewPage({ recordId }) {
  const navigate = useNavigate();
  const api = useApi();
  const {
    getSuggestions,
    decideSuggestion,
    addSuggestion,
    triggerDiagnosis,
    finalizeReview,
    getTaskRecord,
    getKnowledgeBatch,
  } = api;
  const { doctorId } = useDoctorStore();
  const queryClient = useQueryClient();

  const params = new URLSearchParams(window.location.search);
  const source = params.get("source") || "";
  const reviewTaskId = params.get("review_task_id") || "";

  // Local state for optimistic mutations
  const [record, setRecord] = useState(null);
  const [suggestions, setSuggestions] = useState(null);
  const [finalizing, setFinalizing] = useState(false);
  const [knowledgeMap, setKnowledgeMap] = useState({});
  const [teachEditId, setTeachEditId] = useState(null);
  const [teachSaving, setTeachSaving] = useState(false);

  // React Query
  const { data: recordData, isLoading: recordLoading } = useTaskRecord(recordId);
  const { data: suggestionsData, isLoading: sugLoading } = useSuggestions(recordId);
  const loading = recordLoading || sugLoading;

  useEffect(() => {
    if (recordData && !record) setRecord(recordData);
  }, [recordData]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!suggestionsData) return;
    const items = Array.isArray(suggestionsData)
      ? suggestionsData
      : suggestionsData?.suggestions || suggestionsData?.items || [];
    if (suggestionsData.status) {
      setRecord((prev) =>
        prev ? { ...prev, status: suggestionsData.status } : prev
      );
    }
    setSuggestions((prev) => {
      if (prev !== null && prev.length > 0) return prev;
      return items;
    });
  }, [suggestionsData]); // eslint-disable-line react-hooks/exhaustive-deps

  // Fetch cited knowledge
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
        (data.items || []).forEach((item) => {
          map[item.id] = item;
        });
        setKnowledgeMap(map);
      })
      .catch(() => {});
  }, [citedIds, doctorId, getKnowledgeBatch]);

  // ── Handlers ────────────────────────────────────────────────────

  async function handleDecide(suggestionId, decision, opts) {
    try {
      const resp = await decideSuggestion(suggestionId, decision, opts);
      queryClient.invalidateQueries({ queryKey: QK.suggestions(recordId, doctorId) });
      queryClient.invalidateQueries({ queryKey: QK.reviewQueue(doctorId) });
      setSuggestions((prev) =>
        (prev || []).map((s) =>
          s.id === suggestionId
            ? {
                ...s,
                decision,
                ...(opts.edited_text ? { edited_text: opts.edited_text } : {}),
                ...(opts.reason ? { reason: opts.reason } : {}),
              }
            : s
        )
      );
      if (resp?.teach_prompt && resp?.edit_id) {
        setTeachEditId(resp.edit_id);
      }
    } catch {
      Toast.show({ content: "操作失败", position: "bottom" });
    }
  }

  async function handleAdd(section, content, detail) {
    try {
      const created = await addSuggestion(
        recordId,
        doctorId,
        section,
        content,
        detail || undefined
      );
      queryClient.invalidateQueries({ queryKey: QK.suggestions(recordId, doctorId) });
      setSuggestions((prev) => [...(prev || []), created]);
    } catch {
      Toast.show({ content: "添加失败", position: "bottom" });
    }
  }

  async function handleTriggerDiagnosis() {
    try {
      await triggerDiagnosis(recordId, doctorId);
      setRecord((prev) => (prev ? { ...prev, status: "pending_review" } : prev));
      setSuggestions([]);
      queryClient.invalidateQueries({ queryKey: QK.suggestions(recordId, doctorId) });
      Toast.show({ content: "已提交分析请求", position: "bottom" });
    } catch {
      Toast.show({ content: "请求失败", position: "bottom" });
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
      queryClient.invalidateQueries({ queryKey: QK.draftSummary(doctorId) });
      queryClient.invalidateQueries({ queryKey: QK.reviewQueue(doctorId) });
      Toast.show({ content: "审核完成", position: "bottom" });
      setTimeout(() => {
        if (isPreviewOnboardingFlow && followUpTaskIds.length > 0) {
          const highlight = followUpTaskIds.join(",");
          navigate(
            `${dp("tasks")}?tab=followups&highlight_task_ids=${highlight}&origin=review_finalize`
          );
          return;
        }
        if (record?.patient_id) {
          navigate(dp(`patients/${record.patient_id}`));
        } else {
          navigate(dp("patients"));
        }
      }, 600);
    } catch {
      Toast.show({ content: "提交失败", position: "bottom" });
      setFinalizing(false);
    }
  }

  async function handleTeachSave() {
    if (!teachEditId || teachSaving) return;
    setTeachSaving(true);
    try {
      await (api.createRuleFromEdit || (() => Promise.resolve()))(
        teachEditId,
        doctorId
      );
      queryClient.invalidateQueries({ queryKey: QK.knowledge(doctorId) });
      setTeachEditId(null);
    } catch {
      Toast.show({ content: "保存失败", position: "bottom" });
    } finally {
      setTeachSaving(false);
    }
  }

  // ── Derived state ────────────────────────────────────────────────

  const hasSuggestions = suggestions && suggestions.length > 0;
  const isPendingReview =
    record?.review_status === "pending_review" ||
    record?.status === "pending_review";
  const isDiagnosisFailed = record?.status === "diagnosis_failed";

  const isDecided = (s) =>
    s.decision === "confirmed" ||
    s.decision === "rejected" ||
    s.decision === "edited" ||
    s.decision === "custom";
  const allDecided = hasSuggestions && (suggestions || []).every(isDecided);
  const undecidedCount = (suggestions || []).filter((s) => !isDecided(s)).length;

  // Group suggestions by section
  const grouped = {};
  SECTIONS.forEach((s) => {
    grouped[s.key] = [];
  });
  (suggestions || []).forEach((s) => {
    if (grouped[s.section]) grouped[s.section].push(s);
  });

  const patientName = record?.patient_name || "诊断审核";

  // ── Render ───────────────────────────────────────────────────────

  return (
    <div
      style={{
        height: "100%",
        display: "flex",
        flexDirection: "column",
        backgroundColor: APP.surfaceAlt,
        overflow: "hidden",
      }}
    >
      <SafeArea position="top" />

      {/* NavBar */}
      <NavBar
        onBack={() => navigate(-1)}
        style={{
          "--height": "44px",
          "--border-bottom": `0.5px solid ${APP.border}`,
          backgroundColor: APP.surface,
          flexShrink: 0,
        }}
      >
        {patientName}
      </NavBar>

      {/* Scrollable content */}
      <div
        style={{
          flex: 1,
          overflowY: "auto",
          paddingBottom: hasSuggestions ? 96 : 24,
        }}
      >
        {/* Source/flow banner for patient_preview */}
        {source === "patient_preview" && (
          <Card style={{ margin: "8px 12px", borderRadius: RADIUS.md }}>
            <div style={{ fontWeight: 600, fontSize: FONT.md, marginBottom: 4 }}>
              患者预问诊已提交
            </div>
            <div style={{ fontSize: FONT.sm, color: APP.text3, lineHeight: 1.6 }}>
              该病例来自患者预问诊提交，审核完成后会生成随访任务。
              {reviewTaskId ? ` 当前审核任务 #${reviewTaskId}` : ""}
            </div>
          </Card>
        )}

        {/* Provenance */}
        <ProvenanceCard record={record} />

        {/* Record summary */}
        <RecordSummaryCard record={record} />

        {/* Loading / polling state */}
        {(loading || (!loading && !hasSuggestions && isPendingReview)) && (
          <LoadingCard />
        )}

        {/* Diagnosis failed — retry */}
        {!loading && !hasSuggestions && isDiagnosisFailed && (
          <Card style={{ margin: "8px 12px", borderRadius: RADIUS.md, textAlign: "center" }}>
            <div
              style={{ fontSize: FONT.sm, color: APP.danger, marginBottom: 12 }}
            >
              AI 诊断超时，请重试
            </div>
            <Button
              color="primary"
              fill="none"
              size="small"
              onClick={handleTriggerDiagnosis}
            >
              重新分析
            </Button>
          </Card>
        )}

        {/* Trigger button: no suggestions, not pending, not failed */}
        {!loading && !hasSuggestions && !isPendingReview && !isDiagnosisFailed && (
          <Card style={{ margin: "8px 12px", borderRadius: RADIUS.md, textAlign: "center" }}>
            <div style={{ fontSize: FONT.sm, color: APP.text3, marginBottom: 12 }}>
              可生成 AI 诊断建议
            </div>
            <Button
              color="primary"
              fill="none"
              size="small"
              onClick={handleTriggerDiagnosis}
            >
              请 AI 分析此病历
            </Button>
          </Card>
        )}

        {/* AI suggestions header */}
        {hasSuggestions && (
          <div
            style={{
              padding: "8px 16px",
              backgroundColor: APP.surfaceAlt,
              borderTop: `0.5px solid ${APP.border}`,
              borderBottom: `0.5px solid ${APP.border}`,
              marginTop: 4,
            }}
          >
            <span
              style={{
                fontSize: FONT.sm,
                fontWeight: 600,
                color: APP.text4,
                letterSpacing: 0.3,
              }}
            >
              AI 诊断建议
            </span>
          </div>
        )}

        {/* Suggestion sections */}
        {SECTIONS.map((sec) => (
          <ChecklistSection
            key={sec.key}
            sectionKey={sec.key}
            label={sec.label}
            items={grouped[sec.key]}
            onDecide={handleDecide}
            onAdd={handleAdd}
            knowledgeMap={knowledgeMap}
          />
        ))}
      </div>

      {/* Bottom action bar */}
      {hasSuggestions && (
        <div
          style={{
            position: "absolute",
            bottom: 0,
            left: 0,
            right: 0,
            padding: "12px 16px",
            paddingBottom:
              "calc(12px + env(safe-area-inset-bottom, 0px))",
            backgroundColor: APP.surface,
            borderTop: `0.5px solid ${APP.border}`,
            flexShrink: 0,
          }}
        >
          <Button
            block
            color="primary"
            size="large"
            disabled={!allDecided || finalizing}
            loading={finalizing}
            onClick={handleFinalize}
          >
            {allDecided
              ? "完成审核"
              : `还有 ${undecidedCount} 项未处理`}
          </Button>
        </div>
      )}

      {/* Teach-AI snackbar — shown after an edit decision */}
      {teachEditId && (
        <div
          style={{
            position: "fixed",
            bottom: 80,
            left: 16,
            right: 16,
            backgroundColor: APP.text2,
            color: APP.white,
            borderRadius: RADIUS.md,
            padding: "12px 16px",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            zIndex: 1000,
            fontSize: FONT.sm,
          }}
        >
          <span style={{ flex: 1, marginRight: 12 }}>
            您的修改已记录。要将这条诊断修正保存为知识条目吗？
          </span>
          <div style={{ display: "flex", gap: 16, flexShrink: 0 }}>
            <span
              style={{ opacity: 0.8, cursor: "pointer" }}
              onClick={() => setTeachEditId(null)}
            >
              跳过
            </span>
            <span
              style={{
                color: APP.wechatGreen,
                fontWeight: 500,
                cursor: teachSaving ? "default" : "pointer",
                opacity: teachSaving ? 0.5 : 1,
              }}
              onClick={handleTeachSave}
            >
              {teachSaving ? "保存中..." : "保存"}
            </span>
          </div>
        </div>
      )}

      <SafeArea position="bottom" />
    </div>
  );
}
