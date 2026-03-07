import { create } from "zustand";
import { persist } from "zustand/middleware";

export const useDoctorStore = create(
  persist(
    (set) => ({
      doctorId: "web_doctor",
      setDoctorId: (id) => set({ doctorId: id }),
    }),
    { name: "doctor-session" }
  )
);
