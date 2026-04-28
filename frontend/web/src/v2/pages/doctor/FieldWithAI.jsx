/**
 * FieldWithAI — inline per-field review row for the v2 ReviewPage.
 *
 * Visual reference: docs/specs/2026-04-20-mockups/inline-suggestions-review.html
 *
 * Three layouts inside one component:
 *   - 诊断 / 治疗方向: editable textarea + 1 AI pending row (no 换一条)
 *   - 检查建议: stack of accepted ✓ rows + 1 AI pending row (with 换一条)
 *
 * Props are intentionally narrow. Parent owns the editable textarea state
 * and decision handlers. `pendingIndex` for workup cycle is local to this
 * component — session-only per spec.
 */
import { useState, useMemo } from "react";
import { TextArea, Swiper } from "antd-mobile";
import LocalHospitalOutlinedIcon from "@mui/icons-material/LocalHospitalOutlined";
import BiotechOutlinedIcon from "@mui/icons-material/BiotechOutlined";
import MedicationOutlinedIcon from "@mui/icons-material/MedicationOutlined";
import { APP, FONT, RADIUS, ICON } from "../../theme";

const SECTION_ICONS = {
  differential: LocalHospitalOutlinedIcon,
  workup: BiotechOutlinedIcon,
  treatment: MedicationOutlinedIcon,
};

function pickTopPending(sections) {
  // Priority: is_custom > (not rejected/confirmed/edited) > id asc
  const eligible = sections.filter(
    (s) => s.decision == null || s.decision === "pending"
  );
  if (eligible.length === 0) return null;
  const customs = eligible.filter((s) => s.is_custom);
  const pool = customs.length > 0 ? customs : eligible;
  return [...pool].sort((a, b) => (a.id || 0) - (b.id || 0))[0];
}

function isAcceptedDecision(decision) {
  return decision === "confirmed" || decision === "edited" || decision === "custom";
}

function AcceptedRow({ text, note, expanded, onClick }) {
  return (
    <div
      onClick={onClick}
      style={{
        padding: "7px 14px",
        borderTop: `0.5px solid ${APP.borderLight}`,
        background: APP.primaryLight,
        display: "flex",
        alignItems: "center",
        gap: 8,
        fontSize: FONT.sm,
        lineHeight: 1.5,
        cursor: onClick ? "pointer" : "default",
      }}
    >
      <span
        style={{
          width: 16,
          height: 16,
          flexShrink: 0,
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
          background: APP.primary,
          color: APP.white,
          borderRadius: "50%",
          fontSize: 10, // lint-ui-ignore: decorative badge glyph (✓ inside 16px circle)
          fontWeight: 700,
        }}
      >
        ✓
      </span>
      <span style={{ flex: 1, color: APP.text2 }}>
        已采纳：<b style={{ color: APP.text1, fontWeight: 600 }}>{text}</b>
        {note && (
          <span
            style={{
              color: APP.text4,
              fontSize: FONT.xs,
              fontWeight: 400,
              marginLeft: 4,
            }}
          >
            · {note}
          </span>
        )}
      </span>
      {onClick && (
        <span
          style={{
            fontSize: FONT.xs,
            color: APP.text4,
            flexShrink: 0,
            transform: expanded ? "rotate(90deg)" : "none",
            transition: "transform 0.15s ease",
          }}
        >
          ›
        </span>
      )}
    </div>
  );
}

