/**
 * ReviewSubpage — shared presentational review UI for diagnosis suggestions.
 *
 * Displays record summary, grouped suggestion sections (differential, workup,
 * treatment), each with DiagnosisCard and inline add. Bottom bar shows
 * progress and finalize button.
 *
 * Used by both real ReviewPage (API data) and MockPages (static data).
 *
 * @see /debug/doctor-pages → 诊断审核
 */
import { useState } from "react";
import { Box, Button, TextField, Typography } from "@mui/material";
import DiagnosisCard from "../../../components/doctor/DiagnosisCard";
import SubpageHeader from "../../../components/SubpageHeader";
import BarButton from "../../../components/BarButton";
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
    <Box sx={{ px: 2, pb: 1.25, borderTop: `0.5px solid ${COLOR.borderLight}` }}>
      <TextField
        fullWidth size="small" placeholder="建议内容"
        value={content} onChange={(e) => setContent(e.target.value)}
        sx={{ mt: 1.1, mb: 0.8, "& .MuiInputBase-root": { fontSize: TYPE.secondary.fontSize, bgcolor: "#fafafa" } }}
      />
      <TextField
        fullWidth size="small" placeholder="详细说明（可选）"
        value={detail} onChange={(e) => setDetail(e.target.value)}
        multiline minRows={1} maxRows={3}
        sx={{ mb: 0.8, "& .MuiInputBase-root": { fontSize: TYPE.caption.fontSize, bgcolor: "#fafafa" } }}
      />
      <Box sx={{ display: "flex", gap: 2.2, justifyContent: "flex-end" }}>
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

/* ── Suggestion section ── */

function SuggestionSection({ sectionKey, label, items, expandedIds, onToggle, onDecide, onAdd, knowledgeMap }) {
  const [adding, setAdding] = useState(false);
  if ((!items || items.length === 0) && !adding) return null;

  const decidedCount = (items || []).filter((s) => s.decision).length;
  const total = (items || []).length;

  return (
    <Box sx={{ mt: 1, bgcolor: COLOR.white, borderTop: `0.5px solid ${COLOR.border}`, borderBottom: `0.5px solid ${COLOR.border}` }}>
      {/* Section header */}
      <Box sx={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 1.5, px: 2, py: 1.2 }}>
        <Box sx={{ minWidth: 0 }}>
          <Typography sx={{ fontSize: TYPE.action.fontSize, fontWeight: 500, color: COLOR.text1 }}>{label}</Typography>
          <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4, mt: 0.2 }}>{decidedCount}/{total} 已处理</Typography>
        </Box>
        <Box onClick={() => setAdding((prev) => !prev)}
          sx={{ fontSize: TYPE.caption.fontSize, color: adding ? COLOR.text4 : COLOR.primary, cursor: "pointer", whiteSpace: "nowrap", pt: 0.2, "&:active": { opacity: 0.6 } }}>
          {adding ? "取消" : "添加"}
        </Box>
      </Box>

      {adding && (
        <InlineAddForm
          onSubmit={(content, detail) => { onAdd?.(sectionKey, content, detail); setAdding(false); }}
          onCancel={() => setAdding(false)}
        />
      )}

      {(items || []).map((s) => (
        <DiagnosisCard
          key={s.id}
          suggestion={s}
          expanded={expandedIds instanceof Set ? expandedIds.has(s.id) : expandedIds === s.id}
          onToggle={() => onToggle(s.id)}
          onDecide={onDecide}
          knowledgeMap={knowledgeMap}
        />
      ))}
    </Box>
  );
}

/* ── Main ── */

export default function ReviewSubpage({
  record,
  suggestions = [],
  expandedIds,
  onToggle,
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

  // Group suggestions by section
  const grouped = {};
  SECTIONS.forEach((s) => { grouped[s.key] = []; });
  suggestions.forEach((s) => {
    if (grouped[s.section]) grouped[s.section].push(s);
  });

  const totalCount = suggestions.length;
  const decidedCount = suggestions.filter((s) => s.decision).length;

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%", bgcolor: COLOR.surfaceAlt }}>
      <SubpageHeader title="诊断审核" onBack={onBack} right={headerRight} />

      <Box sx={{ flex: 1, overflow: "auto", pb: hasSuggestions ? "88px" : 2 }}>
        {/* Record summary (render via children or default) */}
        {children}

        {/* Suggestion sections */}
        {hasSuggestions && (
          <Box sx={{ pb: 1 }}>
            {SECTIONS.map((sec) => (
              <SuggestionSection
                key={sec.key}
                sectionKey={sec.key}
                label={sec.label}
                items={grouped[sec.key]}
                expandedIds={expandedIds}
                onToggle={onToggle}
                onDecide={onDecide}
                onAdd={onAdd}
                knowledgeMap={knowledgeMap}
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
              <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4 }}>已处理</Typography>
              <Typography sx={{ fontSize: TYPE.body.fontSize, color: COLOR.text2 }}>{decidedCount}/{totalCount}</Typography>
            </Box>
            <Button
              variant="contained" onClick={onFinalize} disabled={finalizing}
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
    </Box>
  );
}
