import { useCallback, useEffect, useState } from "react";
import { getTasks, patchTask, postponeTask as apiPostpone, createTask as apiCreate } from "../api";

export function useTaskData(doctorId) {
  const [tasks, setTasks] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const reload = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const result = await getTasks(doctorId);
      setTasks(Array.isArray(result) ? result : []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [doctorId]);

  useEffect(() => {
    reload();
  }, [reload]);

  const completeTask = useCallback(
    async (taskId) => {
      await patchTask(taskId, doctorId, "completed");
      await reload();
    },
    [doctorId, reload]
  );

  const cancelTask = useCallback(
    async (taskId) => {
      await patchTask(taskId, doctorId, "cancelled");
      await reload();
    },
    [doctorId, reload]
  );

  const postponeTask = useCallback(
    async (taskId, dueAt) => {
      await apiPostpone(taskId, doctorId, dueAt);
      await reload();
    },
    [doctorId, reload]
  );

  const createTask = useCallback(
    async (fields) => {
      await apiCreate(doctorId, fields);
      await reload();
    },
    [doctorId, reload]
  );

  return { tasks, loading, error, reload, completeTask, cancelTask, postponeTask, createTask };
}
