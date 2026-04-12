/**
 * Workflow 17 — QR invite + Patient preview
 *
 * Mirrors docs/qa/workflows/17-qr-patient-preview.md.
 */
import { test, expect } from "./fixtures/doctor-auth";
import { API_BASE_URL } from "./fixtures/doctor-auth";

test.describe("Workflow 17 — QR invite + Patient preview", () => {
  test("1. QR subpage shell renders with form", async ({ doctorPage }) => {
    await doctorPage.goto("/doctor/settings/qr");

    // 1.1 — header
    await expect(doctorPage.getByText("患者预问诊码")).toBeVisible();

    // 1.2 — form elements
    await expect(doctorPage.getByText("为患者生成专属入口")).toBeVisible();
    await expect(
      doctorPage.getByPlaceholder("请输入患者姓名，例如：李阿姨"),
    ).toBeVisible();

    // 1.3 — generate button disabled when name is empty
    const generateBtn = doctorPage.getByRole("button", { name: "生成入口" });
    await expect(generateBtn).toBeDisabled();
  });

  test("2. Generate QR code and see result", async ({
    doctorPage,
    doctor,
  }) => {
    await doctorPage.goto("/doctor/settings/qr");

    // 2.1 — type a patient name
    const nameInput = doctorPage.getByPlaceholder(
      "请输入患者姓名，例如：李阿姨",
    );
    await nameInput.fill("测试患者");

    // 2.1 — button enables
    const generateBtn = doctorPage.getByRole("button", { name: "生成入口" });
    await expect(generateBtn).toBeEnabled();

    // 2.2 — tap generate
    await generateBtn.click();

    // 2.3 — wait for QR code to render (the QRCodeSVG component renders an
    // <svg> element once the portal_url is set)
    await expect(doctorPage.locator("svg")).toBeVisible({ timeout: 10_000 });

    // 2.3 — patient name displayed below QR
    await expect(doctorPage.getByText("测试患者").first()).toBeVisible();

    // 2.3 — description text
    await expect(
      doctorPage.getByText(/患者扫码后将进入 AI 预问诊/),
    ).toBeVisible();

    // 2.3 — action buttons
    await expect(
      doctorPage.getByRole("button", { name: "复制" }),
    ).toBeVisible();
    await expect(
      doctorPage.getByRole("button", { name: "预览" }),
    ).toBeVisible();
  });

  test("3. Preview page loads from QR flow", async ({
    doctorPage,
    doctor,
    request,
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
    await expect(doctorPage.getByText("患者端预览")).toBeVisible({
      timeout: 10_000,
    });
    await expect(
      doctorPage.getByText(/2 分钟左右的 AI 预问诊流程/),
    ).toBeVisible();
  });
});
