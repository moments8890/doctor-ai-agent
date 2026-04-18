/**
 * @route /doctor/settings/review
 *
 * ReviewSubpage v2 — diagnosis suggestions checklist.
 * Presentational component; receives data + callbacks from parent.
 * Also usable standalone as a settings subpage for editing suggestion templates.
 * antd-mobile only, no MUI.
 */
import { useState } from "react";
import { NavBar, Button, TextArea, Dialog } from "antd-mobile";
import { CheckOutline } from "antd-mobile-icons";
import { useNavigate } from "react-router-dom";
import { APP } from "../../../theme";

const SECTIONS = [
  { key: "differential", label: "鉴别诊断" },
  { key: "workup", label: "检查建议" },
  { key: "treatment", label: "治疗方向" },
];

// ── Inline add form ────────────────────────────────────────────────

function InlineAddForm({ onSubmit, onCancel }) {
  const [content, setContent] = useState("");
  const [detail, setDetail] = useState("");

  return (
    <div
      style={{
        padding: "12px 16px",
        borderTop: `0.5px solid ${APP.borderLight}`,
        backgroundColor: APP.surface,
      }}
    >
      <TextArea
        placeholder="建议内容"
        value={content}
        onChange={setContent}
        autoSize={{ minRows: 1, maxRows: 3 }}
        style={{
          "--font-size": "14px",
          backgroundColor: APP.surfaceAlt,
          borderRadius: 6,
          padding: "8px 10px",
          border: `0.5px solid ${APP.border}`,
          marginBottom: 8,
        }}
      />
      <TextArea
        placeholder="详细说明（可选）"
        value={detail}
        onChange={setDetail}
        autoSize={{ minRows: 1, maxRows: 3 }}
        style={{
          "--font-size": "13px",
          backgroundColor: APP.surfaceAlt,
          borderRadius: 6,
          padding: "8px 10px",
          border: `0.5px solid ${APP.border}`,
          marginBottom: 10,
        }}
      />
      <div
        style={{ display: "flex", gap: 16, justifyContent: "flex-end" }}
      >
        <span
          onClick={onCancel}
          style={{
            fontSize: 14,
            color: APP.text4,
            cursor: "pointer",
            padding: "4px 0",
          }}
        >
          取消
        </span>
        <span
          onClick={() => {
            if (content.trim()) onSubmit(content.trim(), detail.trim());
          }}
          style={{
            fontSize: 14,
            color: content.trim() ? "#07C160" : APP.text4,
            cursor: content.trim() ? "pointer" : "default",
            fontWeight: 500,
            padding: "4px 0",
          }}
        >
          添加
        </span>
      </div>
    </div>
  );
}

// ── Checklist section ──────────────────────────────────────────────

