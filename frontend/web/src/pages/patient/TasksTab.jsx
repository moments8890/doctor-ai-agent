/**
 * TasksTab — patient task list (pending + completed).
 *
 * Extracted from PatientPage.jsx. Splits tasks into pending
 * (status "pending") and completed, renders with
 * TaskChecklist, and shows an empty-state when there are none.
 */

import { useEffect, useState, useCallback } from "react";
import { Box, CircularProgress, Typography } from "@mui/material";
import { usePatientApi } from "../../api/PatientApiContext";
import TaskChecklist from "../../components/TaskChecklist";
import SectionLabel from "../../components/SectionLabel";
import EmptyState from "../../components/EmptyState";
import SectionLoading from "../../components/SectionLoading";
import FilterBar from "../../components/FilterBar";
import AssignmentOutlinedIcon from "@mui/icons-material/AssignmentOutlined";
import { PATIENT_TASK_FILTERS } from "./constants";

export default function TasksTab({ token }) {
  const { getPatientTasks, completePatientTask, uncompletePatientTask } = usePatientApi();
  const [tasks, setTasks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("all");

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

  async function handleUndo(taskId) {
    try {
      await uncompletePatientTask(token, taskId);
      setTasks(prev => prev.map(t => t.id === taskId ? { ...t, status: "pending", completed_at: null } : t));
    } catch {}
  }

  if (loading) {
    return <SectionLoading py={6} />;
  }

  const pending = tasks.filter(t => t.status === "pending");
  const completed = tasks.filter(t => t.status === "completed");

  const filtered = filter === "all" ? tasks
    : filter === "pending" ? tasks.filter(t => t.status === "pending")
    : tasks.filter(t => t.status === "completed");

  return (
    <Box sx={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
      <FilterBar items={PATIENT_TASK_FILTERS} active={filter} onChange={setFilter} />
      <Box sx={{ flex: 1, overflowY: "auto" }}>
        {filtered.length === 0 ? (
          <EmptyState icon={<AssignmentOutlinedIcon />} title="暂无任务" subtitle="医生安排的复查、用药提醒将显示在这里" />
        ) : filter === "all" ? (
          <>
            {pending.length > 0 && (
              <>
                <SectionLabel>待完成 · {pending.length}</SectionLabel>
                <TaskChecklist tasks={pending} onComplete={handleComplete} />
              </>
            )}
            {completed.length > 0 && (
              <>
                <SectionLabel sx={{ mt: 1 }}>已完成 · {completed.length}</SectionLabel>
                <TaskChecklist tasks={completed} onUndo={handleUndo} />
              </>
            )}
          </>
        ) : (
          <TaskChecklist
            tasks={filtered}
            onComplete={filter === "pending" ? handleComplete : undefined}
            onUndo={filter === "done" ? handleUndo : undefined}
          />
        )}
      </Box>
    </Box>
  );
}