function AIPendingRow({
  suggestion,
  counter,
  allowCycle,
  onAccept,
  onCycle,
  onEdit,
  cycleExhausted,
  knowledgeMap,
  onOpenCitation,
  onOpenFeedback,
}) {
  const s = suggestion;
  const citedRules = (s.cited_knowledge_ids || [])
    .map((id) => knowledgeMap?.[id])
    .filter(Boolean);

  return (
    <div
      style={{
        padding: "8px 14px 10px",
        borderTop: `0.5px solid ${APP.borderLight}`,
        background: APP.surface,
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "baseline",
          gap: 8,
          marginBottom: 2,
        }}
      >
        <span
          style={{
            fontSize: FONT.md,
            color: APP.text1,
            lineHeight: 1.4,
            fontWeight: 600,
            flex: 1,
            minWidth: 0,
          }}
        >
          {s.edited_text || s.content}
        </span>
        {counter && (
          <span
            style={{
              fontSize: FONT.xs,
              color: APP.text4,
              flexShrink: 0,
            }}
          >
            {counter}
          </span>
        )}
      </div>
      {/* Detail message — the "详细说明" prose. Editable via the 修改 form;
          always rendered when present so the doctor sees the full message
          without having to open edit mode. */}
      {s.detail && s.detail.trim().length > 0 && (
        <div
          style={{
            marginTop: 4,
            fontSize: FONT.sm,
            color: APP.text2,
            lineHeight: 1.55,
            whiteSpace: "pre-wrap",
          }}
        >
          {s.detail}
        </div>
      )}
      {/* Compact supporting context — kept visible (safety + reasoning) but
          rendered as one-line muted text so the diagnosis title stays the
          primary visual anchor. Capped at 2 items each: more than that pushes
          the title down and overwhelms the card. */}
      {s.evidence && s.evidence.length > 0 && (
        <div
          style={{
            marginTop: 4,
            fontSize: FONT.xs,
            color: APP.text4,
            lineHeight: 1.5,
          }}
        >
          <span style={{ fontWeight: 500 }}>依据：</span>
          {s.evidence.slice(0, 2).join("、")}
        </div>
      )}
      {s.risk_signals && s.risk_signals.length > 0 && (
        <div
          style={{
            marginTop: 2,
            fontSize: FONT.xs,
            color: APP.text4,
            lineHeight: 1.5,
          }}
        >
          <span style={{ fontWeight: 500, color: APP.danger || "#d92d2d" }}>
            风险监测：
          </span>
          {s.risk_signals.slice(0, 2).join("、")}
        </div>
      )}
      {citedRules.length > 0 && (
        <div style={{ marginTop: 4, display: "grid", gap: 4, justifyItems: "start" }}>
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
      {/* Action row: 反馈 leftmost, decisions (修改 / 采纳, plus optional
          换一条) grouped on the right. Mirrors the standalone ReviewPage
          SuggestionCard layout so doctors get a consistent action map. */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginTop: 8,
        }}
      >
        {onOpenFeedback ? (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onOpenFeedback(suggestion);
            }}
            title="反馈这条建议不合理"
            aria-label="反馈"
            style={{
              fontSize: FONT.sm,
              color: APP.text4,
              background: "none",
              border: "none",
              padding: 0,
              cursor: "pointer",
              display: "inline-flex",
              alignItems: "center",
              gap: 4,
              fontFamily: "inherit",
            }}
          >
            <svg
              viewBox="0 0 24 24"
              width="14"
              height="14"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.6"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <path d="M4 21V4h12l-2 4h6v8H8v5H4z" />
            </svg>
            反馈
          </button>
        ) : (
          <span />
        )}
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          {allowCycle && (
            <button
              onClick={cycleExhausted ? undefined : onCycle}
              disabled={cycleExhausted}
              style={{
                fontSize: FONT.sm,
                color: cycleExhausted ? APP.text4 : APP.primary,
                fontWeight: 500,
                background: "none",
                border: "none",
                padding: 0,
                cursor: cycleExhausted ? "not-allowed" : "pointer",
              }}
            >
              {cycleExhausted ? "已看完" : "换一条"}
            </button>
          )}
          <button
            onClick={onEdit}
            style={{
              fontSize: FONT.sm,
              color: APP.primary,
              fontWeight: 500,
              background: "none",
              border: "none",
              padding: 0,
              cursor: "pointer",
            }}
          >
            修改
          </button>
          <button
            onClick={onAccept}
            style={{
              padding: "5px 14px",
              borderRadius: RADIUS.xs,
              background: APP.primary,
              color: APP.white,
              fontSize: FONT.sm,
              fontWeight: 500,
              border: "none",
              cursor: "pointer",
            }}
          >
            采纳
          </button>
        </div>
      </div>
    </div>
  );
}

