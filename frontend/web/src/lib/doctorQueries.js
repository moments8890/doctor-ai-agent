import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { QK } from "./queryKeys";
import { useApi } from "../api/ApiContext";
import { useDoctorStore } from "../store/doctorStore";

// staleTime constants
const STALE = {
  profile:    60 * 60_000,  // 1 hr
  knowledge:  30 * 60_000,  // 30 min
  patients:    3 * 60_000,  // 3 min
  aiAttention: 5 * 60_000,  // 5 min
  aiActivity:  2 * 60_000,  // 2 min
  counts:        30_000,    // 30 sec — badge-critical
  queue:         30_000,    // 30 sec
  tasks:         60_000,    // 1 min
  record:        60_000,    // 1 min
};

// Auto-refresh interval (ms) for active data — keeps lists fresh while doctor is viewing
const POLL = 10_000; // 10 sec

export function useDoctorProfile() {
  const { doctorId } = useDoctorStore();
  const api = useApi();
  return useQuery({
    queryKey: QK.doctorProfile(doctorId),
    queryFn:  () => api.getDoctorProfile(doctorId),
    staleTime: STALE.profile,
    enabled:  !!doctorId,
  });
}

export function usePendingTasks() {
  const { doctorId } = useDoctorStore();
  const api = useApi();
  return useQuery({
    queryKey: QK.tasks(doctorId, "pending"),
    queryFn:  () => api.getTasks(doctorId, "pending"),
    staleTime: STALE.tasks,
    refetchInterval: POLL,
    enabled:  !!doctorId,
  });
}

export function useCompletedTasks() {
  const { doctorId } = useDoctorStore();
  const api = useApi();
  return useQuery({
    queryKey: QK.tasks(doctorId, "completed"),
    queryFn:  () => api.getTasks(doctorId, "completed"),
    staleTime: STALE.tasks,
    refetchInterval: POLL,
    enabled:  !!doctorId,
  });
}

export function useDraftSummary() {
  const { doctorId } = useDoctorStore();
  const api = useApi();
  return useQuery({
    queryKey: QK.draftSummary(doctorId),
    queryFn:  () => api.fetchDraftSummary(doctorId),
    staleTime: STALE.counts,
    refetchInterval: POLL,
    enabled:  !!doctorId,
  });
}

export function useReviewQueue() {
  const { doctorId } = useDoctorStore();
  const api = useApi();
  return useQuery({
    queryKey: QK.reviewQueue(doctorId),
    queryFn:  () => api.getReviewQueue(doctorId),
    staleTime: STALE.queue,
    refetchInterval: POLL,
    enabled:  !!doctorId,
  });
}

export function useDrafts(opts = {}) {
  const { doctorId } = useDoctorStore();
  const api = useApi();
  return useQuery({
    queryKey: QK.drafts(doctorId),
    queryFn:  () => api.fetchDrafts(doctorId, opts),
    staleTime: STALE.queue,
    refetchInterval: POLL,
    enabled:  !!doctorId,
  });
}

export function useKnowledgeItems() {
  const { doctorId } = useDoctorStore();
  const api = useApi();
  return useQuery({
    queryKey: QK.knowledge(doctorId),
    queryFn:  () => api.getKnowledgeItems(doctorId),
    staleTime: STALE.knowledge,
    enabled:  !!doctorId,
  });
}

export function usePatients() {
  const { doctorId } = useDoctorStore();
  const api = useApi();
  return useQuery({
    queryKey: QK.patients(doctorId),
    queryFn:  () => api.getPatients(doctorId, {}, 200),
    staleTime: STALE.patients,
    refetchInterval: POLL,
    enabled:  !!doctorId,
  });
}

export function useAIActivity(limit = 3) {
  const { doctorId } = useDoctorStore();
  const api = useApi();
  return useQuery({
    queryKey: QK.aiActivity(doctorId, limit),
    queryFn:  () => api.fetchAIActivity(doctorId, limit),
    staleTime: STALE.aiActivity,
    refetchInterval: POLL,
    enabled:  !!doctorId,
  });
}

