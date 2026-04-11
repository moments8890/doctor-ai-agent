/**
 * Workflow 10 — Tasks browse + complete
 *
 * Mirrors docs/qa/workflows/10-tasks.md. Task creation depends on
 * review suggestion confirmation; tests here are skeleton until a
 * direct task seed endpoint exists.
 */
import { test, expect } from "./fixtures/doctor-auth";

test.describe("Workflow 10 — Tasks", () => {
  test("1. Task list shell renders tabs", async ({ doctorPage }) => {
    await doctorPage.goto("/doctor/tasks");
    await expect(doctorPage.getByText("任务").first()).toBeVisible();
    for (const label of ["待处理", "已安排", "已发送", "已完成"]) {
      await expect(doctorPage.getByText(label, { exact: true })).toBeVisible();
    }
  });

  test("2. Empty tab states", async ({ doctorPage }) => {
    await doctorPage.goto("/doctor/tasks");
    // Fresh doctor — expect empty state for all tabs.
    const empty = doctorPage.getByText(/暂无|没有/).first();
    await expect(empty).toBeVisible();

    // Switch to 已完成 — still empty.
    await doctorPage.getByText("已完成", { exact: true }).click();
    await expect(doctorPage.getByText(/暂无|没有/).first()).toBeVisible();
  });

  // Deferred until we have a seed helper for tasks (or a test-only API to
  // create one directly instead of going through review confirmation).
  test.skip("3-7. Complete / reschedule / cancel task", async () => {});
});
