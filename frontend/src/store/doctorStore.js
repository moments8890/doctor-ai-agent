import { create } from "zustand";
import { persist } from "zustand/middleware";

export const useDoctorStore = create(
  persist(
    (set) => ({
      doctorId: null,
      doctorName: null,
      accessToken: null,
      setAuth: (doctorId, name, token) => set({ doctorId, doctorName: name, accessToken: token }),
      clearAuth: () => set({ doctorId: null, doctorName: null, accessToken: null }),
    }),
    { name: "doctor-session" }
  )
);
