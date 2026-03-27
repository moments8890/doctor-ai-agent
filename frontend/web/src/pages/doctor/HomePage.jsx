/** @route /doctor */
import { useEffect, useState } from "react";
import { Box } from "@mui/material";
import { useApi } from "../../api/ApiContext";
import { useAppNavigate } from "../../hooks/useAppNavigate";
import HomeSubpage from "./subpages/HomeSubpage";

export default function HomePage({ doctorId, onNavigateToChat }) {
  const navigate = useAppNavigate();
  const { getBriefing } = useApi();
  const [data, setData] = useState(null);

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
    else if (target === "chat") navigate("/doctor/chat");
  }

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%", bgcolor: "#ededed" }}>
      <HomeSubpage
        stats={stats}
        overdueTasks={overdueTasks}
        onNavigate={handleNavigate}
        onAskAI={() => navigate("/doctor/chat")}
      />
    </Box>
  );
}
