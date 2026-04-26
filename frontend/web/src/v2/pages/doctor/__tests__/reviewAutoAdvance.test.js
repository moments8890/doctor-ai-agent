import { describe, test, expect } from "vitest";
import { computeNextNav } from "../reviewAutoAdvance";

describe("computeNextNav", () => {
  test("returns next pending record id, excluding current", () => {
    const queue = {
      pending: [
        { record_id: "r1" },
        { record_id: "r2" },
        { record_id: "r3" },
      ],
    };
    expect(computeNextNav(queue, "r1")).toEqual({ kind: "next", nextId: "r2", remaining: 2 });
  });

  test("excludes current even if not first in queue", () => {
    const queue = {
      pending: [
        { record_id: "r1" },
        { record_id: "r2" },
      ],
    };
    expect(computeNextNav(queue, "r2")).toEqual({ kind: "next", nextId: "r1", remaining: 1 });
  });

  test("returns done when no other pending items remain", () => {
    const queue = { pending: [{ record_id: "r1" }] };
    expect(computeNextNav(queue, "r1")).toEqual({ kind: "done" });
  });

  test("handles null/undefined queue", () => {
    expect(computeNextNav(null, "r1")).toEqual({ kind: "done" });
    expect(computeNextNav(undefined, "r1")).toEqual({ kind: "done" });
  });

  test("handles missing pending field", () => {
    expect(computeNextNav({}, "r1")).toEqual({ kind: "done" });
  });
});
