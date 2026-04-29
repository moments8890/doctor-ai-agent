/**
 * Workflow 17 — Patient invite code + QR
 *
 * The flow was simplified per the security/beta review: a doctor now has
 * a permanent 4-char attach code (no per-patient generation, no rotation).
 * Patients scan the QR or type the code to register against this doctor.
 *
 * What changed from the old spec:
 *   - Header: 患者预问诊码 → 我的患者邀请码
 *   - No per-patient name input + "生成入口" button (auto-loaded code instead)
 *   - No "预览" action — the doctor-side patient-preview page was removed
 *     when the per-patient generation flow was retired.
 */
import { test, expect } from "./fixtures/doctor-auth";

test.describe("工作流 17 — 邀请码与二维码", () => {
  test("1. 邀请码页面外壳渲染", async ({ doctorPage, steps }) => {
    await doctorPage.goto("/doctor/settings/qr");

    await expect(doctorPage.getByText("我的患者邀请码")).toBeVisible();
    await steps.capture(doctorPage, "打开邀请码页面");

    // The intro paragraph explains the flow.
    await expect(
      doctorPage.getByText(/4 位邀请码就可以加入您的患者列表/),
    ).toBeVisible();
  });

  test("2. 邀请码已加载且可复制", async ({ doctorPage, steps }) => {
    await doctorPage.goto("/doctor/settings/qr");

    // The code is fetched from getDoctorAttachCode on mount. Wait for the
    // 4-char display to settle (placeholder is "····" while loading).
    // Match a 4-char alphanumeric block via regex.
    await expect(
      doctorPage.getByText(/^[A-Z0-9]{4}$/).first(),
    ).toBeVisible({ timeout: 10_000 });

    await steps.capture(doctorPage, "邀请码已加载");

    // Copy action surfaces a Toast — clicking shouldn't throw.
    await doctorPage.getByText("复制邀请码").click();
    await expect(doctorPage.getByText("已复制")).toBeVisible({ timeout: 5_000 });
    await steps.capture(doctorPage, "复制邀请码");
  });

  // Test 3 (preview page) removed — the doctor-side patient preview route
  // (/doctor/preview/:patientId) was retired with the QR redesign. There is
  // no per-patient generation flow to preview into anymore.
});
