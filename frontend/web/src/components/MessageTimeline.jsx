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

export default function MessageTimeline({ messages, maxHeight, defaultExpanded = false }) {
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
          <TimelineNode key={m.id || i} m={m} isLast={i === visibleMessages.length - 1} />
        ))}
      </Box>
    </Box>
  );
}
