/**
 * TasksTab — patient task list (pending + completed).
 *
 * Extracted from PatientPage.jsx. Splits tasks into pending
 * (status "pending" | "notified") and completed, renders with
 * TaskChecklist, and shows an empty-state when there are none.
 */

import { useEffect, useState, useCallback } from "react";
import { Box, CircularProgress, Typography } from "@mui/material";
import { usePatientApi } from "../../api/PatientApiContext";
import TaskChecklist from "../../components/TaskChecklist";
import SectionLabel from "../../components/SectionLabel";
import { ICON } from "../../theme";

export default function TasksTab({ token }) {
  const { getPatientTasks, completePatientTask } = usePatientApi();
  const [tasks, setTasks] = useState([]);
  const [loading, setLoading] = useState(true);

  const loadTasks = useCallback(() => {
    setLoading(true);
    getPatientTasks(token)
      .then(data => setTasks(Array.isArray(data) ? data : []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [token, getPatientTasks]);

  useEffect(() => { loadTasks(); }, [loadTasks]);

  async function handleComplete(taskId) {
    try {
      await completePatientTask(token, taskId);
      setTasks(prev => prev.map(t => t.id === taskId ? { ...t, status: "completed" } : t));
    } catch {}
  }

  if (loading) {
    return <Box display="flex" justifyContent="center" py={6}><CircularProgress size={20} /></Box>;
  }

  if (tasks.length === 0) {
    return (
      <Box sx={{ flex: 1, overflowY: "auto", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
        <Typography sx={{ fontSize: ICON.display, color: "#ccc", mb: 1 }}>📋</Typography>
        <Typography color="text.disabled" sx={{ fontWeight: 500 }}>暂无任务</Typography>
        <Typography variant="caption" color="text.disabled" sx={{ mt: 0.5 }}>
          医生安排的复查、用药提醒将显示在这里
        </Typography>
      </Box>
    );
  }

  const pending = tasks.filter(t => t.status === "pending" || t.status === "notified");
  const completed = tasks.filter(t => t.status === "completed");

  return (
    <Box sx={{ flex: 1, overflowY: "auto" }}>
      {pending.length > 0 && (
        <>
          <SectionLabel>待完成 · {pending.length}</SectionLabel>
          <TaskChecklist tasks={pending} onComplete={handleComplete} />
        </>
      )}
      {completed.length > 0 && (
        <>
          <SectionLabel sx={{ mt: 1 }}>已完成 · {completed.length}</SectionLabel>
          <TaskChecklist tasks={completed} />
        </>
      )}
    </Box>
  );
}
