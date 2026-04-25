// TDD test for the patient filter reducer used by the admin v3 患者 tab.
// Spec: docs/plans/2026-04-24-admin-modern-port.md — Task 2.3 step 1.
//
// applyFilter is a pure function that takes the patient list + the active
// filter key and returns the filtered slice. usePatientFilter is the React
// hook wrapper that adds the filter state + counts; it's exercised indirectly
// here through applyFilter to keep the test deterministic and DOM-free.

import { describe, it, expect } from "vitest";
import { applyFilter } from "../../src/pages/admin/v3/hooks/usePatientFilter";

const SAMPLE = [
  { id: 1, name: "陈玉琴", risk: "warn",   silentDays: 0,  isPostOp: false },
  { id: 2, name: "周建国", risk: null,     silentDays: 1,  isPostOp: true  },
  { id: 3, name: "林文华", risk: "danger", silentDays: 0,  isPostOp: false },
  { id: 4, name: "何建华", risk: null,     silentDays: 12, isPostOp: false },
];

describe("applyFilter", () => {
  it("returns all when filter='all'", () => {
    expect(applyFilter(SAMPLE, "all")).toHaveLength(4);
  });

  it("returns only danger when filter='danger'", () => {
    expect(applyFilter(SAMPLE, "danger").map((p) => p.name)).toEqual(["林文华"]);
  });

  it("returns only warn (未达标) when filter='warn'", () => {
    expect(applyFilter(SAMPLE, "warn").map((p) => p.name)).toEqual(["陈玉琴"]);
  });

  it("returns silent>=7 when filter='silent'", () => {
    expect(applyFilter(SAMPLE, "silent").map((p) => p.name)).toEqual(["何建华"]);
  });

  it("returns post-op when filter='postop'", () => {
    expect(applyFilter(SAMPLE, "postop").map((p) => p.name)).toEqual(["周建国"]);
  });
});
