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

  test("filters current record when queue has integer ids and currentId is a URL string", () => {
    // Backend returns record_id as a number (DB primary key); URL gives string.
    // Strict !== would keep the current record in the list and pick it as next,
    // causing navigate-replace to the same URL → stuck spinner.
    const queue = { pending: [{ record_id: 53 }, { record_id: 54 }] };
    expect(computeNextNav(queue, "53")).toEqual({ kind: "next", nextId: 54, remaining: 1 });
  });

  test("returns done when only-current is in queue with integer id vs string currentId", () => {
    const queue = { pending: [{ record_id: 53 }] };
    expect(computeNextNav(queue, "53")).toEqual({ kind: "done" });
  });
});