function EditInline({ initialText, initialDetail, onCancel, onSave }) {
  const [text, setText] = useState(initialText || "");
  const [detail, setDetail] = useState(initialDetail || "");

  return (
    <div
      style={{
        padding: "10px 14px",
        borderTop: `0.5px solid ${APP.borderLight}`,
        background: APP.editBg,
      }}
    >
      <TextArea
        placeholder="建议内容"
        value={text}
        onChange={setText}
        autoSize={{ minRows: 1, maxRows: 3 }}
        style={{ marginBottom: 8, fontSize: FONT.sm }}
      />
      <TextArea
        placeholder="详细说明（可选）"
        value={detail}
        onChange={setDetail}
        autoSize={{ minRows: 1, maxRows: 3 }}
        style={{ fontSize: FONT.xs }}
      />
      <div style={{ display: "flex", gap: 16, justifyContent: "flex-end", marginTop: 8 }}>
        <button
          onClick={onCancel}
          style={{
            fontSize: FONT.sm,
            color: APP.text4,
            background: "none",
            border: "none",
            padding: 0,
            cursor: "pointer",
          }}
        >
          取消
        </button>
        <button
          onClick={() => {
            const t = text.trim();
            if (!t) return;
            onSave(t, detail.trim());
          }}
          style={{
            padding: "5px 14px",
            borderRadius: RADIUS.xs,
            background: APP.primary,
            color: APP.white,
            fontSize: FONT.sm,
            fontWeight: 500,
            border: "none",
            cursor: "pointer",
          }}
        >
          保存
        </button>
      </div>
    </div>
  );
}

/**
 * @param {string} label - 诊断 / 检查建议 / 治疗方向
 * @param {string} sectionKey - differential / workup / treatment
 * @param {boolean} allowCycle - true for workup only
 * @param {string|null} editableFieldValue - current value for diagnosis/treatment_plan (null for workup)
 * @param {(v:string)=>void} onEditableFieldChange - updates the editable textarea value
 * @param {Array} suggestions - all suggestions for this section
 * @param {object} knowledgeMap - id -> knowledge item (for citations)
 * @param {(id:number, decision:string, opts:object)=>Promise} onDecide
 * @param {(editing:boolean)=>void} onEditingChange - notify parent when local edit mode toggles
 */
