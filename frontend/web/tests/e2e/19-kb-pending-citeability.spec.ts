/**
 * Workflow 19 — KB-pending accept writes rule to Knowledge list
 *
 * Proves the full factual-edit loop:
 *   1. A KbPendingItem is seeded directly via the test-only endpoint
 *      POST /api/test/seed/kb-pending (ENVIRONMENT=test guard).
 *   2. The doctor opens the "AI发现" pending review page and clicks 保存为规则.
 *   3. The backend calls save_knowledge_item → inserts into doctor_knowledge_items.
 *   4. The doctor navigates to the Knowledge list and the rule is visible.
 *
 * The final leg ("rule becomes [KB-N] citeable in a draft") requires a live
 * LLM and is out of scope here. Stopping at "rule appears in KB list" is
 * sufficient to gate the accept-write pathway.
 *
 * Requires: backend on :8000 (ENVIRONMENT=test or dev), frontend on :5173.
 */
import { test, expect } from "./fixtures/doctor-auth";
import { API_BASE_URL } from "./fixtures/doctor-auth";

test.describe("工作流 19 — KB待确认 → 接受 → 知识库可见", () => {
  test("1. 接受待确认规则后规则出现在知识库列表", async ({
    doctorPage,
    doctor,
    request,
    steps,
  }) => {
    // ── Step 1: Seed a KbPendingItem via test-only endpoint ──────────────────
    const seedResp = await request.post(
      `${API_BASE_URL}/api/test/seed/kb-pending?doctor_id=${encodeURIComponent(doctor.doctorId)}`,
      {
        headers: {
          "Authorization": `Bearer ${doctor.token}`,
          "Content-Type": "application/json",
        },
        data: {
          category: "medication",
          proposed_rule: "颅脑术后头痛不建议使用NSAIDs，首选对乙酰氨基酚",
          summary: "术后头痛药物选择",
          confidence: "high",
        },
      },
    );
    expect(
      seedResp.ok(),
      `test-seed endpoint failed: ${seedResp.status()} ${await seedResp.text()}`,
    ).toBeTruthy();
    const { id: pendingId } = await seedResp.json();
    expect(pendingId).toBeTruthy();
    await steps.capture(doctorPage, `seeded KbPendingItem id=${pendingId}`);

    // ── Step 2: Pre-dismiss the "what's new" release-notes modal ─────────────
    // The modal is driven by `seen_releases:<doctorId>` in localStorage.
    // A fresh doctor has no seen_releases entry, so it shows on first visit.
    // We set it here so the pending-review page isn't blocked.
    await doctorPage.evaluate((id) => {
      localStorage.setItem(`seen_releases:${id}`, JSON.stringify(["2.0.0"]));
    }, doctor.doctorId);

    // ── Step 3: Navigate to KB pending review page ───────────────────────────
    await doctorPage.goto("/doctor/settings/knowledge/pending");
    await steps.capture(doctorPage, "打开AI发现页面");

    // ── Step 3: Verify the seeded rule is shown ──────────────────────────────
    await expect(
      doctorPage.getByText("颅脑术后头痛不建议使用NSAIDs"),
    ).toBeVisible({ timeout: 10_000 });
    await steps.capture(doctorPage, "待确认规则可见");

    // ── Step 4: Click 保存为规则 (AppButton renders as div, not <button>) ─────
    await doctorPage.getByText("保存为规则", { exact: true }).click();

    // The accept call is async; wait for the item to disappear (accepted items
    // are removed from the pending list) as a signal the write completed.
    await expect(
      doctorPage.getByText("颅脑术后头痛不建议使用NSAIDs"),
    ).toBeHidden({ timeout: 10_000 });
    await steps.capture(doctorPage, "规则已接受并从待确认列表移除");

    // ── Step 5: Navigate to Knowledge list and verify rule is present ─────────
    // Use .first() — the KB card renders the full text twice (title + body),
    // which causes strict-mode failure if both are visible. .first() is safe.
    await doctorPage.goto("/doctor/settings/knowledge");
    await expect(
      doctorPage.getByText("颅脑术后头痛不建议使用NSAIDs").first(),
    ).toBeVisible({ timeout: 10_000 });
    await steps.capture(doctorPage, "规则出现在知识库列表");
  });

  test("2. 拒绝待确认规则后规则不写入知识库", async ({
    doctorPage,
    doctor,
    request,
    steps,
  }) => {
    // Seed a rule we intend to reject
    const seedResp = await request.post(
      `${API_BASE_URL}/api/test/seed/kb-pending?doctor_id=${encodeURIComponent(doctor.doctorId)}`,
      {
        headers: {
          "Authorization": `Bearer ${doctor.token}`,
          "Content-Type": "application/json",
        },
        data: {
          category: "followup",
          proposed_rule: "E2E测试拒绝规则不应出现在知识库",
          summary: "测试拒绝路径",
          confidence: "low",
        },
      },
    );
    expect(seedResp.ok(), `test-seed failed: ${seedResp.status()} ${await seedResp.text()}`).toBeTruthy();
    await steps.capture(doctorPage, "seeded rule for rejection test");

    // Pre-dismiss release-notes modal (same guard as test 1)
    await doctorPage.evaluate((id) => {
      localStorage.setItem(`seen_releases:${id}`, JSON.stringify(["2.0.0"]));
    }, doctor.doctorId);

    // Open pending review
    await doctorPage.goto("/doctor/settings/knowledge/pending");
    await expect(
      doctorPage.getByText("E2E测试拒绝规则不应出现在知识库"),
    ).toBeVisible({ timeout: 10_000 });
    await steps.capture(doctorPage, "待确认规则可见");

    // Click 排除 (reject button — AppButton renders as div)
    await doctorPage.getByText("排除", { exact: true }).first().click();

    // ConfirmDialog appears — confirm the rejection
    // ConfirmDialog primary button is on the RIGHT (danger = red per design system)
    const confirmBtn = doctorPage.getByText("确认排除", { exact: true });
    if (await confirmBtn.isVisible({ timeout: 3_000 }).catch(() => false)) {
      await confirmBtn.click();
    }

    // Item removed from pending list
    await expect(
      doctorPage.getByText("E2E测试拒绝规则不应出现在知识库"),
    ).toBeHidden({ timeout: 10_000 });
    await steps.capture(doctorPage, "规则已从待确认列表移除");

    // Rule must NOT appear in the KB list
    await doctorPage.goto("/doctor/settings/knowledge");
    await expect(
      doctorPage.getByText("E2E测试拒绝规则不应出现在知识库"),
    ).toBeHidden({ timeout: 5_000 });
    await steps.capture(doctorPage, "确认拒绝规则未写入知识库");
  });
});
