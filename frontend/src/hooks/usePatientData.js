import { useCallback, useEffect, useState } from "react";
import { getPatients } from "../api";

export function usePatientData(doctorId) {
  const [patients, setPatients] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const reload = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const result = await getPatients(doctorId);
      setPatients(result.items || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [doctorId]);

  useEffect(() => {
    reload();
  }, [reload]);

  return { patients, loading, error, reload };
}
