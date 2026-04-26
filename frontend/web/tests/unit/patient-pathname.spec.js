import { describe, it, expect } from "vitest";
import {
  detectSection,
  detectRecordDetail,
  detectTaskDetail,
  detectProfileSubpage,
} from "../../src/v2/pages/patient/pathname";

describe("detectSection", () => {
  it.each([
    ["/patient", "chat"],
    ["/patient/", "chat"],
    ["/patient/chat", "chat"],
    ["/patient/records", "records"],
    ["/patient/tasks", "tasks"],
    ["/patient/profile", "profile"],
    ["/patient/records/42", "records"],
    ["/patient/tasks/7", "tasks"],
    ["/patient/profile/about", "profile"],
    ["/patient/unknown", "chat"],
  ])("%s → %s", (path, expected) => {
    expect(detectSection(path)).toBe(expected);
  });
});

describe("detectRecordDetail", () => {
  it("returns id for /patient/records/42", () => {
    expect(detectRecordDetail("/patient/records/42")).toBe("42");
  });
  it("returns null for /patient/records/intake", () => {
    expect(detectRecordDetail("/patient/records/intake")).toBeNull();
  });
  it("returns null for /patient/records", () => {
    expect(detectRecordDetail("/patient/records")).toBeNull();
  });
  it("returns null for non-records paths", () => {
    expect(detectRecordDetail("/patient/tasks/42")).toBeNull();
  });
});

describe("detectTaskDetail", () => {
  it("returns id for /patient/tasks/7", () => {
    expect(detectTaskDetail("/patient/tasks/7")).toBe("7");
  });
  it("returns null for /patient/tasks", () => {
    expect(detectTaskDetail("/patient/tasks")).toBeNull();
  });
});

describe("detectProfileSubpage", () => {
  it.each([
    ["/patient/profile/about", "about"],
    ["/patient/profile/privacy", "privacy"],
  ])("%s → %s", (path, expected) => {
    expect(detectProfileSubpage(path)).toBe(expected);
  });
  it("returns null for /patient/profile", () => {
    expect(detectProfileSubpage("/patient/profile")).toBeNull();
  });
  it("returns null for unknown subpage", () => {
    expect(detectProfileSubpage("/patient/profile/xyz")).toBeNull();
  });
});