export function useAIAttention() {
  const { doctorId } = useDoctorStore();
  const api = useApi();
  return useQuery({
    queryKey: QK.aiAttention(doctorId),
    queryFn:  () => api.fetchAIAttention(doctorId),
    staleTime: STALE.aiAttention,
    refetchInterval: POLL,
    enabled:  !!doctorId,
  });
}

export function useTaskRecord(recordId) {
  const { doctorId } = useDoctorStore();
  const api = useApi();
  return useQuery({
    queryKey: QK.taskRecord(recordId, doctorId),
    queryFn:  () => api.getTaskRecord(recordId, doctorId),
    staleTime: STALE.record,
    enabled:  !!recordId && !!doctorId,
  });
}

export function usePersona() {
  const { doctorId } = useDoctorStore();
  const api = useApi();
  return useQuery({
    queryKey: QK.persona(doctorId),
    queryFn:  () => api.getPersona(doctorId),
    staleTime: 5 * 60_000,
    enabled:  !!doctorId,
  });
}

export function usePersonaPending() {
  const { doctorId } = useDoctorStore();
  const api = useApi();
  return useQuery({
    queryKey: QK.personaPending(doctorId),
    queryFn:  () => api.getPersonaPending(doctorId),
    enabled:  !!doctorId,
    staleTime: 30_000,
    refetchInterval: POLL,
  });
}

export function useTodaySummary() {
  const { doctorId } = useDoctorStore();
  const api = useApi();
  return useQuery({
    queryKey: QK.todaySummary(doctorId),
    queryFn:  () => api.getTodaySummary(doctorId),
    staleTime: 30 * 60_000,
    enabled:  !!doctorId,
    retry: 1,
  });
}

export function useAcceptPendingItem() {
  const { doctorId } = useDoctorStore();
  const api = useApi();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (itemId) => api.acceptPendingItem(doctorId, itemId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QK.personaPending(doctorId) });
      queryClient.invalidateQueries({ queryKey: QK.persona(doctorId) });
    },
  });
}

export function useRejectPendingItem() {
  const { doctorId } = useDoctorStore();
  const api = useApi();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (itemId) => api.rejectPendingItem(doctorId, itemId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QK.personaPending(doctorId) });
    },
  });
}

export function useKbPending() {
  const { doctorId } = useDoctorStore();
  const api = useApi();
  return useQuery({
    queryKey: QK.kbPending(doctorId),
    queryFn:  () => api.getKbPending(doctorId),
    enabled:  !!doctorId,
    staleTime: 30_000,
    refetchInterval: POLL,
  });
}

export function useKbHallucinations(days = 7) {
  const { doctorId } = useDoctorStore();
  const api = useApi();
  return useQuery({
    queryKey: QK.kbHallucinations(doctorId, days),
    queryFn:  () => api.getKbHallucinations(doctorId, days),
    enabled:  !!doctorId,
    staleTime: 60_000,
  });
}

export function useAcceptKbPending() {
  const { doctorId } = useDoctorStore();
  const api = useApi();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (itemId) => api.acceptKbPending(doctorId, itemId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QK.kbPending(doctorId) });
      queryClient.invalidateQueries({ queryKey: QK.knowledge(doctorId) });
    },
  });
}

export function useRejectKbPending() {
  const { doctorId } = useDoctorStore();
  const api = useApi();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (itemId) => api.rejectKbPending(doctorId, itemId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QK.kbPending(doctorId) });
    },
  });
}

export function useSuggestions(recordId) {
  const { doctorId } = useDoctorStore();
  const api = useApi();
  return useQuery({
    queryKey: QK.suggestions(recordId, doctorId),
    queryFn:  () => api.getSuggestions(recordId, doctorId),
    staleTime: 0,
    refetchInterval: (query) => {
      const data = query.state.data;
      const items = Array.isArray(data) ? data : (data?.suggestions || data?.items || []);
      return items.length === 0 ? 3000 : false;
    },
    enabled:  !!recordId && !!doctorId,
  });
}
