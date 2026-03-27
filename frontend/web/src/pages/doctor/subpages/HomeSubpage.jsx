/**
 * HomeSubpage — shared presentational home screen for doctor app.
 *
 * Displays stat cards, overdue tasks, onboarding hint, and AskAIBar.
 * Used by both real HomePage (API data) and MockPages (static data).
 *
 * @see /debug/doctor-pages → 首页
 */
import { Box, Typography } from "@mui/material";
import { TYPE, COLOR } from "../../../theme";
import PageSkeleton from "../../../components/PageSkeleton";
import AskAIBar from "../../../components/AskAIBar";

const STAT_CARDS = [
  { key: "today_patients", label: "今日患者", color: COLOR.primary, target: "patients" },
  { key: "pending_tasks", label: "待办任务", color: COLOR.primary, target: "tasks" },
];

export default function HomeSubpage({
  stats = {},
  overdueTasks = [],
  onNavigate,
  onAskAI,
  title = "首页",
}) {
  const content = (
    <Box sx={{ flex: 1, display: "flex", flexDirection: "column" }}>
      <Box sx={{ flex: 1, overflowY: "auto", p: 1.5 }}>
        {/* Stat cards — 2-column grid */}
        <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 1, mb: 1 }}>
          {STAT_CARDS.map((card) => (
            <Box key={card.key}
              onClick={() => onNavigate?.(card.target)}
              sx={{
                bgcolor: COLOR.white, borderRadius: 1, p: 1.5, cursor: "pointer",
                "&:active": { bgcolor: COLOR.surface },
              }}>
              <Typography sx={{
                fontSize: 24, fontWeight: 700, color: card.color,
                fontFamily: '"DM Sans", sans-serif', fontVariantNumeric: "tabular-nums",
              }}>
                {stats[card.key] ?? 0}
              </Typography>
              <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4, mt: 0.2 }}>
                {card.label}
              </Typography>
            </Box>
          ))}
        </Box>

        {/* Completed count */}
        <Box sx={{ bgcolor: COLOR.white, borderRadius: 1, p: 1.5, mb: 1 }}>
          <Typography sx={{ fontSize: 24, fontWeight: 700, color: COLOR.text4,
            fontFamily: '"DM Sans", sans-serif', fontVariantNumeric: "tabular-nums" }}>
            {stats.completed_tasks ?? stats.completed_today ?? 0}
          </Typography>
          <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4 }}>已完成</Typography>
        </Box>

        {/* Overdue tasks */}
        {overdueTasks.length > 0 && (
          <Box sx={{ bgcolor: COLOR.white, borderRadius: 1, p: 1.5, mb: 1 }}>
            <Box sx={{ display: "flex", justifyContent: "space-between", mb: 1 }}>
              <Typography sx={{ fontWeight: 600, fontSize: TYPE.heading.fontSize }}>逾期任务</Typography>
              <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.danger }}>{overdueTasks.length}项</Typography>
            </Box>
            {overdueTasks.map((t) => (
              <Box key={t.id} onClick={() => onNavigate?.("tasks")}
                sx={{
                  display: "flex", justifyContent: "space-between", py: 0.8,
                  borderTop: `0.5px solid ${COLOR.borderLight}`, cursor: "pointer",
                }}>
                <Typography sx={{ fontSize: TYPE.secondary.fontSize }}>
                  {t.patient_name} {t.title}
                </Typography>
                <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.danger }}>
                  {t.due || t.context}
                </Typography>
              </Box>
            ))}
          </Box>
        )}

        {/* Onboarding hint — shown when all stats are zero */}
        {STAT_CARDS.every((c) => !(stats[c.key])) && (
          <Box sx={{ bgcolor: COLOR.white, borderRadius: 1, p: 2 }}>
            <Typography sx={{ fontSize: TYPE.secondary.fontSize, fontWeight: 600, color: COLOR.text1, mb: 1 }}>
              欢迎使用鲸鱼随行！
            </Typography>
            {[
              "发送消息给 AI 助手创建第一条病历",
              "在患者页面添加患者",
              "在任务页面创建任务",
            ].map((hint, i) => (
              <Typography key={i} sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text3, lineHeight: 1.8 }}>
                {i + 1}. {hint}
              </Typography>
            ))}
          </Box>
        )}
      </Box>

      {/* Sticky AskAIBar — always above bottom nav */}
      <AskAIBar onClick={onAskAI} />
    </Box>
  );

  return <PageSkeleton title={title} isMobile listPane={content} />;
}
