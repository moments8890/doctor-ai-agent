import { describe, it, expect, beforeEach } from "vitest";

describe("usePatientStore", () => {
  beforeEach(() => {
    // Reset localStorage between tests so persist middleware is clean
    localStorage.clear();
  });

  it("loginWithIdentity replaces all identity fields atomically", async () => {
    const { usePatientStore } = await import("../../src/store/patientStore.js");
    usePatientStore.getState().loginWithIdentity({
      token: "tok-1", patientId: "p1", patientName: "Alice",
      doctorId: "d1", doctorName: "Dr A",
    });
    expect(usePatientStore.getState().token).toBe("tok-1");
    expect(usePatientStore.getState().patientName).toBe("Alice");

    // Second login with only some fields wipes the rest (atomic replace)
    usePatientStore.getState().loginWithIdentity({ token: "tok-2", doctorId: "d2" });
    const s = usePatientStore.getState();
    expect(s.token).toBe("tok-2");
    expect(s.patientId).toBe("");      // wiped
    expect(s.patientName).toBe("");    // wiped
    expect(s.doctorId).toBe("d2");
    expect(s.doctorName).toBe("");     // wiped
  });

  it("mergeProfile updates only provided fields and never touches token", async () => {
    const { usePatientStore } = await import("../../src/store/patientStore.js");
    usePatientStore.getState().loginWithIdentity({ token: "T", patientId: "p1", patientName: "A" });
    usePatientStore.getState().mergeProfile({ patientName: "Alice", doctorId: "dx" });
    const s = usePatientStore.getState();
    expect(s.token).toBe("T");          // untouched
    expect(s.patientId).toBe("p1");     // untouched (not provided)
    expect(s.patientName).toBe("Alice"); // updated
    expect(s.doctorId).toBe("dx");       // updated
  });

  it("clearAuth wipes everything", async () => {
    const { usePatientStore } = await import("../../src/store/patientStore.js");
    usePatientStore.getState().loginWithIdentity({ token: "T", patientId: "p1" });
    usePatientStore.getState().clearAuth();
    expect(usePatientStore.getState().token).toBe("");
    expect(usePatientStore.getState().patientId).toBe("");
  });
});
