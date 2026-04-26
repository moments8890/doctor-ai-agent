import { describe, test, expect } from "vitest";
import { decideColdStartSeed } from "../coldStartSeed";

describe("decideColdStartSeed", () => {
  test("noop when already at home", () => {
    expect(
      decideColdStartSeed({
        pathname: "/doctor/my-ai",
        search: "",
        hash: "",
        historyLength: 1,
      })
    ).toEqual({ kind: "noop" });
  });

  test("noop when not a doctor path", () => {
    expect(
      decideColdStartSeed({
        pathname: "/login",
        search: "",
        hash: "",
        historyLength: 1,
      })
    ).toEqual({ kind: "noop" });
  });

  test("noop when history already has multiple entries", () => {
    expect(
      decideColdStartSeed({
        pathname: "/doctor/review/abc",
        search: "",
        hash: "",
        historyLength: 5,
      })
    ).toEqual({ kind: "noop" });
  });

  test("seeds /doctor/my-ai for cold-start /doctor/review/:id", () => {
    expect(
      decideColdStartSeed({
        pathname: "/doctor/review/abc",
        search: "?x=1",
        hash: "",
        historyLength: 1,
      })
    ).toEqual({
      kind: "seed",
      homePath: "/doctor/my-ai",
      target: "/doctor/review/abc?x=1",
    });
  });

  test("seeds /mock/doctor/my-ai for cold-start /mock/doctor/patients/123", () => {
    expect(
      decideColdStartSeed({
        pathname: "/mock/doctor/patients/123",
        search: "",
        hash: "",
        historyLength: 1,
      })
    ).toEqual({
      kind: "seed",
      homePath: "/mock/doctor/my-ai",
      target: "/mock/doctor/patients/123",
    });
  });

  test("preserves search and hash in the target", () => {
    expect(
      decideColdStartSeed({
        pathname: "/doctor/patients/9",
        search: "?tab=records",
        hash: "#section-2",
        historyLength: 1,
      })
    ).toEqual({
      kind: "seed",
      homePath: "/doctor/my-ai",
      target: "/doctor/patients/9?tab=records#section-2",
    });
  });
});
