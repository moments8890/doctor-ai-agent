/** @route /doctor */
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Box, Typography } from "@mui/material";
import useMediaQuery from "@mui/material/useMediaQuery";
import { useTheme } from "@mui/material/styles";
import { getBriefing } from "../../api";
import { useDoctorStore } from "../../store/doctorStore";
import AskAIBar from "../../components/AskAIBar";
import BottomSheet from "../../components/BottomSheet";
import SubpageHeader from "./SubpageHeader";
import ChatSection from "./ChatSection";
import { TYPE } from "../../theme";

const STAT_CARDS = [
  { key: "today_patients", label: "今日患者", color: "#1B6EF3", bg: "#E8F0FE", nav: "/doctor/patients" },
  { key: "today_tasks", label: "待办任务", color: "#07C160", bg: "#E8F5E9", nav: "/doctor/tasks" },
  { key: "completed_today", label: "已完成", color: "#999", bg: "#F5F5F5", nav: "/doctor/tasks" },
];

export default function BriefingSection({ doctorId, onNavigateToChat }) {
  const doctorName = useDoctorStore((s) => s.doctorName);
  const navigate = useNavigate();
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down("sm"));
  const [data, setData] = useState(null);
  const [chatOpen, setChatOpen] = useState(false);

  useEffect(() => {
    if (!doctorId) return;
    let cancelled = false;
    const load = () =>
      getBriefing(doctorId)
        .then((d) => { if (!cancelled) setData(d); })
        .catch(() => {});
    load();
    const id = setInterval(load, 60000);
    return () => { cancelled = true; clearInterval(id); };
  }, [doctorId]);

  const stats = data?.stats || {};

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%", bgcolor: "#ededed" }}>
      {isMobile && <SubpageHeader title="首页" />}


      <Box sx={{ flex: 1, overflowY: "auto", p: 1.5 }}>
        {/* 4 stat cards */}
        <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 1, mb: 1.5 }}>
          {STAT_CARDS.map((card) => {
            const value = stats[card.key] ?? 0;
            const badge = card.badgeKey ? (stats[card.badgeKey] || 0) : 0;
            return (
              <Box key={card.key} onClick={() => navigate(card.nav)}
                sx={{ bgcolor: "#fff", borderRadius: "6px", p: 1.5, cursor: "pointer",
                  "&:active": { bgcolor: "#f9f9f9" } }}>
                <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
                  <Typography sx={{
                    fontSize: 24, fontWeight: 700, color: card.color,
                    fontFamily: '"DM Sans", sans-serif', fontVariantNumeric: "tabular-nums",
                  }}>
                    {value}
                  </Typography>
                  {badge > 0 && (
                    <Box sx={{ width: 8, height: 8, borderRadius: "50%", bgcolor: "#E8533F" }} />
                  )}
                </Box>
                <Typography sx={{ fontSize: TYPE.caption.fontSize, color: "#666", mt: 0.2 }}>
                  {card.label}
                </Typography>
              </Box>
            );
          })}
        </Box>

        {/* Onboarding hint — shown when all stats are zero */}
        {STAT_CARDS.every((c) => !(stats[c.key])) && (
          <Box sx={{ bgcolor: "#fff", borderRadius: "6px", p: 2, mb: 1.5 }}>
            <Typography sx={{ fontSize: TYPE.secondary.fontSize, fontWeight: 600, color: "#333", mb: 1 }}>
              欢迎使用鲸鱼随行！
            </Typography>
            {[
              "发送消息给 AI 助手创建第一条病历",
              "在患者页面添加患者",
              "在任务页面创建任务",
            ].map((hint, i) => (
              <Typography key={i} sx={{ fontSize: TYPE.caption.fontSize, color: "#666", lineHeight: 1.8 }}>
                {i + 1}. {hint}
              </Typography>
            ))}
          </Box>
        )}

        {/* Overdue tasks */}
        {data?.cards?.filter((c) => c.type === "urgent").length > 0 && (
          <Box sx={{ bgcolor: "#fff", borderRadius: "6px", mb: 1 }}>
            <Box sx={{ px: 1.5, pt: 1.2, pb: 0.5 }}>
              <Typography sx={{ fontSize: TYPE.secondary.fontSize, fontWeight: 600, color: "#E8533F" }}>
                逾期任务
              </Typography>
            </Box>
            {data.cards.filter((c) => c.type === "urgent").slice(0, 3).map((card, i) => (
              <Box key={i} onClick={() => navigate("/doctor/tasks")}
                sx={{ display: "flex", alignItems: "center", px: 1.5, py: 1,
                  borderTop: "0.5px solid #f0f0f0", cursor: "pointer",
                  "&:active": { bgcolor: "#f9f9f9" } }}>
                <Typography sx={{ fontSize: TYPE.body.fontSize, color: "#333", flex: 1 }} noWrap>
                  {card.title}
                </Typography>
                <Typography sx={{ fontSize: TYPE.caption.fontSize, color: "#999" }}>
                  {card.context}
                </Typography>
              </Box>
            ))}
          </Box>
        )}
      </Box>

      {isMobile && <AskAIBar onClick={() => setChatOpen(true)} />}

      {/* Chat bottom sheet — mobile only */}
      {isMobile && (
        <BottomSheet open={chatOpen} onClose={() => setChatOpen(false)}>
          <ChatSection doctorId={doctorId} onMessageCountChange={() => {}} onBack={() => setChatOpen(false)} />
        </BottomSheet>
      )}
    </Box>
  );
}
