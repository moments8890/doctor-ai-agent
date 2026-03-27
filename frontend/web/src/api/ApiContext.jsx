import { createContext, useContext } from "react";
import * as realApi from "../api";

const ApiContext = createContext(null);

/**
 * Provides API functions to descendants. Defaults to real api.js.
 * In mock mode, MockApiProvider overrides with mockApi functions.
 */
export function ApiProvider({ children, value }) {
  const api = value || { ...realApi, isMock: false };
  return <ApiContext.Provider value={api}>{children}</ApiContext.Provider>;
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
