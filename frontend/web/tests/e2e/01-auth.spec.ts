/**
 * Workflow 01 — Auth (login / logout / history safety)
 *
 * Mirrors docs/qa/workflows/01-auth.md. Each section here matches a
 * numbered section in the MD file.
 */
import { test, expect, API_BASE_URL, registerDoctor } from "./fixtures/doctor-auth";

test.describe("Workflow 01 — Auth", () => {
  test("1. Login with valid credentials", async ({ page, request }) => {
    const doctor = await registerDoctor(request);

    // 1.1 — navigate to clean /login
    await page.goto("/login");
    await page.evaluate(() => localStorage.clear());
    await page.reload();

    // Doctor tab should be default.
    await expect(page.getByRole("tab", { name: "医生" })).toBeVisible();

    // 1.2 — 昵称 = phone
    await page.getByLabel(/昵称|手机号/).fill(doctor.phone);
    // 1.3 — 口令 = birth year
    await page.getByLabel(/口令|密码/).fill(String(doctor.yearOfBirth));

    // 1.4 — submit, expect 4-tab bottom nav
    await page.getByRole("button", { name: "登录" }).click();
    await expect(page).toHaveURL(/\/doctor/);
    for (const label of ["我的AI", "患者", "审核", "任务"]) {
      await expect(page.getByRole("tab", { name: label }).or(page.getByText(label))).toBeVisible();
    }

    // 1.5 — localStorage populated
    const token = await page.evaluate(() => localStorage.getItem("doctor_token"));
    expect(token, "doctor_token must be set after login").toBeTruthy();

    // 1.6 — reload preserves session
    await page.reload();
    await expect(page).toHaveURL(/\/doctor/);
  });

  test("2. Login with invalid credentials stays on /login", async ({ page, request }) => {
    const doctor = await registerDoctor(request);
    await page.goto("/login");
    await page.evaluate(() => localStorage.clear());

    await page.getByLabel(/昵称|手机号/).fill(doctor.phone);
    await page.getByLabel(/口令|密码/).fill("9999");
    await page.getByRole("button", { name: "登录" }).click();

    // 2.2 — still on /login, no tokens written.
    await expect(page).toHaveURL(/\/login/);
    const token = await page.evaluate(() => localStorage.getItem("doctor_token"));
    expect(token).toBeFalsy();
  });

  test("3. Logout clears session", async ({ doctorPage }) => {
    // doctorPage fixture → already authed.
    await doctorPage.goto("/doctor");

    // 3.1 — open settings (adjust selector if settings is a subpage route)
    await doctorPage.goto("/doctor/settings");
    const logoutRow = doctorPage.getByText("退出登录");
    await expect(logoutRow).toBeVisible();

    // 3.2 / 3.3 — logout (may show confirm dialog)
    await logoutRow.click();
    const confirmBtn = doctorPage.getByRole("button", { name: /退出|确认/ });
    if (await confirmBtn.isVisible().catch(() => false)) {
      await confirmBtn.click();
    }

    // 3.4 — redirected + cleared
    await expect(doctorPage).toHaveURL(/\/login/);
    const token = await doctorPage.evaluate(() => localStorage.getItem("doctor_token"));
    expect(token).toBeFalsy();
  });

  test("4. Browser-back after logout does not show authed pages (BUG-07)", async ({ doctorPage }) => {
    await doctorPage.goto("/doctor/settings");
    await doctorPage.getByText("退出登录").click();
    const confirmBtn = doctorPage.getByRole("button", { name: /退出|确认/ });
    if (await confirmBtn.isVisible().catch(() => false)) {
      await confirmBtn.click();
    }
    await expect(doctorPage).toHaveURL(/\/login/);

    // 4.2 — press back
    await doctorPage.goBack();
    await expect(doctorPage).toHaveURL(/\/login/);
  });

  // Sanity: expected API endpoints exist on this backend.
  test("backend is reachable", async ({ request }) => {
    const res = await request.get(`${API_BASE_URL}/api/health`);
    expect(res.ok()).toBeTruthy();
  });
});
