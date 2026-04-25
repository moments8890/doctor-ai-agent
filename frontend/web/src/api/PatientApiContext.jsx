import { createContext, useContext } from "react";
import {
  getPatientMe,
  getPatientRecords,
  getPatientRecordDetail,
  getPatientTasks,
  getPatientTaskDetail,
  completePatientTask,
  uncompletePatientTask,
  getPatientChatMessages,
  sendPatientChat,
  confirmPatientChatDraft,
  sendPatientMessage,
  interviewStart,
  interviewTurn,
  interviewConfirm,
  interviewCancel,
} from "../api";

export const PatientApiContext = createContext(null);

const realApi = {
  getPatientMe,
  getPatientRecords,
  getPatientRecordDetail,
  getPatientTasks,
  getPatientTaskDetail,
  completePatientTask,
  uncompletePatientTask,
  getPatientChatMessages,
  sendPatientChat,
  confirmPatientChatDraft,
  sendPatientMessage,
  interviewStart,
  interviewTurn,
  interviewConfirm,
  interviewCancel,
};

// Stable reference — avoids new-object-per-render when no value prop is passed
const DEFAULT_API_VALUE = { ...realApi, isMock: false };

/**
 * Provides patient API functions to descendants. Defaults to real api.js.
 * In mock mode, PatientMockApiProvider overrides with mock functions.
 */
export function PatientApiProvider({ children, value }) {
  return (
    <PatientApiContext.Provider value={value ?? DEFAULT_API_VALUE}>
      {children}
    </PatientApiContext.Provider>
  );
}

/**
 * Hook to access patient API functions. Must be called inside PatientApiProvider.
 * Returns all patient api exports + `isMock` boolean.
 */
export function usePatientApi() {
  const ctx = useContext(PatientApiContext);
  if (!ctx) throw new Error("usePatientApi must be used within a PatientApiProvider");
  return ctx;
}
