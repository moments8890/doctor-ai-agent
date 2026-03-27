import { createContext, useContext } from "react";
import * as realApi from "../api";

const ApiContext = createContext(null);

// Stable reference — avoids new-object-per-render when no value prop is passed
const DEFAULT_API_VALUE = { ...realApi, isMock: false };

/**
 * Provides API functions to descendants. Defaults to real api.js.
 * In mock mode, MockApiProvider overrides with mockApi functions.
 */
export function ApiProvider({ children, value }) {
  return <ApiContext.Provider value={value ?? DEFAULT_API_VALUE}>{children}</ApiContext.Provider>;
}

/**
 * Hook to access API functions. Must be called inside ApiProvider.
 * Returns all api.js exports + `isMock` boolean.
 */
export function useApi() {
  const ctx = useContext(ApiContext);
  if (!ctx) throw new Error("useApi must be used within an ApiProvider");
  return ctx;
}
