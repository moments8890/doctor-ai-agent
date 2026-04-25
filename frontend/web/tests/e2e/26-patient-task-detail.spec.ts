import { test, expect } from "@playwright/test";

const SEEDED_AUTH = {
  state: {
    token: "seeded-patient-token",
    patientId: "1",
    patientName: "测试患者",
    doctorId: "seeded_doctor",
    doctorName: "测试医生",
  },
  version: 0,
};

const PENDING_TASK = {
  id: 7,
  task_type: "general",
  title: "测试任务",
  content: "请完成此任务",
  status: "pending",
  due_at: null,
  source_type: null,
  created_at: "2026-04-20T10:00:00Z",
  completed_at: null,
  source_record_id: null,
};

const COMPLETED_TASK = {
  ...PENDING_TASK,
  status: "completed",
  completed_at: "2026-04-20T11:00:00Z",
};

test.describe("patient task detail", () => {
  test.beforeEach(async ({ page }) => {
    await page.route("**/api/patient/me", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          patient_id: 1,
          patient_name: "测试患者",
          doctor_id: "seeded_doctor",
          doctor_name: "测试医生",
        }),
      }),
    );
    await page.addInitScript((auth) => {
      localStorage.setItem("patient-portal-auth", JSON.stringify(auth));
    }, SEEDED_AUTH);
  });

  test("list → body-tap → detail → 标记完成 keeps user on detail", async ({ page }) => {
    await page.route("**/api/patient/tasks", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([PENDING_TASK]),
      }),
    );
    await page.route("**/api/patient/tasks/7", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(PENDING_TASK),
      }),
    );
    await page.route("**/api/patient/tasks/7/complete", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          ...PENDING_TASK,
          status: "completed",
          completed_at: "2026-04-20T11:00:00Z",
        }),
      }),
    );

    await page.goto("/patient/tasks");
    const row = page.locator('[data-testid="patient-task-row"]').first();
    await expect(row).toBeVisible();
    // Body tap (NOT the prefix circle) navigates to detail. The row's onClick
    // handles tap-to-detail; the prefix circle stops propagation.
    await row.click();

    await expect(page).toHaveURL(/\/patient\/tasks\/7/);
    await expect(page.getByText("测试任务")).toBeVisible();

    await page.getByText("标记完成", { exact: true }).click();

    // No auto-redirect — user stays on the detail page after the mutation.
    await expect(page).toHaveURL(/\/patient\/tasks\/7/);
  });

  test("撤销完成 with confirm dialog", async ({ page }) => {
    await page.route("**/api/patient/tasks/7", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(COMPLETED_TASK),
      }),
    );
    let uncompleteHit = false;
    await page.route("**/api/patient/tasks/7/uncomplete", (route) => {
      uncompleteHit = true;
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          ...COMPLETED_TASK,
          status: "pending",
          completed_at: null,
        }),
      });
    });

    await page.goto("/patient/tasks/7");
    await expect(page.getByText("测试任务")).toBeVisible();
    await page.getByText("撤销完成", { exact: true }).click();

    // Dialog.confirm content
    await expect(page.getByText("确定要撤销该任务的完成状态吗？")).toBeVisible();
    // antd-mobile Dialog.confirm renders the buttons as <Box>, so click by text.
    await page.getByText("撤销", { exact: true }).click();

    await expect.poll(() => uncompleteHit).toBe(true);
  });

  test("deep-link hard-refresh works (per-id endpoint)", async ({ page }) => {
    // Only stub the per-id endpoint, NOT the list endpoint.
    await page.route("**/api/patient/tasks/7", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(PENDING_TASK),
      }),
    );

    await page.goto("/patient/tasks/7");
    await expect(page.getByText("测试任务")).toBeVisible();
    await expect(page.getByText("任务不存在或已删除")).toHaveCount(0);
  });
});
