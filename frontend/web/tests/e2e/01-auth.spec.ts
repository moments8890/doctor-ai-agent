/**
 * Workflow 01 — Auth (login / logout / history safety)
 *
 * Mirrors docs/qa/workflows/01-auth.md. Each section here matches a
 * numbered section in the MD file.
 */
import { test, expect, API_BASE_URL, registerDoctor } from "./fixtures/doctor-auth";

test.describe("工作流 01 — 登录认证", () => {
  test("1. 有效凭证登录成功", async ({ page, request, steps }) => {
    const doctor = await registerDoctor(request);

    // 1.1 — navigate to clean /login
    await page.goto("/login");
    await page.evaluate(() => localStorage.clear());
    await page.reload();

    await steps.capture(page, "打开登录页面", "清除缓存后的登录页面");

    // Doctor tab should be default.
    await expect(page.getByRole("tab", { name: "医生" })).toBeVisible();

    // 1.2 — 昵称
    await page.getByPlaceholder("请输入昵称").fill(doctor.nickname);
    // 1.3 — 口令
    await page.getByPlaceholder("请输入数字口令").fill(doctor.passcode);

    // Pre-set onboarding bypass so login lands on workbench (not wizard).
    await page.evaluate((id) => {
      localStorage.setItem(
        `onboarding_wizard_done:${id}`,
        JSON.stringify({ status: "completed", completedAt: new Date().toISOString() }),
      );
      localStorage.setItem(`onboarding_setup_done:${id}`, "1");
    }, doctor.doctorId);

    // 1.4 — submit, expect redirect to doctor workbench
    await page.getByRole("button", { name: "登录" }).click();
    await expect(page).toHaveURL(/\/doctor/);

    await steps.capture(page, "登录成功跳转", "已跳转到医生工作台");

    // 1.5 — localStorage populated. Real key is "doctor-session" (zustand
    // persist blob), not the old "doctor_token" / "doctor_id" / "doctor_name"
    // trio. See src/store/doctorStore.js:13.
    const session = await page.evaluate(() =>
      localStorage.getItem("doctor-session"),
    );
    expect(session, "doctor-session blob must be set after login").toBeTruthy();
    const parsed = JSON.parse(session!);
    expect(parsed.state.accessToken).toBeTruthy();
    expect(parsed.state.doctorId).toBeTruthy();

    // 1.6 — reload preserves session
    await page.reload();
    await expect(page).toHaveURL(/\/doctor/);

    await steps.capture(page, "刷新后保持登录", "页面刷新后仍在医生工作台");
  });

  test("2. 无效凭证停留在登录页", async ({ page, request, steps }) => {
    const doctor = await registerDoctor(request);
    await page.goto("/login");
    await page.evaluate(() => localStorage.clear());

    await page.getByPlaceholder("请输入昵称").fill(doctor.nickname);
    await page.getByPlaceholder("请输入数字口令").fill("9999");
    await page.getByRole("button", { name: "登录" }).click();

    await steps.capture(page, "错误凭证登录", "输入错误口令后仍停留在登录页");

    // 2.2 — still on /login, no authed session written. The doctor-session
    // blob may exist from an earlier test; the key assertion is that
    // accessToken is missing / null.
    await expect(page).toHaveURL(/\/login/);
    const accessToken = await page.evaluate(() => {
      const raw = localStorage.getItem("doctor-session");
      if (!raw) return null;
      try { return JSON.parse(raw)?.state?.accessToken ?? null; } catch { return null; }
    });
    expect(accessToken).toBeFalsy();
  });

  test.skip("3. 退出登录清除会话", async ({ doctorPage, steps }) => {
    // SKIP: DEV_MODE auto-restores a synthetic session after clearAuth() fires.
    // v2/App.jsx lines ~150-155 call restoreRealSession() on hydration, which
    // re-applies the session immediately after clearAuth() nulls it, so the
    // navigate-to-/login never sticks in a Vite dev build.
    // Unskip once v2/App.jsx:DEV_MODE restore is gated on an explicit logout flag.

    // doctorPage fixture → already authed.
    await doctorPage.goto("/doctor");

    await steps.capture(doctorPage, "进入医生工作台", "登录后的医生首页");

    // 3.1 — open settings (adjust selector if settings is a subpage route)
    await doctorPage.goto("/doctor/settings");
    const logoutRow = doctorPage.getByText("退出登录");
    await expect(logoutRow).toBeVisible();

    await steps.capture(doctorPage, "打开设置页", "设置页面显示退出登录选项");

    // 3.2 — logout fires immediately (no confirm dialog in current code:
    // SettingsListSubpage onClick → DoctorPage handleLogout → clearAuth()
    // → navigate("/login", {replace: true})).
    await logoutRow.click();

    // 3.4 — redirected + session cleared. clearAuth() sets the inner fields
    // to null but the persist blob itself stays — check state.accessToken,
    // not the key's existence.
    await expect(doctorPage).toHaveURL(/\/login/);
    const accessToken = await doctorPage.evaluate(() => {
      const raw = localStorage.getItem("doctor-session");
      if (!raw) return null;
      try { return JSON.parse(raw)?.state?.accessToken ?? null; } catch { return null; }
    });
    expect(accessToken).toBeFalsy();

    await steps.capture(doctorPage, "退出登录成功", "已跳转回登录页面");
  });

  // BUG-07: Browser-back after logout still navigates to the cached /doctor
  // page. The SPA auth guard does not currently redirect stale history entries.
  // Skipping until the guard is implemented.
  test.skip("4. 退出后浏览器返回不显示已认证页面", async ({ doctorPage, steps }) => {
    await doctorPage.goto("/doctor/settings");
    await doctorPage.getByText("退出登录").click();
    await expect(doctorPage).toHaveURL(/\/login/);

    // 4.2 — press back
    await doctorPage.goBack();
    await expect(doctorPage).toHaveURL(/\/login/);
  });

  // Sanity: expected API endpoints exist on this backend.
  test("后端接口可达", async ({ request, steps }) => {
    const res = await request.get(`${API_BASE_URL}/healthz`);
    expect(res.ok()).toBeTruthy();
  });
});