function ChecklistSection({ sectionKey, label, items, onDecide, onAdd, knowledgeMap }) {
  const [expandedId, setExpandedId] = useState(null);
  const [adding, setAdding] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [editText, setEditText] = useState("");
  const [editDetail, setEditDetail] = useState("");

  if ((!items || items.length === 0) && !adding) return null;

  return (
    <>
      {/* Section header */}
      <div
        style={{
          padding: "8px 16px",
          backgroundColor: APP.surfaceAlt,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          borderTop: `0.5px solid ${APP.border}`,
          borderBottom: `0.5px solid ${APP.border}`,
        }}
      >
        <span
          style={{
            fontSize: 11,
            fontWeight: 600,
            color: APP.text4,
            letterSpacing: 0.3,
          }}
        >
          {label}
        </span>
        <span
          onClick={() => setAdding((prev) => !prev)}
          style={{
            fontSize: 11,
            color: adding ? APP.text4 : "#07C160",
            cursor: "pointer",
          }}
        >
          {adding ? "取消" : "+ 添加"}
        </span>
      </div>

      {/* Add form */}
      {adding && (
        <InlineAddForm
          onSubmit={(content, detail) => {
            onAdd?.(sectionKey, content, detail);
            setAdding(false);
          }}
          onCancel={() => setAdding(false)}
        />
      )}

      {/* Items */}
      <div
        style={{
          backgroundColor: APP.surface,
          borderBottom: `0.5px solid ${APP.border}`,
        }}
      >
        {(items || []).map((s) => {
          const isConfirmed =
            s.decision === "confirmed" || s.decision === "edited";
          const isRejected = s.decision === "rejected";
          const isExpanded = expandedId === s.id;
          const citedRules = (s.cited_knowledge_ids || [])
            .map((id) => knowledgeMap[id])
            .filter(Boolean);

          return (
            <div
              key={s.id}
              style={{
                borderBottom: `0.5px solid ${APP.borderLight}`,
              }}
            >
              <div
                style={{
                  display: "flex",
                  alignItems: "flex-start",
                  gap: 12,
                  padding: "12px 16px",
                  cursor: "pointer",
                  backgroundColor: isExpanded ? APP.surfaceAlt : APP.surface,
                  opacity: isRejected ? 0.4 : 1,
                }}
              >
                {/* Checkbox circle */}
                <div
                  onClick={(e) => {
                    e.stopPropagation();
                    onDecide(
                      s.id,
                      isConfirmed ? "rejected" : "confirmed",
                      {}
                    );
                  }}
                  style={{
                    width: 18,
                    height: 18,
                    borderRadius: "50%",
                    flexShrink: 0,
                    marginTop: 2,
                    cursor: "pointer",
                    backgroundColor: isConfirmed ? "#07C160" : "transparent",
                    border: isConfirmed
                      ? "none"
                      : `1.5px solid ${APP.border}`,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                  }}
                >
                  {isConfirmed && (
                    <CheckOutline
                      style={{ color: "#fff", fontSize: 11, lineHeight: 1 }}
                    />
                  )}
                </div>

                {/* Content */}
                <div
                  onClick={() => {
                    if (editingId !== s.id)
                      setExpandedId(isExpanded ? null : s.id);
                  }}
                  style={{ flex: 1, minWidth: 0 }}
                >
                  {editingId === s.id ? (
                    <div onClick={(e) => e.stopPropagation()}>
                      <TextArea
                        autoFocus
                        placeholder="建议内容"
                        value={editText}
                        onChange={setEditText}
                        autoSize={{ minRows: 1, maxRows: 3 }}
                        style={{
                          "--font-size": "15px",
                          backgroundColor: APP.surfaceAlt,
                          borderRadius: 6,
                          padding: "6px 10px",
                          border: `0.5px solid ${APP.border}`,
                          marginBottom: 8,
                        }}
                      />
                      <TextArea
                        placeholder="详细说明"
                        value={editDetail}
                        onChange={setEditDetail}
                        autoSize={{ minRows: 2, maxRows: 6 }}
                        style={{
                          "--font-size": "13px",
                          backgroundColor: APP.surfaceAlt,
                          borderRadius: 6,
                          padding: "6px 10px",
                          border: `0.5px solid ${APP.border}`,
                          marginBottom: 8,
                        }}
                      />
                      <div style={{ display: "flex", gap: 16 }}>
                        <span
                          onClick={() => setEditingId(null)}
                          style={{
                            fontSize: 13,
                            color: APP.text4,
                            cursor: "pointer",
                          }}
                        >
                          取消
                        </span>
                        <span
                          onClick={() => {
                            onDecide(s.id, "edited", {
                              edited_text: editText,
                              detail: editDetail,
                            });
                            setEditingId(null);
                          }}
                          style={{
                            fontSize: 13,
                            color: "#07C160",
                            fontWeight: 500,
                            cursor: "pointer",
                          }}
                        >
                          保存
                        </span>
                      </div>
                    </div>
                  ) : (
                    <>
                      <div
                        style={{
                          fontSize: 15,
                          fontWeight: 500,
                          color: isRejected ? APP.text4 : APP.text1,
                        }}
                      >
                        {s.edited_text || s.content}
                        {!isExpanded && !isConfirmed && !isRejected && (
                          <span
                            style={{
                              fontSize: 11,
                              color: APP.text4,
                              marginLeft: 4,
                            }}
                          >
                            ▾
                          </span>
                        )}
                      </div>

                      {isExpanded && (
                        <div style={{ marginTop: 8 }}>
                          {s.detail && (
                            <p
                              style={{
                                fontSize: 13,
                                color: APP.text3,
                                lineHeight: 1.6,
                                margin: "0 0 8px",
                              }}
                            >
                              {s.detail}
                            </p>
                          )}
                          {citedRules.length > 0 && (
                            <div style={{ marginBottom: 8 }}>
                              {citedRules.map((rule) => (
                                <div
                                  key={rule.id}
                                  style={{
                                    fontSize: 11,
                                    color: "#FA5151",
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
                                fontSize: 11,
                                color: "#FA5151",
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
                                onClick={(e) => {
                                  e.stopPropagation();
                                  onDecide(s.id, "confirmed", {});
                                }}
                                style={{
                                  fontSize: 13,
                                  color: "#07C160",
                                  fontWeight: 500,
                                  cursor: "pointer",
                                }}
                              >
                                确认
                              </span>
                            )}
                            <span
                              onClick={(e) => {
                                e.stopPropagation();
                                setEditText(s.edited_text || s.content);
                                setEditDetail(s.detail || "");
                                setEditingId(s.id);
                              }}
                              style={{
                                fontSize: 13,
                                color: APP.text4,
                                cursor: "pointer",
                              }}
                            >
                              修改
                            </span>
                            <span
                              onClick={(e) => {
                                e.stopPropagation();
                                onDecide(s.id, "rejected", {
                                  reason: "removed",
                                });
                              }}
                              style={{
                                fontSize: 13,
                                color: APP.text4,
                                cursor: "pointer",
                              }}
                            >
                              移除
                            </span>
                          </div>
                        </div>
                      )}
                    </>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </>
  );
}

// ── Main ───────────────────────────────────────────────────────────

export default function ReviewSubpage({
  record,
  suggestions = [],
  onDecide,
  onAdd,
  onFinalize,
  onBack,
  finalizing = false,
  headerRight,
  children,
  knowledgeMap = {},
}) {
  const navigate = useNavigate();

  const hasSuggestions = suggestions.length > 0;
  const isDecided = (s) =>
    s.decision === "confirmed" ||
    s.decision === "rejected" ||
    s.decision === "edited" ||
    s.decision === "custom";
  const allDecided = hasSuggestions && suggestions.every(isDecided);
  const undecidedCount = suggestions.filter((s) => !isDecided(s)).length;

  // Group by section
  const grouped = {};
  SECTIONS.forEach((s) => {
    grouped[s.key] = [];
  });
  suggestions.forEach((s) => {
    if (grouped[s.section]) grouped[s.section].push(s);
  });

  function handleBack() {
    if (onBack) {
      onBack();
    } else {
      navigate(-1);
    }
  }

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100%",
        backgroundColor: APP.surfaceAlt,
        overflow: "hidden",
      }}
    >
      <NavBar
        onBack={handleBack}
        right={headerRight || null}
        style={{
          "--height": "44px",
          "--border-bottom": `0.5px solid ${APP.border}`,
          backgroundColor: APP.surface,
          flexShrink: 0,
        }}
      >
        诊断审核
      </NavBar>

      <div
        style={{
          flex: 1,
          overflowY: "auto",
          paddingBottom: hasSuggestions ? 88 : 16,
        }}
      >
        {children}

        {hasSuggestions && (
          <div
            style={{
              padding: "8px 16px",
              backgroundColor: APP.surfaceAlt,
              borderTop: `0.5px solid ${APP.border}`,
              borderBottom: `0.5px solid ${APP.border}`,
            }}
          >
            <span
              style={{
                fontSize: 11,
                fontWeight: 600,
                color: APP.text4,
                letterSpacing: 0.3,
              }}
            >
              AI 诊断建议
            </span>
          </div>
        )}

        {SECTIONS.map((sec) => (
          <ChecklistSection
            key={sec.key}
            sectionKey={sec.key}
            label={sec.label}
            items={grouped[sec.key]}
            onDecide={onDecide}
            onAdd={onAdd}
            knowledgeMap={knowledgeMap}
          />
        ))}
      </div>

      {hasSuggestions && (
        <div
          style={{
            position: "absolute",
            bottom: 0,
            left: 0,
            right: 0,
            padding: "12px 16px",
            paddingBottom:
              "calc(12px + var(--safe-bottom, env(safe-area-inset-bottom)))",
            backgroundColor: APP.surface,
            borderTop: `0.5px solid ${APP.border}`,
          }}
        >
          <Button
            block
            color="primary"
            loading={finalizing}
            disabled={!allDecided}
            onClick={onFinalize}
          >
            {allDecided ? "完成审核" : `还有 ${undecidedCount} 项未处理`}
          </Button>
        </div>
      )}
    </div>
  );
}
