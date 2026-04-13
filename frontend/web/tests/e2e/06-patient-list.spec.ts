/**
 * Workflow 06 — Patient list + search
 *
 * Mirrors docs/qa/workflows/06-patient-list.md.
 */
import { test, expect, registerPatient } from "./fixtures/doctor-auth";
import { completePatientInterview } from "./fixtures/seed";

test.describe("Workflow 06 — Patient list", () => {
  // Skip: preseed creates demo patient on registration, empty state unreachable
  test.skip("1. Empty state — zero patients", async ({ doctorPage }) => {
    await doctorPage.goto("/doctor/patients");
    // Actual empty state text is "暂无患者档案"
    await expect(doctorPage.getByText("暂无患者档案")).toBeVisible();
  });

  test("2. Populated list with correct card content", async ({
    doctorPage,
    doctor,
    request,
  }) => {
    const p1 = await registerPatient(request, doctor.doctorId, {
      name: "张三E2E06a",
      gender: "male",
      yearOfBirth: 1960,
    });
    await registerPatient(request, doctor.doctorId, {
      name: "李四E2E06a",
      gender: "female",
      yearOfBirth: 1995,
    });
    await completePatientInterview(request, p1);

    await doctorPage.goto("/doctor/patients");
    await expect(doctorPage.getByText(/最近 · \d+位患者/)).toBeVisible();
    await expect(doctorPage.getByText("张三E2E06a").first()).toBeVisible();
    await expect(doctorPage.getByText("李四E2E06a").first()).toBeVisible();

    // 2.3 — no ISO timestamps visible
    const body = await doctorPage.locator("body").innerText();
    expect(body).not.toMatch(/\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/);
  });

  test("3. Text search filters in real time", async ({
    doctorPage,
    doctor,
    request,
  }) => {
    await registerPatient(request, doctor.doctorId, { name: "张秀兰E2E06b", yearOfBirth: 1955 });
    await registerPatient(request, doctor.doctorId, { name: "李建国E2E06b", yearOfBirth: 1962 });

    await doctorPage.goto("/doctor/patients");

    const search = doctorPage.getByPlaceholder(/搜索患者/);
    await search.fill("张秀兰");
    await expect(doctorPage.getByText("张秀兰E2E06b").first()).toBeVisible();
    await expect(doctorPage.getByText("李建国E2E06b")).toBeHidden();

    await search.fill("张三E2E06unique");
    // Autocomplete creates a "new patient" row
    await expect(doctorPage.getByText(/\+ 新建患者「张三E2E06unique」/)).toBeVisible();
  });

  // Skip: NL search requires LLM backend
  test.skip("4. NL search — male patients (BUG-06 regression)", async ({
    doctorPage,
    doctor,
    request,
  }) => {
    const male1 = await registerPatient(request, doctor.doctorId, {
      name: "王伟E2E06c",
      gender: "male",
    });
    await registerPatient(request, doctor.doctorId, {
      name: "陈霞E2E06c",
      gender: "female",
    });
    await completePatientInterview(request, male1);

    await doctorPage.goto("/doctor/patients");

    const search = doctorPage.getByPlaceholder(/搜索患者/);
    await search.fill("最近来诊的男性");

    // Wait for debounced request + UI update.
    await expect(doctorPage.getByText("王伟E2E06c").first()).toBeVisible({ timeout: 5_000 });
    // Female patient should NOT be in results.
    await expect(doctorPage.getByText("陈霞E2E06c")).toBeHidden();
  });

  test("4. NL search — no match shows empty state", async ({ doctorPage }) => {
    await doctorPage.goto("/doctor/patients");
    const search = doctorPage.getByPlaceholder(/搜索患者/);
    await search.fill("xyznotapatient");
    // The Autocomplete noOptionsText is "未找到患者". It may also show the
    // PatientList empty state "未找到患者「xyznotapatient」".
    // Check for either text appearing.
    await expect(
      doctorPage.getByText(/未找到患者/).first(),
    ).toBeVisible({ timeout: 5_000 });
  });
});
