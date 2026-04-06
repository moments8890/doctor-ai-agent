/**
 * ReviewSubpage — shared presentational review UI for diagnosis suggestions.
 *
 * Displays record summary, then checklist-style suggestion rows grouped by
 * section (differential, workup, treatment). Each row has three states:
 * collapsed (compact), expanded (detail + actions), confirmed (green check).
 *
 * Used by both real ReviewPage (API data) and MockPages (static data).
 *
 * @see /mock/doctor-pages → 诊断审核
 */
import { useState } from "react";
import { Box, TextField, Typography } from "@mui/material";
import SubpageHeader from "../../../components/SubpageHeader";
import AppButton from "../../../components/AppButton";
import { TYPE, COLOR } from "../../../theme";

const SECTIONS = [
  { key: "differential", label: "鉴别诊断" },
  { key: "workup",       label: "检查建议" },
  { key: "treatment",    label: "治疗方向" },
];

/* ── Inline add form ── */

function InlineAddForm({ onSubmit, onCancel }) {
  const [content, setContent] = useState("");
  const [detail, setDetail] = useState("");

  return (
    <Box sx={{ px: 2, pb: 1.5, borderTop: `0.5px solid ${COLOR.borderLight}` }}>
      <TextField
        fullWidth size="small" placeholder="建议内容"
        value={content} onChange={(e) => setContent(e.target.value)}
        sx={{ mt: 1, mb: 1, "& .MuiInputBase-root": { fontSize: TYPE.secondary.fontSize, bgcolor: COLOR.surface } }}
      />
      <TextField
        fullWidth size="small" placeholder="详细说明（可选）"
        value={detail} onChange={(e) => setDetail(e.target.value)}
        multiline minRows={1} maxRows={3}
        sx={{ mb: 1, "& .MuiInputBase-root": { fontSize: TYPE.caption.fontSize, bgcolor: COLOR.surface } }}
      />
      <Box sx={{ display: "flex", gap: 2, justifyContent: "flex-end" }}>
        <Box onClick={onCancel}
          sx={{ minHeight: 32, display: "inline-flex", alignItems: "center", fontSize: TYPE.body.fontSize, color: COLOR.text4, cursor: "pointer", "&:active": { opacity: 0.6 } }}>
          取消
        </Box>
        <Box onClick={() => { if (content.trim()) onSubmit(content.trim(), detail.trim()); }}
          sx={{
            minHeight: 32, display: "inline-flex", alignItems: "center", fontSize: TYPE.body.fontSize, color: COLOR.primary,
            cursor: content.trim() ? "pointer" : "default", opacity: content.trim() ? 1 : 0.35,
            "&:active": content.trim() ? { opacity: 0.7 } : {},
          }}>
          添加
        </Box>
      </Box>
    </Box>
  );
}

/* ── Checklist section ── */

