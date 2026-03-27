import { ApiProvider } from "./ApiContext";
import * as mockApi from "./mockApi";

const mockValue = { ...mockApi, isMock: true };

/**
 * Wraps children in ApiProvider with mock API functions.
 * Does NOT touch useDoctorStore — the real auth state stays intact.
 * In dev: RequireAuth passes through (no auth needed).
 * In prod: user must be logged in first, their real identity stays.
 * Either way, API calls go to mockApi which returns MOCK_* data
 * regardless of the doctorId passed.
 */
export function MockApiProvider({ children }) {
  return <ApiProvider value={mockValue}>{children}</ApiProvider>;
}
