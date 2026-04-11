/**
 * Workflow 06 — Patient list + search
 *
 * Mirrors docs/qa/workflows/06-patient-list.md.
 */
import { test, expect, registerPatient } from "./fixtures/doctor-auth";
import { completePatientInterview } from "./fixtures/seed";

test.describe("Workflow 06 — Patient list", () => {
  test("1. Empty state — zero patients", async ({ doctorPage }) => {
    await doctorPage.goto("/doctor/patients");
    await expect(doctorPage.getByText(/暂无患者|添加第一位/)).toBeVisible();
  });

  test("2. Populated list with correct card content", async ({
    doctorPage,
    doctor,
    request,
  }) => {
    const p1 = await registerPatient(request, doctor.doctorId, {
      name: "张三",
      gender: "male",
      yearOfBirth: 1960,
    });
    await registerPatient(request, doctor.doctorId, {
      name: "李四",
      gender: "female",
      yearOfBirth: 1995,
    });
    await completePatientInterview(request, p1);

    await doctorPage.goto("/doctor/patients");
    await expect(doctorPage.getByText(/最近 · \d+位患者/)).toBeVisible();
    await expect(doctorPage.getByText("张三")).toBeVisible();
    await expect(doctorPage.getByText("李四")).toBeVisible();

    // 2.3 — no ISO timestamps visible
    const body = await doctorPage.locator("body").innerText();
    expect(body).not.toMatch(/\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/);
  });

  test("3. Text search filters in real time", async ({
    doctorPage,
    doctor,
    request,
  }) => {
    await registerPatient(request, doctor.doctorId, { name: "张秀兰", yearOfBirth: 1955 });
    await registerPatient(request, doctor.doctorId, { name: "李建国", yearOfBirth: 1962 });

    await doctorPage.goto("/doctor/patients");

    const search = doctorPage.getByPlaceholder(/搜索患者/);
    await search.fill("张");
    await expect(doctorPage.getByText("张秀兰")).toBeVisible();
    await expect(doctorPage.getByText("李建国")).toBeHidden();

    await search.fill("张三");
    // Autocomplete row
    await expect(doctorPage.getByText(/\+ 新建患者「张三」/)).toBeVisible();
  });

  test("4. NL search — male patients (BUG-06 regression)", async ({
    doctorPage,
    doctor,
    request,
  }) => {
    const male1 = await registerPatient(request, doctor.doctorId, {
      name: "王伟",
      gender: "male",
    });
    await registerPatient(request, doctor.doctorId, {
      name: "陈霞",
      gender: "female",
    });
    await completePatientInterview(request, male1);

    await doctorPage.goto("/doctor/patients");

    const search = doctorPage.getByPlaceholder(/搜索患者/);
    await search.fill("最近来诊的男性");

    // Wait for debounced request + UI update.
    await expect(doctorPage.getByText("王伟")).toBeVisible({ timeout: 5_000 });
    // Female patient should NOT be in results.
    await expect(doctorPage.getByText("陈霞")).toBeHidden();
  });

  test("4. NL search — no match shows empty state", async ({ doctorPage }) => {
    await doctorPage.goto("/doctor/patients");
    const search = doctorPage.getByPlaceholder(/搜索患者/);
    await search.fill("xyznotapatient");
    await expect(doctorPage.getByText(/没有找到|未匹配|无结果/).first()).toBeVisible({
      timeout: 5_000,
    });
  });
});