function ChecklistSection({ sectionKey, label, items, onDecide, onAdd, knowledgeMap }) {
  const [expandedId, setExpandedId] = useState(null);
  const [adding, setAdding] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [editText, setEditText] = useState("");
  const [editDetail, setEditDetail] = useState("");
  if ((!items || items.length === 0) && !adding) return null;

  return (
    <>
      <Box sx={{ px: 2, py: 1, bgcolor: COLOR.surfaceAlt }}>
        <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <Typography sx={{ fontSize: TYPE.micro.fontSize, fontWeight: 600, color: COLOR.text4, letterSpacing: 0.3 }}>{label}</Typography>
          <Typography onClick={() => setAdding(prev => !prev)}
            sx={{ fontSize: TYPE.micro.fontSize, color: adding ? COLOR.text4 : COLOR.primary, cursor: "pointer" }}>
            {adding ? "取消" : "+ 添加"}
          </Typography>
        </Box>
      </Box>

      {adding && (
        <Box sx={{ bgcolor: COLOR.white, borderTop: `0.5px solid ${COLOR.border}`, borderBottom: `0.5px solid ${COLOR.border}` }}>
          <InlineAddForm
            onSubmit={(content, detail) => { onAdd?.(sectionKey, content, detail); setAdding(false); }}
            onCancel={() => setAdding(false)}
          />
        </Box>
      )}

      <Box sx={{ bgcolor: COLOR.white, borderTop: `0.5px solid ${COLOR.border}`, borderBottom: `0.5px solid ${COLOR.border}` }}>
        {(items || []).map((s) => {
          const isConfirmed = s.decision === "confirmed" || s.decision === "edited";
          const isRejected = s.decision === "rejected";
          const isExpanded = expandedId === s.id;
          const citedRules = (s.cited_knowledge_ids || []).map(id => knowledgeMap[id]).filter(Boolean);

          return (
            <Box key={s.id} sx={{ borderBottom: `0.5px solid ${COLOR.borderLight}`, "&:last-child": { borderBottom: "none" } }}>
              <Box sx={{
                display: "flex", alignItems: "flex-start", gap: 1.5, px: 2, py: 1.5,
                cursor: "pointer",
                ...(isExpanded ? { bgcolor: COLOR.surface } : {}),
                ...(isRejected ? { opacity: 0.4 } : {}),
              }}>
                {/* Checkbox */}
                <Box onClick={(e) => { e.stopPropagation(); onDecide(s.id, isConfirmed ? "rejected" : "confirmed", {}); }}
                  sx={{ width: 18, height: 18, borderRadius: "50%", flexShrink: 0, mt: 0.5, cursor: "pointer",
                    ...(isConfirmed
                      ? { bgcolor: COLOR.primary, display: "flex", alignItems: "center", justifyContent: "center" }
                      : { border: `1.5px solid ${COLOR.border}` }),
                  }}>
                  {isConfirmed && <Typography sx={{ color: COLOR.white, fontSize: 11, lineHeight: 1 }}>✓</Typography>}
                </Box>

                {/* Content — tap to expand */}
                <Box onClick={() => { if (editingId !== s.id) setExpandedId(isExpanded ? null : s.id); }} sx={{ flex: 1, minWidth: 0 }}>
                  {editingId === s.id ? (
                    <Box onClick={(e) => e.stopPropagation()}>
                      <TextField fullWidth size="small" multiline minRows={1} maxRows={3} autoFocus
                        placeholder="建议内容"
                        value={editText} onChange={(e) => setEditText(e.target.value)}
                        sx={{ mb: 1, "& .MuiOutlinedInput-root": { fontSize: TYPE.action.fontSize } }} />
                      <TextField fullWidth size="small" multiline minRows={2} maxRows={6}
                        placeholder="详细说明"
                        value={editDetail} onChange={(e) => setEditDetail(e.target.value)}
                        sx={{ "& .MuiOutlinedInput-root": { fontSize: TYPE.secondary.fontSize } }} />
                      <Box sx={{ display: "flex", gap: 2, mt: 1 }}>
                        <Typography onClick={() => { onDecide(s.id, "edited", { edited_text: editText, detail: editDetail }); setEditingId(null); }}
                          sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.primary, fontWeight: 500, cursor: "pointer" }}>保存</Typography>
                        <Typography onClick={() => setEditingId(null)}
                          sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text4, cursor: "pointer" }}>取消</Typography>
                      </Box>
                    </Box>
                  ) : (
                    <>
                      <Typography sx={{ fontSize: TYPE.action.fontSize, fontWeight: 500, color: isRejected ? COLOR.text4 : COLOR.text1 }}>
                        {s.edited_text || s.content}
                        {!isExpanded && !isConfirmed && !isRejected && <Box component="span" sx={{ fontSize: 11, color: COLOR.text4, ml: 0.5 }}>▾</Box>}
                      </Typography>
                      {isExpanded && (
                        <Box sx={{ mt: 1 }}>
                          {s.detail && (
                            <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text3, lineHeight: 1.6, mb: 1 }}>
                              {s.detail}
                            </Typography>
                          )}
                          {citedRules.length > 0 && (
                            <Box sx={{ mb: 1 }}>
                              {citedRules.map(rule => (
                                <Typography key={rule.id} sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.danger }}>
                                  引用: {rule.title}
                                </Typography>
                              ))}
                            </Box>
                          )}
                          {s.rule_cited && citedRules.length === 0 && (
                            <Typography sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.danger, mb: 1 }}>
                              引用: {s.rule_cited}
                            </Typography>
                          )}
                          <Box sx={{ display: "flex", gap: 2, pt: 1, borderTop: `0.5px solid ${COLOR.borderLight}` }}>
                            {!isConfirmed && <Typography onClick={(e) => { e.stopPropagation(); onDecide(s.id, "confirmed", {}); }}
                              sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.primary, fontWeight: 500, cursor: "pointer" }}>确认</Typography>}
                            <Typography onClick={(e) => { e.stopPropagation(); setEditText(s.edited_text || s.content); setEditDetail(s.detail || ""); setEditingId(s.id); }}
                              sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text4, cursor: "pointer" }}>修改</Typography>
                            <Typography onClick={(e) => { e.stopPropagation(); onDecide(s.id, "rejected", { reason: "removed" }); }}
                              sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text4, cursor: "pointer" }}>移除</Typography>
                          </Box>
                        </Box>
                      )}
                    </>
                  )}
                </Box>
              </Box>
            </Box>
          );
        })}
      </Box>
    </>
  );
}

/* ── Main ── */

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
  const hasSuggestions = suggestions.length > 0;
  const isDecided = (s) =>
    s.decision === "confirmed" || s.decision === "rejected" ||
    s.decision === "edited" || s.decision === "custom";
  const allDecided = hasSuggestions && suggestions.every(isDecided);
  const undecidedCount = suggestions.filter((s) => !isDecided(s)).length;

  // Group suggestions by section
  const grouped = {};
  SECTIONS.forEach((s) => { grouped[s.key] = []; });
  suggestions.forEach((s) => {
    if (grouped[s.section]) grouped[s.section].push(s);
  });

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%", bgcolor: COLOR.surfaceAlt }}>
      <SubpageHeader title="诊断审核" onBack={onBack} right={headerRight} />

      <Box sx={{ flex: 1, overflow: "auto", pb: hasSuggestions ? "80px" : 2 }}>
        {children}

        {hasSuggestions && (
          <Box sx={{ px: 2, py: 1, bgcolor: COLOR.surfaceAlt, borderTop: `0.5px solid ${COLOR.border}`, borderBottom: `0.5px solid ${COLOR.border}` }}>
            <Typography sx={{ fontSize: TYPE.micro.fontSize, fontWeight: 600, color: COLOR.text4, letterSpacing: 0.3 }}>
              AI 诊断建议
            </Typography>
          </Box>
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
      </Box>

      {hasSuggestions && (
        <Box sx={{ position: "absolute", bottom: 0, left: 0, right: 0, px: 2, pt: 1.5, pb: "calc(12px + env(safe-area-inset-bottom))", bgcolor: COLOR.white, borderTop: `0.5px solid ${COLOR.border}` }}>
          <AppButton variant="primary" size="lg" fullWidth onClick={onFinalize} loading={finalizing} loadingLabel="提交中..." disabled={!allDecided}>
            {allDecided ? "完成审核" : `还有 ${undecidedCount} 项未处理`}
          </AppButton>
        </Box>
      )}
    </Box>
  );
}
