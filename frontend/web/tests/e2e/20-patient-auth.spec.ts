/**
 * Workflow 20 — Patient auth smoke
 */
import { test, expect, authenticatePatientPage, loginAsTestDoctor, loginAsTestPatient } from "./fixtures/doctor-auth";

test.describe("工作流 20 — 患者登录", () => {
  test("患者端加载显示4个底部标签", async ({ page, request, steps }) => {
    const doctor = await loginAsTestDoctor(request);
    const patient = await loginAsTestPatient(request, doctor.doctorId);
    await authenticatePatientPage(page, patient, doctor.name);

    // Mark onboarding done so it doesn't block nav assertions
    await page.evaluate((pid) => {
      localStorage.setItem("patient_onboarding_done_" + pid, "1");
    }, patient.patientId);

    await page.goto("/patient");
    await page.waitForLoadState("networkidle");
    await steps.capture(page, "患者端主页加载");

    // Bottom nav labels (PatientPage.jsx:58-61): 聊天 / 病历 / 任务 / 我的.
    // Scope to the antd-mobile TabBar so the same label in the NavBar title
    // doesn't trigger strict-mode "resolved to 2 elements". The nav items
    // are divs (not <button>) — see CLAUDE.md selector rules.
    const tabBar = page.locator(".adm-tab-bar");
    await expect(tabBar.getByText("聊天", { exact: true })).toBeVisible();
    await expect(tabBar.getByText("病历", { exact: true })).toBeVisible();
    await expect(tabBar.getByText("任务", { exact: true })).toBeVisible();
    await expect(tabBar.getByText("我的", { exact: true })).toBeVisible();
    await steps.capture(page, "验证四个导航标签");
  });
});
