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
  { key: "pending_review", label: "待审核", color: "#F59E0B", bg: "#FFF7E6", nav: "/doctor/tasks" },
  { key: "today_patients", label: "今日患者", color: "#1B6EF3", bg: "#E8F0FE", nav: "/doctor/patients", badgeKey: "red_flags" },
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

        {/* Pending review items */}
        {data?.cards?.map((card, i) => {
          if (card.type !== "pending_review" || !card.items) return null;
          return (
            <Box key={i} sx={{ bgcolor: "#fff", borderRadius: "6px", mb: 1 }}>
              <Box sx={{ px: 1.5, pt: 1.2, pb: 0.5 }}>
                <Typography sx={{ fontSize: TYPE.secondary.fontSize, fontWeight: 600, color: "#333" }}>
                  {card.title}
                </Typography>
              </Box>
              {card.items.slice(0, 3).map((item, j) => (
                <Box key={j} onClick={() => navigate(`/doctor/tasks/review/${item.queue_id}`)}
                  sx={{ display: "flex", alignItems: "center", px: 1.5, py: 1,
                    borderTop: "0.5px solid #f0f0f0", cursor: "pointer",
                    "&:active": { bgcolor: "#f9f9f9" } }}>
                  <Box sx={{ flex: 1, minWidth: 0 }}>
                    <Typography sx={{ fontSize: TYPE.body.fontSize, color: "#333" }} noWrap>
                      {item.patient_name}
                      {item.chief_complaint && (
                        <Typography component="span" sx={{ fontSize: TYPE.caption.fontSize, color: "#999", ml: 0.5 }}>
                          {item.chief_complaint}
                        </Typography>
                      )}
                    </Typography>
                  </Box>
                  <Typography sx={{ fontSize: TYPE.caption.fontSize, color: "#07C160", flexShrink: 0 }}>
                    审核 ›
                  </Typography>
                </Box>
              ))}
            </Box>
          );
        })}

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
