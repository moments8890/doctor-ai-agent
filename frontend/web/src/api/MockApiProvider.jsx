import { useEffect } from "react";
import { ApiProvider } from "./ApiContext";
import { useDoctorStore } from "../store/doctorStore";
import * as mockApi from "./mockApi";

const mockValue = { ...mockApi, isMock: true };

/**
 * Wraps children in ApiProvider with mock API functions.
 * Sets mock auth so debug pages show "测试医生" instead of real login name.
 * Sets browser tab title to "[debug] ..." so it's obvious which mode you're in.
 */
export function MockApiProvider({ children }) {
  const { setAuth } = useDoctorStore();

  useEffect(() => {
    document.title = "[debug] 鲸鱼随行";
    setAuth({ doctorId: "mock_doctor", doctorName: "测试医生", accessToken: "mock-token" });
    return () => { document.title = "鲸鱼随行"; };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  return <ApiProvider value={mockValue}>{children}</ApiProvider>;
}
