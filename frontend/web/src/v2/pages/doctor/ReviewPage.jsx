/**
 * @route /doctor/review/:recordId
 *
 * v2 ReviewPage — antd-mobile rewrite.
 * Full-screen subpage (hides TabBar) for reviewing a single AI diagnosis record.
 * No MUI, no src/components, no src/theme.js.
 */
import { useState, useEffect, useMemo, useCallback, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import {
  NavBar,
  Button,
  Checkbox,
  Dialog,
  Toast,
  SpinLoading,
  TextArea,
  Card,
  SafeArea,
  Tag,
  Collapse,
  ActionSheet,
  Ellipsis,
} from "antd-mobile";
import { MoreOutline } from "antd-mobile-icons";
import { pageContainer, navBarStyle, scrollable } from "../../layouts";
import { keyboardAwareStyle, useScrollOnKeyboard } from "../../keyboard";
import { ActionFooter, SectionHeader, CitationPopup } from "../../components";
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
import FieldWithAI from "./FieldWithAI";
import FeedbackSheet from "../../components/FeedbackSheet";

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

// Fields the doctor reads first to judge AI's suggestions. Everything else
// (past history, family history, physical exam, etc.) hides behind 展开.
const KEY_FIELDS = ["chief_complaint", "present_illness", "diagnosis", "treatment_plan"];

function RecordSummaryCard({ record }) {
  // Expanded by default — doctor needs full context to judge AI suggestions.
  const [expanded, setExpanded] = useState(true);
  if (!record) return null;

  const structured = record.structured || {};
  const filledAll = SUMMARY_FIELD_ORDER.filter((k) => structured[k]);
  const filledKey = KEY_FIELDS.filter((k) => structured[k]);
  const hasMore = filledAll.length > filledKey.length;
  const toRender = expanded ? filledAll : filledKey;

  if (toRender.length === 0 && !record.content) return null;

  return (
    <div
      style={{
        background: APP.surface,
        border: `0.5px solid ${APP.border}`,
        borderRadius: RADIUS.md,
        padding: "12px 14px",
        margin: "8px 12px",
      }}
    >
      {toRender.length > 0 ? (
        toRender.map((key, i) => (
          <div
            key={key}
            style={{
              display: "flex",
              gap: 10,
              padding: "6px 0",
              borderTop: i === 0 ? "none" : `0.5px solid ${APP.borderLight}`,
            }}
          >
            <span
              style={{
                fontSize: FONT.sm,
                color: APP.text4,
                fontWeight: 500,
                flexShrink: 0,
                minWidth: 60,
              }}
            >
              {STRUCTURED_FIELD_LABELS[key] || key}
            </span>
            <span
              style={{
                flex: 1,
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
          }}
        >
          {record.content}
        </div>
      ) : null}
      {hasMore && (
        <div
          onClick={() => setExpanded((v) => !v)}
          style={{
            marginTop: 8,
            paddingTop: 8,
            borderTop: `0.5px solid ${APP.borderLight}`,
            fontSize: FONT.sm,
            color: APP.primary,
            cursor: "pointer",
            textAlign: "center",
          }}
        >
          {expanded ? "收起" : `展开全部（${filledAll.length} 项）`}
        </div>
      )}
    </div>
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

/**
 * Decision card for one AI suggestion. Three visual states:
 *  - pending   → white card, title + body + optional citation chip + 修改/采纳
 *  - accepted  → light-green fill, single line ✓ + title; tap to reopen
 *  - editing   → inline textareas + 取消/保存
 * No category tags, no urgency chip — all categorization dropped by design.
 */
function SuggestionCard({ suggestion, onDecide, knowledgeMap, onOpenCitation }) {
  const [editing, setEditing] = useState(false);
  const [editText, setEditText] = useState("");
  const [editDetail, setEditDetail] = useState("");

  const s = suggestion;
  const isAccepted = s.decision === "confirmed" || s.decision === "edited";
  const isRejected = s.decision === "rejected";

  // Resolve cited knowledge → human-readable entries. Each shows as its own
  // row below the card; tapping any row opens the shared swiper popup at that
  // index.
  const citedRules = (s.cited_knowledge_ids || [])
    .map((id) => knowledgeMap[id])
    .filter(Boolean);

  function startEdit() {
    setEditText(s.edited_text || s.content || "");
    setEditDetail(s.detail || "");
    setEditing(true);
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

  // ── Rejected: muted single-line card, tap to restore ──────────────
  if (isRejected && !editing) {
    return (
      <div
        onClick={() => onDecide(s.id, "pending", {})}
        style={{
          background: APP.surfaceAlt,
          borderRadius: RADIUS.md,
          padding: "10px 14px",
          margin: "0 12px 12px",
          display: "flex",
          alignItems: "center",
          gap: 8,
          cursor: "pointer",
        }}
      >
        <span style={{ color: APP.text4, fontSize: FONT.sm, flexShrink: 0 }}>已移除</span>
        <div
          style={{
            flex: 1,
            fontSize: FONT.sm,
            color: APP.text4,
            textDecoration: "line-through",
            minWidth: 0,
          }}
        >
          <Ellipsis direction="end" content={s.edited_text || s.content} rows={1} />
        </div>
        <span style={{ fontSize: FONT.sm, color: APP.primary }}>恢复</span>
      </div>
    );
  }

  // ── Accepted: single-line light-green card ────────────────────────
  if (isAccepted && !editing) {
    return (
      <div
        onClick={() => onDecide(s.id, "pending", {})}
        style={{
          background: APP.primaryLight,
          borderRadius: RADIUS.md,
          padding: "12px 14px",
          margin: "0 12px 12px",
          display: "flex",
          alignItems: "center",
          gap: 8,
          cursor: "pointer",
        }}
      >
        <span style={{ color: APP.primary, fontWeight: 600, fontSize: FONT.md, flexShrink: 0 }}>
          ✓
        </span>
        <span style={{ flex: 1, fontSize: FONT.base, color: APP.text1, fontWeight: 500 }}>
          {s.edited_text || s.content}
        </span>
      </div>
    );
  }

  // ── Editing: inline textareas ─────────────────────────────────────
  if (editing) {
    return (
      <div
        style={{
          background: APP.surface,
          border: `0.5px solid ${APP.border}`,
          borderRadius: RADIUS.md,
          padding: 14,
          margin: "0 12px 12px",
        }}
      >
        <TextArea
          placeholder="建议内容"
          value={editText}
          onChange={setEditText}
          autoSize={{ minRows: 1, maxRows: 3 }}
          style={{ marginBottom: 8, fontSize: FONT.md }}
        />
        <TextArea
          placeholder="详细说明"
          value={editDetail}
          onChange={setEditDetail}
          autoSize={{ minRows: 2, maxRows: 6 }}
          style={{ fontSize: FONT.sm }}
        />
        <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
          <button
            onClick={() => setEditing(false)}
            style={{
              flex: 1, padding: "8px 0",
              background: APP.surface,
              border: `0.5px solid ${APP.border}`,
              borderRadius: RADIUS.sm,
              color: APP.text2,
              fontSize: FONT.sm,
              fontWeight: 500,
              cursor: "pointer",
            }}
          >
            取消
          </button>
          <button
            onClick={saveEdit}
            style={{
              flex: 1, padding: "8px 0",
              background: APP.primary,
              border: "none",
              borderRadius: RADIUS.sm,
              color: APP.white,
              fontSize: FONT.sm,
              fontWeight: 500,
              cursor: "pointer",
            }}
          >
            保存
          </button>
        </div>
      </div>
    );
  }

  // ── Pending: title + body + citation + 修改/采纳 ───────────────────
  return (
    <div
      style={{
        background: APP.surface,
        border: `0.5px solid ${APP.border}`,
        borderRadius: RADIUS.md,
        padding: 14,
        margin: "0 12px 12px",
        display: "flex",
        flexDirection: "column",
        gap: 10,
      }}
    >
      <div style={{ fontSize: FONT.md, color: APP.text1, fontWeight: 500, lineHeight: 1.4 }}>
        {s.edited_text || s.content}
      </div>
      {s.detail && (
        <div style={{ fontSize: FONT.sm, color: APP.text3, lineHeight: 1.55 }}>
          {s.detail}
        </div>
      )}
      {citedRules.length > 0 && (
        <div style={{ display: "grid", gap: 4, justifyItems: "start" }}>
          {citedRules.map((rule, idx) => (
            <span
              key={rule.id}
              onClick={(e) => {
                e.stopPropagation();
                onOpenCitation?.(citedRules, idx);
              }}
              style={{
                color: APP.primary,
                background: APP.primaryLight,
                fontSize: FONT.xs,
                padding: "2px 8px",
                borderRadius: RADIUS.xs,
                cursor: "pointer",
                maxWidth: "100%",
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
            >
              依据：{rule.title || rule.text?.slice(0, 16) || "已删除"} ›
            </span>
          ))}
        </div>
      )}
      <div
        style={{
          display: "flex",
          justifyContent: "flex-end",
          alignItems: "center",
          gap: 16,
        }}
      >
        <span
          onClick={() => onDecide(s.id, "rejected", { reason: "removed" })}
          style={{
            fontSize: FONT.sm,
            color: APP.text4,
            cursor: "pointer",
            padding: "10px 4px",
          }}
        >
          移除
        </span>
        <span
          onClick={startEdit}
          style={{
            fontSize: FONT.sm,
            color: APP.text4,
            cursor: "pointer",
            padding: "10px 4px",
          }}
        >
          修改
        </span>
        <button
          onClick={() => onDecide(s.id, "confirmed", {})}
          style={{
            background: APP.primary,
            border: "none",
            borderRadius: RADIUS.sm,
            color: APP.white,
            fontSize: FONT.sm,
            fontWeight: 500,
            padding: "8px 20px",
            cursor: "pointer",
          }}
        >
          采纳
        </button>
      </div>
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
      <SectionHeader
        action={adding ? "取消" : "+ 添加"}
        onAction={() => setAdding((v) => !v)}
      >
        {label}
      </SectionHeader>

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

// ── Inline review layout (feature-flagged V5) ──────────────────────

/**
 * InlineReviewLayout — V5 inline-per-field render path.
 * Active only when INLINE_SUGGESTIONS_V2 flag is on AND suggestions exist.
 *
 * Responsibilities:
 *  - Render patient banner + read-only summary card (main fields)
 *  - Per-section FieldWithAI rows (诊断 / 检查建议 / 治疗方向)
 *  - Per-section custom add buttons
 *  - Bottom "完成审核 · N 条未处理" bar with implicit_reject finalize
 *
 * Does NOT own the suggestions list or decide handlers — those are passed
 * down from the parent `ReviewPage`.
 */
function InlineReviewLayout({
  record,
  patientName,
  contextBits,
  suggestions,
  knowledgeMap,
  onDecide,
  onAdd,
  onFinalize,
  onOpenCitation,
  onSubmitFeedback,
  finalizing,
  onBack,
  teachEditId,
  onTeachSkip,
  onTeachSave,
  teachSaving,
}) {
  // Which suggestion is currently being flagged. null → sheet closed.
  // Object carries { id, content, detail, section, decision, ... } so the
  // FeedbackSheet can render a preview and the submit handler can attribute
  // the flag back to the right row.
  const [feedbackFor, setFeedbackFor] = useState(null);
  const structured = record?.structured || {};

  // Editable draft state for diagnosis + treatment_plan. Hydrated once.
  const [diagnosisDraft, setDiagnosisDraft] = useState(
    structured.diagnosis || ""
  );
  const [treatmentDraft, setTreatmentDraft] = useState(
    structured.treatment_plan || ""
  );
  useEffect(() => {
    if (structured.diagnosis && !diagnosisDraft) {
      setDiagnosisDraft(structured.diagnosis);
    }
    if (structured.treatment_plan && !treatmentDraft) {
      setTreatmentDraft(structured.treatment_plan);
    }
  }, [structured.diagnosis, structured.treatment_plan]); // eslint-disable-line react-hooks/exhaustive-deps

  // Track whether any FieldWithAI is in inline edit mode → disables finalize
  const [editingFields, setEditingFields] = useState({
    differential: false,
    workup: false,
    treatment: false,
  });
  const anyFieldEditing = Object.values(editingFields).some(Boolean);

  // Custom composer state: keyed by section
  const [composerSection, setComposerSection] = useState(null);
  const composerRef = useRef(null);
  useEffect(() => {
    if (composerSection && composerRef.current) {
      // Small delay lets the composer mount + layout settle before scrolling.
      const t = setTimeout(() => {
        composerRef.current?.scrollIntoView({
          behavior: "smooth",
          block: "center",
        });
      }, 50);
      return () => clearTimeout(t);
    }
  }, [composerSection]);
  const [composerText, setComposerText] = useState("");
  const [composerDetail, setComposerDetail] = useState("");

  const openComposer = (section) => {
    setComposerSection(section);
    setComposerText("");
    setComposerDetail("");
  };
  const closeComposer = () => {
    setComposerSection(null);
    setComposerText("");
    setComposerDetail("");
  };
  const submitComposer = async () => {
    const trimmed = composerText.trim();
    if (!trimmed) return;
    await onAdd(
      composerSection,
      trimmed,
      composerDetail.trim() || undefined
    );
    // For 诊断/治疗: custom-add also populates the editable field so it
    // lands in the final record on 完成审核.
    if (composerSection === "differential") setDiagnosisDraft(trimmed);
    if (composerSection === "treatment") setTreatmentDraft(trimmed);
    closeComposer();
  };

  // Section-split suggestions
  const bySection = useMemo(() => {
    const out = { differential: [], workup: [], treatment: [] };
    (suggestions || []).forEach((s) => {
      if (out[s.section]) out[s.section].push(s);
    });
    return out;
  }, [suggestions]);

  const undecidedCount = (suggestions || []).filter(
    (s) => s.decision == null || s.decision === "pending"
  ).length;

  const handleFinalize = () => {
    if (anyFieldEditing || finalizing) return;
    onFinalize({
      implicit_reject: true,
      edited_record: {
        diagnosis: diagnosisDraft || "",
        treatment_plan: treatmentDraft || "",
      },
    });
  };

  // 病例摘要 fields — read-only in Phase 1a/1b
  const SUMMARY_KEYS = ["chief_complaint", "present_illness", "past_history", "physical_exam"];
  const summaryRows = SUMMARY_KEYS.filter((k) => structured[k]);

  return (
    <div style={{ ...pageContainer, ...keyboardAwareStyle }}>
      <SafeArea position="top" />

      <NavBar onBack={onBack} style={navBarStyle}>
        诊断审核
      </NavBar>

      {/* Patient banner */}
      {record && (
        <div
          style={{
            background: APP.surface,
            padding: "8px 14px",
            margin: "6px 12px",
            border: `0.5px solid ${APP.border}`,
            borderRadius: RADIUS.md,
            fontSize: FONT.sm,
            color: APP.text3,
            lineHeight: 1.5,
            flexShrink: 0,
          }}
        >
          <div
            style={{
              color: APP.text1,
              fontSize: FONT.base,
              fontWeight: 600,
              marginBottom: 1,
            }}
          >
            {patientName}
          </div>
          {contextBits.length > 0 && <div>{contextBits.join(" · ")}</div>}
        </div>
      )}

      {/* Scrollable content */}
      <div style={{ ...scrollable, paddingBottom: 96 }}>
        {/* 病例摘要 — read-only summary card */}
        {summaryRows.length > 0 && (
          <>
            <div
              style={{
                padding: "12px 16px 4px",
                fontSize: FONT.xs,
                color: APP.text4,
                letterSpacing: "0.02em",
              }}
            >
              病例摘要
            </div>
            <div
              style={{
                background: APP.surface,
                margin: "0 12px 6px",
                border: `0.5px solid ${APP.border}`,
                borderRadius: RADIUS.md,
                padding: "10px 14px",
              }}
            >
              {summaryRows.map((key, i) => (
                <div
                  key={key}
                  style={{
                    display: "flex",
                    gap: 10,
                    padding: "6px 0",
                    fontSize: FONT.sm,
                    lineHeight: 1.55,
                    borderTop: i === 0 ? "none" : `0.5px solid ${APP.borderLight}`,
                  }}
                >
                  <span
                    style={{
                      minWidth: 60,
                      flexShrink: 0,
                      color: APP.text4,
                      fontWeight: 500,
                    }}
                  >
                    {STRUCTURED_FIELD_LABELS[key] || key}
                  </span>
                  <span
                    style={{
                      flex: 1,
                      color: APP.text2,
                      whiteSpace: "pre-wrap",
                    }}
                  >
                    {structured[key]}
                  </span>
                </div>
              ))}
            </div>
          </>
        )}

        {/* AI 建议 list header */}
        <div
          style={{
            padding: "12px 16px 4px",
            fontSize: FONT.xs,
            color: APP.text4,
            letterSpacing: "0.02em",
          }}
        >
          AI 建议 · 请逐项确认
        </div>

        <FieldWithAI
          label="诊断"
          sectionKey="differential"
          allowCycle={false}
          editableFieldValue={diagnosisDraft}
          onEditableFieldChange={setDiagnosisDraft}
          suggestions={bySection.differential}
          knowledgeMap={knowledgeMap}
          onDecide={onDecide}
          onOpenCitation={onOpenCitation}
          onOpenFeedback={setFeedbackFor}
          onEditingChange={(v) =>
            setEditingFields((prev) => ({ ...prev, differential: v }))
          }
        />

        <FieldWithAI
          label="检查建议"
          sectionKey="workup"
          allowCycle={true}
          editableFieldValue={null}
          onEditableFieldChange={() => {}}
          suggestions={bySection.workup}
          knowledgeMap={knowledgeMap}
          onDecide={onDecide}
          onOpenCitation={onOpenCitation}
          onOpenFeedback={setFeedbackFor}
          onEditingChange={(v) =>
            setEditingFields((prev) => ({ ...prev, workup: v }))
          }
        />

        <FieldWithAI
          label="治疗方向"
          sectionKey="treatment"
          allowCycle={false}
          editableFieldValue={treatmentDraft}
          onEditableFieldChange={setTreatmentDraft}
          suggestions={bySection.treatment}
          knowledgeMap={knowledgeMap}
          onDecide={onDecide}
          onOpenCitation={onOpenCitation}
          onOpenFeedback={setFeedbackFor}
          onEditingChange={(v) =>
            setEditingFields((prev) => ({ ...prev, treatment: v }))
          }
        />

        {/* Custom-add buttons */}
        <div style={{ display: "flex", gap: 8, margin: "6px 12px 12px" }}>
          {[
            { section: "differential", label: "+ 诊断" },
            { section: "workup", label: "+ 检查" },
            { section: "treatment", label: "+ 治疗" },
          ].map((btn) => (
            <div
              key={btn.section}
              onClick={() => openComposer(btn.section)}
              style={{
                flex: 1,
                padding: "8px 6px",
                background: APP.surface,
                border: `0.5px solid ${APP.border}`,
                borderRadius: RADIUS.md,
                fontSize: FONT.sm,
                color: APP.primary,
                fontWeight: 500,
                textAlign: "center",
                cursor: "pointer",
              }}
            >
              {btn.label}
            </div>
          ))}
        </div>

        {/* Inline custom composer */}
        {composerSection && (
          <div
            ref={composerRef}
            style={{
              background: APP.surface,
              border: `0.5px dashed ${APP.border}`,
              borderRadius: RADIUS.md,
              padding: 14,
              margin: "0 12px 12px",
            }}
          >
            <div style={{ fontSize: FONT.sm, color: APP.text3, marginBottom: 8 }}>
              新增自定义建议（
              {composerSection === "differential"
                ? "诊断"
                : composerSection === "workup"
                ? "检查"
                : "治疗"}
              ）
            </div>
            <TextArea
              placeholder="建议内容"
              value={composerText}
              onChange={setComposerText}
              autoSize={{ minRows: 1, maxRows: 3 }}
              style={{ marginBottom: 8, fontSize: FONT.base }}
            />
            <TextArea
              placeholder="详细说明（可选）"
              value={composerDetail}
              onChange={setComposerDetail}
              autoSize={{ minRows: 1, maxRows: 4 }}
              style={{ fontSize: FONT.sm }}
            />
            <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
              <button
                onClick={closeComposer}
                style={{
                  flex: 1,
                  padding: "8px 0",
                  background: APP.surface,
                  border: `0.5px solid ${APP.border}`,
                  borderRadius: RADIUS.sm,
                  color: APP.text2,
                  fontSize: FONT.sm,
                  fontWeight: 500,
                  cursor: "pointer",
                }}
              >
                取消
              </button>
              <button
                onClick={submitComposer}
                disabled={!composerText.trim()}
                style={{
                  flex: 1,
                  padding: "8px 0",
                  background: APP.primary,
                  border: "none",
                  borderRadius: RADIUS.sm,
                  color: APP.white,
                  fontSize: FONT.sm,
                  fontWeight: 500,
                  cursor: composerText.trim() ? "pointer" : "not-allowed",
                  opacity: composerText.trim() ? 1 : 0.5,
                }}
              >
                添加
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Bottom bar */}
      <ActionFooter
        style={{
          position: "absolute",
          bottom: 0,
          left: 0,
          right: 0,
          flexDirection: "column",
          gap: 4,
        }}
      >
        <div
          style={{
            fontSize: FONT.xs,
            color: APP.text4,
            textAlign: "center",
          }}
        >
          {anyFieldEditing
            ? "请先保存当前编辑再完成审核"
            : "未处理的建议在完成审核时将视为不采纳"}
        </div>
        <Button
          block
          color="primary"
          size="large"
          disabled={anyFieldEditing || finalizing}
          loading={finalizing}
          onClick={handleFinalize}
        >
          完成审核
          {undecidedCount > 0 && (
            <span
              style={{
                fontSize: FONT.xs,
                fontWeight: 400,
                opacity: 0.85,
                marginLeft: 6,
              }}
            >
              · {undecidedCount} 条未处理
            </span>
          )}
        </Button>
      </ActionFooter>

      {/* Teach-AI snackbar */}
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
            <span style={{ opacity: 0.8, cursor: "pointer" }} onClick={onTeachSkip}>
              跳过
            </span>
            <span
              style={{
                color: APP.wechatGreen,
                fontWeight: 500,
                cursor: teachSaving ? "default" : "pointer",
                opacity: teachSaving ? 0.5 : 1,
              }}
              onClick={onTeachSave}
            >
              {teachSaving ? "保存中..." : "保存"}
            </span>
          </div>
        </div>
      )}

      <SafeArea position="bottom" />

      {/* F1 feedback capture — bottom sheet rendered at the layout level so
          any FieldWithAI row can open it via onOpenFeedback. */}
      <FeedbackSheet
        visible={!!feedbackFor}
        suggestion={feedbackFor}
        onCancel={() => setFeedbackFor(null)}
        onSubmit={async (reasonTag, reasonText) => {
          if (!feedbackFor || !onSubmitFeedback) {
            setFeedbackFor(null);
            return;
          }
          try {
            await onSubmitFeedback({
              suggestion: feedbackFor,
              reasonTag,
              reasonText,
            });
            setFeedbackFor(null);
          } catch (err) {
            // Re-throw so FeedbackSheet surfaces its own Toast and keeps
            // the sheet open for retry.
            throw err;
          }
        }}
      />
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
    submitFeedback,
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
      // Custom adds are the doctor's own input — no need for a second accept.
      // Mark as decision=custom so the ✓ stack picks it up immediately.
      await decideSuggestion(created.id, "custom", {});
      queryClient.invalidateQueries({ queryKey: QK.suggestions(recordId, doctorId) });
      setSuggestions((prev) => [
        ...(prev || []),
        {
          id: created.id,
          section,
          content,
          detail: detail || null,
          is_custom: true,
          decision: "custom",
          cited_knowledge_ids: [],
        },
      ]);
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

  async function handleFinalize(opts = {}) {
    if (finalizing) return;
    setFinalizing(true);
    try {
      const data = await finalizeReview(recordId, doctorId, opts);
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

  async function handleSubmitFeedback({ suggestion, reasonTag, reasonText }) {
    if (!submitFeedback || !suggestion) {
      throw new Error("submitFeedback unavailable");
    }
    return submitFeedback({
      suggestion_id: suggestion.id,
      record_id: Number(recordId),
      doctor_id: doctorId,
      reason_tag: reasonTag,
      reason_text: reasonText || undefined,
      doctor_action: suggestion.decision || "pending",
    });
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
  const decidedCount = (suggestions || []).length - undecidedCount;

  const patientName = record?.patient_name || "诊断审核";

  // Compact context stat line for the header strip
  const contextBits = [
    record?.chief_complaint,
    record?.created_at
      ? `${String(new Date(record.created_at).getMonth() + 1).padStart(2, "0")}-${String(new Date(record.created_at).getDate()).padStart(2, "0")}`
      : null,
  ].filter(Boolean);

  const [addingCustom, setAddingCustom] = useState(false);
  const [customText, setCustomText] = useState("");
  const [customDetail, setCustomDetail] = useState("");

  async function submitCustom() {
    if (!customText.trim()) return;
    // Default added suggestions to "treatment" section — categories aren't
    // surfaced in the UI but the DB column is required.
    await handleAdd("treatment", customText.trim(), customDetail.trim() || undefined);
    setCustomText("");
    setCustomDetail("");
    setAddingCustom(false);
  }

  // Citation preview — open the centered-modal swiper instead of navigating
  // away so the doctor keeps their review context. Popup rendered at the root
  // (see end of this component). Each SuggestionCard passes its full list of
  // citedRules and the tapped index so the swiper opens on the right card.
  const [citationPopupItems, setCitationPopupItems] = useState(null);
  const [citationPopupIndex, setCitationPopupIndex] = useState(0);
  function handleOpenCitation(rules, idx) {
    if (!Array.isArray(rules) || rules.length === 0) return;
    setCitationPopupItems(rules);
    setCitationPopupIndex(idx || 0);
  }

  // Keyboard-aware scroll — keeps add form visible when keyboard opens
  const scrollBottomRef = useRef(null);
  useScrollOnKeyboard(scrollBottomRef);

  // Shared citation preview — rendered on both layout paths so the swiper
  // popup is always available when a 依据 pill is tapped.
  const citationPopupNode = (
    <CitationPopup
      visible={citationPopupItems != null}
      items={citationPopupItems}
      initialIndex={citationPopupIndex}
      onClose={() => setCitationPopupItems(null)}
      onOpenDetail={(item) => {
        setCitationPopupItems(null);
        if (item?.id != null) navigate(`/doctor/settings/knowledge/${item.id}`);
      }}
    />
  );

  // ── Inline-per-field layout (V5) — default when suggestions exist ──
  if (hasSuggestions) {
    return (
      <>
        <InlineReviewLayout
          record={record}
          patientName={patientName}
          contextBits={contextBits}
          suggestions={suggestions}
          knowledgeMap={knowledgeMap}
          onDecide={handleDecide}
          onAdd={handleAdd}
          onFinalize={handleFinalize}
          onOpenCitation={handleOpenCitation}
          onSubmitFeedback={handleSubmitFeedback}
          finalizing={finalizing}
          onBack={() => navigate(-1)}
          teachEditId={teachEditId}
          onTeachSkip={() => setTeachEditId(null)}
          onTeachSave={handleTeachSave}
          teachSaving={teachSaving}
        />
        {citationPopupNode}
      </>
    );
  }

  // ── Render (flag-off: legacy flat card list) ─────────────────────

  return (
    <div style={{ ...pageContainer, ...keyboardAwareStyle }}>
      <SafeArea position="top" />

      {/* NavBar */}
      <NavBar
        onBack={() => navigate(-1)}
        style={navBarStyle}
      >
        诊断审核
      </NavBar>

      {/* Compact context strip — name · 主诉 · date */}
      {record && (
        <div
          style={{
            background: APP.surface,
            padding: "10px 16px",
            display: "flex",
            alignItems: "baseline",
            gap: 8,
            borderBottom: `0.5px solid ${APP.border}`,
            flexShrink: 0,
          }}
        >
          <span style={{ fontSize: FONT.md, fontWeight: 600, color: APP.text1, flexShrink: 0 }}>
            {patientName}
          </span>
          <div
            style={{
              flex: 1,
              fontSize: FONT.sm,
              color: APP.text3,
              minWidth: 0,
            }}
          >
            <Ellipsis
              direction="end"
              content={contextBits.length > 0 ? `· ${contextBits.join(" · ")}` : ""}
              rows={1}
            />
          </div>
        </div>
      )}

      {/* Scrollable content */}
      <div
        style={{
          ...scrollable,
          paddingBottom: hasSuggestions ? 96 : 24,
        }}
      >
        {/* Record detail — the actual content doctor needs to judge AI */}
        <RecordSummaryCard record={record} />

        {/* Section header + progress (inside scroll so it doesn't pin) */}
        {hasSuggestions && (
          <div
            style={{
              padding: "14px 16px 8px",
              display: "flex",
              alignItems: "baseline",
              justifyContent: "space-between",
            }}
          >
            <span style={{ fontSize: FONT.base, fontWeight: 600, color: APP.text2 }}>
              AI 诊断建议
            </span>
            <span style={{ fontSize: FONT.sm, color: APP.text4 }}>
              {decidedCount} / {(suggestions || []).length} 已确认
            </span>
          </div>
        )}

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

        {/* Loading / polling state */}
        {(loading || (!loading && !hasSuggestions && isPendingReview)) && (
          <LoadingCard />
        )}

        {/* Diagnosis failed — retry */}
        {!loading && !hasSuggestions && isDiagnosisFailed && (
          <Card style={{ margin: "8px 12px", borderRadius: RADIUS.md, textAlign: "center" }}>
            <div style={{ fontSize: FONT.sm, color: APP.danger, marginBottom: 12 }}>
              AI 诊断超时，请重试
            </div>
            <Button color="primary" fill="none" size="small" onClick={handleTriggerDiagnosis}>
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
            <Button color="primary" fill="none" size="small" onClick={handleTriggerDiagnosis}>
              请 AI 分析此病历
            </Button>
          </Card>
        )}

        {/* Flat suggestion list — no categories, no urgency */}
        {hasSuggestions && (suggestions || []).map((s) => (
          <SuggestionCard
            key={s.id}
            suggestion={s}
            onDecide={handleDecide}
            knowledgeMap={knowledgeMap}
            onOpenCitation={handleOpenCitation}
          />
        ))}

        {/* Inline "+ 添加我的建议" bottom of list — always visible */}
        {hasSuggestions && !addingCustom && (
          <div
            onClick={() => setAddingCustom(true)}
            style={{
              margin: "0 12px 12px",
              padding: "14px",
              textAlign: "center",
              border: `1px dashed ${APP.border}`,
              borderRadius: RADIUS.md,
              background: APP.surface,
              color: APP.text3,
              fontSize: FONT.sm,
              cursor: "pointer",
            }}
          >
            + 添加我的建议
          </div>
        )}

        {/* Inline composer opens in place when doctor taps the button above */}
        {addingCustom && (
          <div
            style={{
              background: APP.surface,
              border: `0.5px dashed ${APP.border}`,
              borderRadius: RADIUS.md,
              padding: 14,
              margin: "0 12px 12px",
            }}
          >
            <TextArea
              placeholder="建议内容"
              value={customText}
              onChange={setCustomText}
              autoSize={{ minRows: 1, maxRows: 3 }}
              style={{ marginBottom: 8, fontSize: FONT.md }}
            />
            <TextArea
              placeholder="详细说明（可选）"
              value={customDetail}
              onChange={setCustomDetail}
              autoSize={{ minRows: 1, maxRows: 4 }}
              style={{ fontSize: FONT.sm }}
            />
            <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
              <button
                onClick={() => { setAddingCustom(false); setCustomText(""); setCustomDetail(""); }}
                style={{
                  flex: 1, padding: "8px 0",
                  background: APP.surface,
                  border: `0.5px solid ${APP.border}`,
                  borderRadius: RADIUS.sm,
                  color: APP.text2, fontSize: FONT.sm, fontWeight: 500,
                  cursor: "pointer",
                }}
              >
                取消
              </button>
              <button
                onClick={submitCustom}
                disabled={!customText.trim()}
                style={{
                  flex: 1, padding: "8px 0",
                  background: APP.primary,
                  border: "none",
                  borderRadius: RADIUS.sm,
                  color: APP.white, fontSize: FONT.sm, fontWeight: 500,
                  cursor: customText.trim() ? "pointer" : "not-allowed",
                  opacity: customText.trim() ? 1 : 0.5,
                }}
              >
                添加
              </button>
            </div>
          </div>
        )}
        <div ref={scrollBottomRef} />
      </div>


      {/* Sticky bottom CTA */}
      {hasSuggestions && (
        <ActionFooter style={{ position: "absolute", bottom: 0, left: 0, right: 0, flexDirection: "column", gap: 4 }}>
          {!allDecided && (
            <div style={{ fontSize: FONT.sm, color: APP.text4, textAlign: "center" }}>
              还有 {undecidedCount} 项待处理
            </div>
          )}
          <Button
            block
            color="primary"
            size="large"
            disabled={!allDecided || finalizing}
            loading={finalizing}
            onClick={handleFinalize}
          >
            {allDecided
              ? "确认诊断"
              : `确认诊断（${decidedCount} / ${(suggestions || []).length}）`}
          </Button>
        </ActionFooter>
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
      {citationPopupNode}
    </div>
  );
}
