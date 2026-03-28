import { describe, it, expect, beforeEach } from "vitest";
import { useDoctorStore } from "./doctorStore";

describe("doctorStore", () => {
  beforeEach(() => {
    useDoctorStore.setState({
      doctorId: null,
      doctorName: null,
      accessToken: null,
    });
  });

  it("starts with null auth state", () => {
    const state = useDoctorStore.getState();
    expect(state.doctorId).toBeNull();
    expect(state.doctorName).toBeNull();
    expect(state.accessToken).toBeNull();
  });

  it("setAuth stores doctor credentials", () => {
    useDoctorStore.getState().setAuth(42, "Dr. Wang", "tok_abc123");
    const state = useDoctorStore.getState();
    expect(state.doctorId).toBe(42);
    expect(state.doctorName).toBe("Dr. Wang");
    expect(state.accessToken).toBe("tok_abc123");
  });

  it("clearAuth resets all fields to null", () => {
    useDoctorStore.getState().setAuth(42, "Dr. Wang", "tok_abc123");
    useDoctorStore.getState().clearAuth();
    const state = useDoctorStore.getState();
    expect(state.doctorId).toBeNull();
    expect(state.doctorName).toBeNull();
    expect(state.accessToken).toBeNull();
  });
});
