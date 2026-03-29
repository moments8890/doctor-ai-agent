/**
 * MessageTimeline — vertical timeline for patient/AI/doctor messages.
 *
 * Green left border with colored dots per source:
 *  - blue (#5b9bd5) = patient
 *  - gray (#999) = AI auto-reply
 *  - green (#07C160) = doctor / AI draft
 *
 * Smart collapse: shows latest 3 messages by default.
 * If more exist, shows "查看更早 N 条" to expand.
 *
 * Props:
 *  - messages: [{ id, source, content, created_at }]
 *  - maxHeight: number (optional, for scrollable container)
 *  - defaultExpanded: boolean (default false)
 */
import { useState } from "react";
import { Box, Typography } from "@mui/material";
import { TYPE, COLOR } from "../theme";

const SOURCE_CONFIG = {
  patient: { label: "患者", color: "#5b9bd5" },
  ai:      { label: "AI", color: "#999" },
  doctor:  { label: "医生", color: COLOR.primary },
};

function formatTime(dateStr) {
  if (!dateStr) return "";
  try {
    return new Date(dateStr).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
  } catch { return ""; }
}

function TimelineNode({ m, isLast }) {
  const cfg = SOURCE_CONFIG[m.source] || SOURCE_CONFIG.ai;
  const isAiDisclosure = (m.content || "").includes("AI辅助生成");

  return (
    <Box sx={{ position: "relative", pb: isLast ? 0.5 : 1.5 }}>
      <Box sx={{
        position: "absolute", left: -20, top: 3,
        width: 8, height: 8, borderRadius: "50%",
        bgcolor: cfg.color,
      }} />
      <Typography sx={{ fontSize: TYPE.micro.fontSize, color: cfg.color, fontWeight: 600 }}>
        {cfg.label}
        <Box component="span" sx={{ color: COLOR.text4, fontWeight: 400, ml: 0.5 }}>
          {formatTime(m.created_at)}
        </Box>
      </Typography>
      <Typography sx={{
        fontSize: TYPE.secondary.fontSize,
        color: isAiDisclosure ? COLOR.text4 : (m.source === "ai" ? COLOR.text3 : COLOR.text1),
        fontStyle: isAiDisclosure ? "italic" : "normal",
        lineHeight: 1.6, mt: 0.2,
        whiteSpace: "pre-wrap", wordBreak: "break-word",
      }}>
        {m.content}
      </Typography>
    </Box>
  );
}

/**
 * Props:
 *  - messages: [{ id, source, content, created_at }]
 *  - draft: { text, rule_cited, onEdit, onSend } (optional — renders as last timeline node)
 *  - maxHeight, defaultExpanded
 */
export default function MessageTimeline({ messages, draft, maxHeight, defaultExpanded = false }) {
  const [showAll, setShowAll] = useState(defaultExpanded);

  if (!messages || messages.length === 0) return null;

  const VISIBLE_COUNT = 3;
  const hasMore = messages.length > VISIBLE_COUNT;
  const hiddenCount = messages.length - VISIBLE_COUNT;
  const visibleMessages = showAll || !hasMore ? messages : messages.slice(-VISIBLE_COUNT);

  return (
    <Box sx={{ maxHeight, overflowY: maxHeight ? "auto" : undefined }}>
      <Box sx={{ borderLeft: `2px solid ${COLOR.primary}`, ml: 0.5, pl: 1.5 }}>
        {/* Expand earlier messages */}
        {hasMore && !showAll && (
          <Box
            onClick={() => setShowAll(true)}
            sx={{
              position: "relative", pb: 1.2,
              cursor: "pointer", "&:active": { opacity: 0.6 },
            }}
          >
            <Box sx={{
              position: "absolute", left: -20, top: 3,
              width: 8, height: 8, borderRadius: "50%",
              border: `2px solid ${COLOR.text4}`, bgcolor: "transparent",
            }} />
            <Typography sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.primary, fontWeight: 500 }}>
              查看更早 {hiddenCount} 条消息 ▾
            </Typography>
          </Box>
        )}

        {/* Collapse link */}
        {hasMore && showAll && (
          <Box
            onClick={() => setShowAll(false)}
            sx={{
              position: "relative", pb: 1.2,
              cursor: "pointer", "&:active": { opacity: 0.6 },
            }}
          >
            <Typography sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.text4 }}>
              收起更早消息 ▴
            </Typography>
          </Box>
        )}

        {/* Message nodes */}
        {visibleMessages.map((m, i) => (
          <TimelineNode key={m.id || i} m={m} isLast={!draft && i === visibleMessages.length - 1} />
        ))}

        {/* AI draft node — green outline dot */}
        {draft && (
          <Box sx={{ position: "relative", pb: 0.5 }}>
            <Box sx={{
              position: "absolute", left: -20, top: 3,
              width: 8, height: 8, borderRadius: "50%",
              border: `2px solid ${COLOR.primary}`, bgcolor: "#fff",
            }} />
            <Typography sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.primary, fontWeight: 600 }}>
              AI起草回复 · 待发送
            </Typography>
            <Typography sx={{
              fontSize: TYPE.secondary.fontSize, color: COLOR.text1,
              lineHeight: 1.6, mt: 0.3, pl: 1,
            }}>
              {draft.text}
            </Typography>
            {draft.rule_cited && (
              <Box sx={{
                display: "inline-block", mt: 0.5, ml: 1, px: 1, py: 0.2,
                bgcolor: "#e8f5e9", borderRadius: "4px",
                fontSize: TYPE.micro.fontSize, color: COLOR.primary, fontWeight: 500,
              }}>
                引用: {draft.rule_cited}
              </Box>
            )}
            <Box sx={{ display: "flex", justifyContent: "flex-end", gap: 2, mt: 0.5 }}>
              {draft.onEdit && (
                <Typography onClick={draft.onEdit} sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text4, cursor: "pointer", "&:active": { opacity: 0.5 } }}>
                  修改
                </Typography>
              )}
              {draft.onSend && (
                <Typography onClick={draft.onSend} sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.primary, cursor: "pointer", "&:active": { opacity: 0.5 } }}>
                  发送 ›
                </Typography>
              )}
            </Box>
          </Box>
        )}
      </Box>
    </Box>
  );
}
