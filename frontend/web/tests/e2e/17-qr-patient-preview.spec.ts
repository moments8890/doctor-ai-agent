/**
 * Workflow 17 — QR invite + Patient preview
 *
 * Mirrors docs/qa/workflows/17-qr-patient-preview.md.
 */
import { test, expect } from "./fixtures/doctor-auth";
import { API_BASE_URL } from "./fixtures/doctor-auth";

test.describe("工作流 17 — 二维码与预览", () => {
  test("1. 二维码页面外壳和表单渲染", async ({ doctorPage, steps }) => {
    await doctorPage.goto("/doctor/settings/qr");

    // 1.1 — header
    await expect(doctorPage.getByText("患者预问诊码")).toBeVisible();
    await steps.capture(doctorPage, "打开二维码页面");

    // 1.2 — form elements
    await expect(doctorPage.getByText("为患者生成专属入口")).toBeVisible();
    await expect(
      doctorPage.getByPlaceholder("请输入患者姓名，例如：李阿姨"),
    ).toBeVisible();

    // 1.3 — generate button disabled when name is empty
    // AppButton renders as div, not <button> — check opacity for disabled state
    const generateBtn = doctorPage.getByText("生成入口", { exact: true });
    await expect(generateBtn).toHaveCSS("opacity", "0.5");
    await steps.capture(doctorPage, "验证表单和按钮禁用");
  });

  test("2. 生成二维码并查看结果", async ({
    doctorPage,
    doctor,
    steps,
  }) => {
    await doctorPage.goto("/doctor/settings/qr");

    // 2.1 — type a patient name
    const nameInput = doctorPage.getByPlaceholder(
      "请输入患者姓名，例如：李阿姨",
    );
    await nameInput.fill("测试患者");

    // 2.1 — button enables (opacity 1)
    const generateBtn = doctorPage.getByText("生成入口", { exact: true });
    await expect(generateBtn).toHaveCSS("opacity", "1");

    // 2.2 — tap generate
    await generateBtn.click();

    // 2.3 — wait for QR code to render. Multiple SVGs exist on page (MUI icons),
    // so check for the description text that appears alongside the QR code instead.
    await expect(
      doctorPage.getByText(/患者扫码后将进入 AI 预问诊/),
    ).toBeVisible({ timeout: 10_000 });
    await steps.capture(doctorPage, "二维码生成成功");

    // 2.3 — patient name displayed below QR
    await expect(doctorPage.getByText("测试患者").first()).toBeVisible();

    // 2.3 — description text
    await expect(
      doctorPage.getByText(/患者扫码后将进入 AI 预问诊/),
    ).toBeVisible();

    // 2.3 — action buttons (AppButton = div, use getByText)
    await expect(
      doctorPage.getByText("复制", { exact: true }),
    ).toBeVisible();
    await expect(
      doctorPage.getByText("预览", { exact: true }),
    ).toBeVisible();
    await steps.capture(doctorPage, "验证操作按钮可见");
  });

  test("3. 从二维码流程加载预览页", async ({
    doctorPage,
    doctor,
    request,
    steps,
  }) => {
    // Seed a patient entry via API (same as what the QR flow does internally)
    const res = await request.post(
      `${API_BASE_URL}/api/manage/onboarding/patient-entry`,
      {
        headers: {
          Authorization: `Bearer ${doctor.token}`,
          "Content-Type": "application/json",
        },
        data: {
          doctor_id: doctor.doctorId,
          patient_name: "预览测试患者",
        },
      },
    );
    expect(res.ok(), `patient entry creation failed: ${res.status()}`).toBeTruthy();
    const body = await res.json();
    const patientId = body.patient_id;
    const portalToken = body.portal_token || "";
    const patientName = body.patient_name || "预览测试患者";

    // Navigate directly to the preview page with proper query params
    const previewUrl = `/doctor/preview/${patientId}?patient_token=${encodeURIComponent(portalToken)}&patient_name=${encodeURIComponent(patientName)}`;
    await doctorPage.goto(previewUrl);

    // 4.2 — intro card
    await expect(doctorPage.getByText("患者端预览").first()).toBeVisible({
      timeout: 10_000,
    });
    await expect(
      doctorPage.getByText(/2 分钟左右的 AI 预问诊流程/),
    ).toBeVisible();
    await steps.capture(doctorPage, "患者端预览页面加载");
  });
});
