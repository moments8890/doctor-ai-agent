/**
 * MessageTimeline — vertical timeline for patient/AI/doctor messages.
 *
 * Green left border with colored dots per source:
 *  - blue (#5b9bd5) = patient
 *  - gray (#999) = AI auto-reply
 *  - green (#07C160) = doctor / AI draft
 *
 * Props:
 *  - messages: [{ id, source, content, created_at }]
 *  - maxHeight: number (optional, for scrollable container)
 */
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

export default function MessageTimeline({ messages, maxHeight }) {
  if (!messages || messages.length === 0) return null;

  return (
    <Box sx={{ maxHeight, overflowY: maxHeight ? "auto" : undefined }}>
      <Box sx={{ borderLeft: `2px solid ${COLOR.primary}`, ml: 0.5, pl: 1.5 }}>
        {messages.map((m, i) => {
          const cfg = SOURCE_CONFIG[m.source] || SOURCE_CONFIG.ai;
          const isLast = i === messages.length - 1;
          const isAiDisclosure = (m.content || "").includes("AI辅助生成");

          return (
            <Box key={m.id || i} sx={{ position: "relative", pb: isLast ? 0.5 : 1.5 }}>
              {/* Dot on the timeline */}
              <Box sx={{
                position: "absolute", left: -20, top: 3,
                width: 8, height: 8, borderRadius: "50%",
                bgcolor: cfg.color,
              }} />

              {/* Label + time */}
              <Typography sx={{ fontSize: TYPE.micro.fontSize, color: cfg.color, fontWeight: 600 }}>
                {cfg.label}
                <Box component="span" sx={{ color: COLOR.text4, fontWeight: 400, ml: 0.5 }}>
                  {formatTime(m.created_at)}
                </Box>
              </Typography>

              {/* Content */}
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
        })}
      </Box>
    </Box>
  );
}
