/**
 * patientQueries — React Query hooks for the patient portal.
 *
 * Mirrors lib/doctorQueries.js shape. Token comes from usePatientStore (not
 * threaded through props/args). ChatTab does NOT live here — its bespoke
 * polling (10s visible / 60s hidden) + optimistic dedupe is preserved as-is.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { PK } from "./queryKeys";
import { usePatientApi } from "../api/PatientApiContext";
import { usePatientStore } from "../store/patientStore";

// ── Queries ──────────────────────────────────────────────────────────────

export function usePatientMe() {
  const api = usePatientApi();
  const token = usePatientStore((s) => s.token);
  return useQuery({
    queryKey: PK.patientMe(),
    queryFn:  () => api.getPatientMe(token),
    enabled:  !!token,
    staleTime: 5 * 60_000,
  });
}

export function usePatientRecords() {
  const api = usePatientApi();
  const token = usePatientStore((s) => s.token);
  return useQuery({
    queryKey: PK.patientRecords(),
    queryFn:  () => api.getPatientRecords(token),
    enabled:  !!token,
    staleTime: 30_000,
  });
}

export function usePatientRecordDetail(id) {
  const api = usePatientApi();
  const token = usePatientStore((s) => s.token);
  return useQuery({
    queryKey: PK.patientRecordDetail(id),
    queryFn:  () => api.getPatientRecordDetail(token, id),
    enabled:  !!token && !!id,
    staleTime: 60_000,
  });
}

export function usePatientTasks() {
  const api = usePatientApi();
  const token = usePatientStore((s) => s.token);
  return useQuery({
    queryKey: PK.patientTasks(),
    queryFn:  () => api.getPatientTasks(token),
    enabled:  !!token,
    staleTime: 30_000,
  });
}

export function usePatientTaskDetail(id) {
  const api = usePatientApi();
  const qc = useQueryClient();
  const token = usePatientStore((s) => s.token);
  return useQuery({
    queryKey: PK.patientTaskDetail(id),
    queryFn:  () => api.getPatientTaskDetail(token, id),
    enabled:  !!token && !!id,
    staleTime: 60_000,
    // Use the matching task from the cached list as initialData when present —
    // gives instant render while the per-id endpoint refreshes in the background.
    initialData: () => {
      const list = qc.getQueryData(PK.patientTasks());
      return list?.find((t) => String(t.id) === String(id));
    },
  });
}

// ── Mutations ────────────────────────────────────────────────────────────

export function useCompletePatientTask() {
  const api = usePatientApi();
  const qc = useQueryClient();
  const token = usePatientStore((s) => s.token);
  return useMutation({
    mutationFn: (taskId) => api.completePatientTask(token, taskId),
    onSuccess: (_data, taskId) => {
      qc.invalidateQueries({ queryKey: PK.patientTasks() });
      qc.invalidateQueries({ queryKey: PK.patientTaskDetail(taskId) });
    },
  });
}

export function useUncompletePatientTask() {
  const api = usePatientApi();
  const qc = useQueryClient();
  const token = usePatientStore((s) => s.token);
  return useMutation({
    mutationFn: (taskId) => api.uncompletePatientTask(token, taskId),
    onSuccess: (_data, taskId) => {
      qc.invalidateQueries({ queryKey: PK.patientTasks() });
      qc.invalidateQueries({ queryKey: PK.patientTaskDetail(taskId) });
    },
  });
}
