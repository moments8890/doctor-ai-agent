import { useEffect } from "react";
import { ApiProvider } from "./ApiContext";
import * as mockApi from "./mockApi";

const mockValue = { ...mockApi, isMock: true };

/**
 * Wraps children in ApiProvider with mock API functions.
 * Does NOT touch useDoctorStore — the real auth state stays intact.
 * Sets browser tab title to "[debug] ..." so it's obvious which mode you're in.
 */
export function MockApiProvider({ children }) {
  useEffect(() => {
    document.title = "[debug] 鲸鱼随行";
    return () => { document.title = "鲸鱼随行"; };
  }, []);

  return <ApiProvider value={mockValue}>{children}</ApiProvider>;
}
