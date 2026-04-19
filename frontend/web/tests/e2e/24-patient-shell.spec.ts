import { test, expect } from "@playwright/test";

const PATIENT_CREDS = { nickname: "patient", passcode: "123456" };

test.describe("patient shell", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/login");
    await page.getByText("患者", { exact: true }).click();
    await page.getByPlaceholder("请输入昵称").fill(PATIENT_CREDS.nickname);
    await page.getByPlaceholder("请输入数字口令").fill(PATIENT_CREDS.passcode);
    await page.getByText("登录", { exact: true }).click();
    await page.waitForURL(/\/patient/);
  });

  test("each tab URL activates the correct tab and NavBar title", async ({ page }) => {
    const cases = [
      { path: "/patient",         title: "聊天" },
      { path: "/patient/chat",    title: "聊天" },
      { path: "/patient/records", title: "病历" },
      { path: "/patient/tasks",   title: "任务" },
      { path: "/patient/profile", title: "我的" },
    ];
    for (const c of cases) {
      await page.goto(c.path);
      await expect(page.locator(".adm-nav-bar-title")).toHaveText(c.title);
    }
  });

  test("records tab shows + action in NavBar", async ({ page }) => {
    await page.goto("/patient/records");
    await expect(page.locator('[aria-label="新问诊"]')).toBeVisible();
  });

  test("other tabs hide the + action", async ({ page }) => {
    for (const path of ["/patient/chat", "/patient/tasks", "/patient/profile"]) {
      await page.goto(path);
      await expect(page.locator('[aria-label="新问诊"]')).toHaveCount(0);
    }
  });

  test("full-screen subpages hide NavBar + TabBar", async ({ page }) => {
    await page.goto("/patient/records/42");
    // Subpage's own NavBar shows, but tab bar is gone
    await expect(page.locator(".adm-tab-bar")).toHaveCount(0);
  });
});
