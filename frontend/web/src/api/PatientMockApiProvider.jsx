import { useEffect } from "react";
import { PatientApiContext } from "./PatientApiContext";
import * as mockApi from "./patientMockApi";

const mockValue = { ...mockApi, isMock: true };

/**
 * Wraps children in PatientApiContext.Provider with mock API functions.
 * Sets browser tab title to "[debug] ..." so it's obvious which mode you're in.
 */
export function PatientMockApiProvider({ children }) {
  useEffect(() => {
    document.title = "[debug] 鲸鱼随行";
    return () => { document.title = "鲸鱼随行"; };
  }, []);

  return (
    <PatientApiContext.Provider value={mockValue}>
      {children}
    </PatientApiContext.Provider>
  );
}
