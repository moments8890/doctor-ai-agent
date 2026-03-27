import { PatientApiContext } from "./PatientApiContext";
import * as mockApi from "./patientMockApi";

const mockValue = { ...mockApi, isMock: true };

/**
 * Wraps children in PatientApiContext.Provider with mock API functions.
 * Patient auth state stays intact — only API calls are replaced with mocks.
 */
export function PatientMockApiProvider({ children }) {
  return (
    <PatientApiContext.Provider value={mockValue}>
      {children}
    </PatientApiContext.Provider>
  );
}
