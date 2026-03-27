/** @route /doctor */
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Box } from "@mui/material";
import useMediaQuery from "@mui/material/useMediaQuery";
import { useTheme } from "@mui/material/styles";
import { getBriefing } from "../../api";
import BottomSheet from "../../components/BottomSheet";
import ChatPage from "./ChatPage";
import HomeSubpage from "./subpages/HomeSubpage";

export default function HomePage({ doctorId, onNavigateToChat }) {
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

  // Map API response to HomeSubpage props
  const stats = {
    today_patients: data?.stats?.today_patients ?? 0,
    pending_tasks: data?.stats?.today_tasks ?? 0,
    completed_tasks: data?.stats?.completed_today ?? 0,
  };

  const overdueTasks = (data?.cards || [])
    .filter((c) => c.type === "urgent")
    .slice(0, 3)
    .map((c, i) => ({ id: c.id || i, title: c.title, context: c.context }));

  function handleNavigate(target) {
    if (target === "patients") navigate("/doctor/patients");
    else if (target === "tasks") navigate("/doctor/tasks");
    else if (target === "chat") setChatOpen(true);
  }

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%", bgcolor: "#ededed" }}>
      <HomeSubpage
        stats={stats}
        overdueTasks={overdueTasks}
        onNavigate={handleNavigate}
        onAskAI={() => setChatOpen(true)}
      />

      {/* Chat bottom sheet — mobile only */}
      {isMobile && (
        <BottomSheet open={chatOpen} onClose={() => setChatOpen(false)}>
          <ChatPage doctorId={doctorId} onMessageCountChange={() => {}} onBack={() => setChatOpen(false)} />
        </BottomSheet>
      )}
    </Box>
  );
}
