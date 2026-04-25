import { create } from "zustand";
import { persist } from "zustand/middleware";

const EMPTY = {
  token: "",
  patientId: "",
  patientName: "",
  doctorId: "",
  doctorName: "",
};

export const usePatientStore = create(
  persist(
    (set) => ({
      ...EMPTY,
      // Atomic identity replace — use at login boundaries (QR absorption, /login).
      // Any field not provided is cleared, so stale identity from a prior session
      // never bleeds into the new one.
      loginWithIdentity: (next = {}) =>
        set({
          token: next.token || "",
          patientId: next.patientId || "",
          patientName: next.patientName || "",
          doctorId: next.doctorId || "",
          doctorName: next.doctorName || "",
        }),
      // Partial profile merge. Use only after login is established (e.g., when
      // /patient/me refresh returns canonical profile fields). Never touches token.
      mergeProfile: (partial = {}) =>
        set((s) => ({
          patientId: partial.patientId ?? s.patientId,
          patientName: partial.patientName ?? s.patientName,
          doctorId: partial.doctorId ?? s.doctorId,
          doctorName: partial.doctorName ?? s.doctorName,
        })),
      clearAuth: () => set(EMPTY),
    }),
    { name: "patient-portal-auth" }
  )
);

// One-shot migration from the legacy per-key localStorage scheme used by
// PatientPage before this store existed. Runs once on module load: if the new
// persisted store hasn't been written yet AND any of the old keys exist, hydrate
// the new store and delete the old keys. Idempotent across reloads.
const LEGACY_KEYS = {
  token:        "patient_portal_token",
  patientName:  "patient_portal_name",
  doctorId:     "patient_portal_doctor_id",
  doctorName:   "patient_portal_doctor_name",
  patientId:    "patient_portal_patient_id",
};

(function migrateLegacyAuth() {
  if (typeof localStorage === "undefined") return;
  if (localStorage.getItem("patient-portal-auth")) return; // new store wins
  const next = {};
  let any = false;
  for (const [field, legacyKey] of Object.entries(LEGACY_KEYS)) {
    const v = localStorage.getItem(legacyKey);
    if (v) { next[field] = v; any = true; }
  }
  if (!any) return;
  usePatientStore.getState().loginWithIdentity(next);
  for (const legacyKey of Object.values(LEGACY_KEYS)) {
    localStorage.removeItem(legacyKey);
  }
})();
