import { useCallback, useEffect, useState } from "react";
import { createLabel, deleteLabelById, getLabels } from "../api";

export function useLabelData(doctorId) {
  const [labels, setLabels] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const reload = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const result = await getLabels(doctorId);
      setLabels(result.items || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [doctorId]);

  useEffect(() => {
    reload();
  }, [reload]);

  const createLabelFn = useCallback(
    async (name, color) => {
      await createLabel({ doctorId, name, color });
      await reload();
    },
    [doctorId, reload]
  );

  const deleteLabelFn = useCallback(
    async (labelId) => {
      await deleteLabelById({ doctorId, labelId });
      await reload();
    },
    [doctorId, reload]
  );

  return { labels, loading, error, reload, createLabel: createLabelFn, deleteLabel: deleteLabelFn };
}