export default function FieldWithAI({
  label,
  sectionKey,
  allowCycle,
  editableFieldValue,
  onEditableFieldChange,
  suggestions,
  knowledgeMap,
  onDecide,
  onOpenCitation,
  onEditingChange,
  onOpenFeedback,
}) {
  const hasEditableField = editableFieldValue !== null && editableFieldValue !== undefined;

  // Pending (undecided) suggestions, sorted: custom first, then id asc
  const pendingSorted = useMemo(() => {
    const eligible = (suggestions || []).filter(
      (s) => s.decision == null || s.decision === "pending"
    );
    const customs = eligible.filter((s) => s.is_custom);
    const nonCustom = eligible.filter((s) => !s.is_custom);
    // For non-workup: custom wins; for workup: LLM output order, customs at bottom
    if (allowCycle) {
      return [
        ...nonCustom.sort((a, b) => (a.id || 0) - (b.id || 0)),
        ...customs.sort((a, b) => (a.id || 0) - (b.id || 0)),
      ];
    }
    const top = pickTopPending(eligible);
    return top ? [top] : [];
  }, [suggestions, allowCycle]);

  const accepted = useMemo(
    () => (suggestions || []).filter((s) => isAcceptedDecision(s.decision)),
    [suggestions]
  );

  const [pendingIndex, setPendingIndex] = useState(0);
  const [editingId, setEditingId] = useState(null);

  const total = pendingSorted.length + accepted.length;
  const safeIndex = Math.min(pendingIndex, Math.max(pendingSorted.length - 1, 0));
  const currentPending = pendingSorted[safeIndex] || null;
  const cycleExhausted = allowCycle && safeIndex >= pendingSorted.length - 1;

  function notifyEditing(flag) {
    onEditingChange?.(flag);
  }

  function handleAcceptCurrent() {
    if (!currentPending) return;
    onDecide(currentPending.id, "confirmed", {});
    if (hasEditableField) {
      // For 诊断/治疗: overwrite the editable textarea value
      onEditableFieldChange(currentPending.edited_text || currentPending.content || "");
    }
    // For workup, pendingIndex stays — next pending will promote naturally
    // once the suggestion list re-filters (current one moves to accepted).
    // But to be robust (parent doesn't re-mount), reset index to 0.
    setPendingIndex(0);
  }

  function handleCycle() {
    if (!allowCycle) return;
    setPendingIndex((i) => Math.min(i + 1, pendingSorted.length - 1));
  }

  function startEdit(s) {
    setEditingId(s.id);
    notifyEditing(true);
  }

  function cancelEdit() {
    setEditingId(null);
    notifyEditing(false);
  }

  function saveEdit(s, text, detail) {
    onDecide(s.id, "edited", { edited_text: text, detail });
    if (hasEditableField) {
      onEditableFieldChange(text);
    }
    setEditingId(null);
    notifyEditing(false);
    setPendingIndex(0);
  }

  const isEmpty = pendingSorted.length === 0 && accepted.length === 0;
  const editingPending = currentPending && editingId === currentPending.id;

  const metaText = allowCycle
    ? accepted.length > 0
      ? `已采纳 ${accepted.length} 条 · 还剩 ${pendingSorted.length} 条`
      : total >= 2
      ? `共 ${total} 条`
      : null
    : accepted.length > 0
    ? "已处理"
    : null;

  return (
    <div
      style={{
        background: APP.surface,
        margin: "0 12px 6px",
        border: `0.5px solid ${editingPending ? APP.primary : APP.border}`,
        borderRadius: RADIUS.md,
        overflow: "hidden",
        boxShadow: editingPending ? `0 0 0 1px ${APP.primaryLight}` : "none",
      }}
    >
      {/* Label row */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "8px 14px 4px",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 6,
            fontSize: FONT.base,
            fontWeight: 600,
            color: APP.text1,
          }}
        >
          {(() => {
            const SectionIcon = SECTION_ICONS[sectionKey];
            return SectionIcon ? (
              <SectionIcon sx={{ fontSize: ICON.xs, color: APP.primary }} />
            ) : null;
          })()}
          {label}
        </div>
        {metaText && (
          <div style={{ fontSize: FONT.xs, color: APP.text4 }}>{metaText}</div>
        )}
      </div>

      {/* Synthetic ✓ row for the editable field (诊断/治疗). The field text
          is the single source of truth — no separate textarea, no duplication
          with the accepted array. Click to expand + edit. */}
      {hasEditableField && (editableFieldValue || "").trim().length > 0 && (() => {
        const isExpanded = editingId === "__field__";
        return (
          <div>
            <AcceptedRow
              text={editableFieldValue}
              note={null}
              expanded={isExpanded}
              onClick={() =>
                isExpanded ? cancelEdit() : (setEditingId("__field__"), notifyEditing(true))
              }
            />
            {isExpanded && (
              <EditInline
                initialText={editableFieldValue}
                initialDetail=""
                onCancel={cancelEdit}
                onSave={(text /* detail unused for field edits */) => {
                  onEditableFieldChange(text);
                  setEditingId(null);
                  notifyEditing(false);
                }}
              />
            )}
          </div>
        );
      })()}

      {/* Accepted ✓ rows from suggestions array — workup only. For 诊断/治疗,
          accept writes into editableFieldValue which renders as the synthetic
          row above, so we skip the array here to avoid duplication. */}
      {!hasEditableField &&
        accepted.map((s) => {
          const isExpanded = editingId === s.id;
          return (
            <div key={s.id}>
              <AcceptedRow
                text={s.edited_text || s.content}
                note={null}
                expanded={isExpanded}
                onClick={() => (isExpanded ? cancelEdit() : startEdit(s))}
              />
              {isExpanded && (
                <EditInline
                  initialText={s.edited_text || s.content || ""}
                  initialDetail={s.detail || ""}
                  onCancel={cancelEdit}
                  onSave={(text, detail) => saveEdit(s, text, detail)}
                />
              )}
            </div>
          );
        })}

      {/* Current pending AI row(s) or inline editor */}
      {allowCycle && pendingSorted.length > 1 && !editingPending ? (
        // Workup with 2+ pending — swipe carousel replaces 换一条
        <Swiper
          key={pendingSorted.map((s) => s.id).join(",")}
          defaultIndex={0}
          loop={false}
          autoplay={false}
          indicator={(total, current) => (
            <div
              style={{
                position: "absolute",
                bottom: 8,
                left: 0,
                right: 0,
                display: "flex",
                justifyContent: "center",
                gap: 6,
                pointerEvents: "none",
              }}
            >
              {Array.from({ length: total }, (_, i) => (
                <span
                  key={i}
                  style={{
                    width: 6,
                    height: 6,
                    borderRadius: "50%",
                    background:
                      i === current ? APP.primary : "rgba(22,36,27,0.16)",
                    transition: "background 0.2s",
                  }}
                />
              ))}
            </div>
          )}
          style={{ "--height": "auto" }}
        >
          {pendingSorted.map((s, idx) => (
            <Swiper.Item key={s.id}>
              <div style={{ paddingBottom: 20 }}>
                <AIPendingRow
                  suggestion={s}
                  counter={`${idx + 1} / ${pendingSorted.length + accepted.length}${
                    pendingSorted.length === 1 ? " · 最后一条" : ""
                  }`}
                  allowCycle={false}
                  cycleExhausted={false}
                  onAccept={() => {
                    onDecide(s.id, "confirmed", {});
                    if (hasEditableField) {
                      onEditableFieldChange(s.edited_text || s.content || "");
                    }
                  }}
                  onCycle={undefined}
                  onEdit={() => startEdit(s)}
                  knowledgeMap={knowledgeMap}
                  onOpenCitation={onOpenCitation}
                  onOpenFeedback={
                    onOpenFeedback
                      ? () => onOpenFeedback({ ...s, section: sectionKey })
                      : undefined
                  }
                />
              </div>
            </Swiper.Item>
          ))}
        </Swiper>
      ) : editingPending ? (
        <EditInline
          initialText={currentPending.edited_text || currentPending.content || ""}
          initialDetail={currentPending.detail || ""}
          onCancel={cancelEdit}
          onSave={(text, detail) => saveEdit(currentPending, text, detail)}
        />
      ) : currentPending &&
        // Hide pending AI for 诊断/治疗 once the field already has a value —
        // doctor picked one, doesn't need another competing proposal.
        !(hasEditableField && (editableFieldValue || "").trim().length > 0) ? (
        <AIPendingRow
          suggestion={currentPending}
          counter={
            allowCycle && pendingSorted.length + accepted.length >= 2
              ? `${safeIndex + 1} / ${pendingSorted.length + accepted.length}${
                  pendingSorted.length === 1 ? " · 最后一条" : ""
                }`
              : null
          }
          allowCycle={false}
          cycleExhausted={false}
          onAccept={handleAcceptCurrent}
          onCycle={handleCycle}
          onEdit={() => startEdit(currentPending)}
          knowledgeMap={knowledgeMap}
          onOpenCitation={onOpenCitation}
          onOpenFeedback={
            onOpenFeedback
              ? () =>
                  onOpenFeedback({ ...currentPending, section: sectionKey })
              : undefined
          }
        />
      ) : isEmpty &&
        // Suppress the empty-state hint when the editable field already has
        // content — the synthetic ✓ row above already shows the doctor's
        // value, so "暂无 AI 建议 · 手动填写" is misleading.
        !(hasEditableField && (editableFieldValue || "").trim().length > 0) ? (
        <div
          style={{
            padding: "7px 14px",
            borderTop: `0.5px solid ${APP.borderLight}`,
            background: APP.surfaceAlt,
            fontSize: FONT.sm,
            color: APP.text4,
          }}
        >
          暂无 AI 建议 · 手动填写
        </div>
      ) : null}
    </div>
  );
}
