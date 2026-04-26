/**
 * Workflow 06 — Patient list + search
 *
 * Mirrors docs/qa/workflows/06-patient-list.md.
 */
import { test, expect, registerPatient } from "./fixtures/doctor-auth";
import { completePatientIntake } from "./fixtures/seed";

test.describe("工作流 06 — 患者列表", () => {
  // Skip: preseed creates demo patient on registration, empty state unreachable
  test.skip("1. 空状态 — 零患者", async ({ doctorPage, steps }) => {
    await doctorPage.goto("/doctor/patients");
    // Actual empty state text is "暂无患者档案"
    await expect(doctorPage.getByText("暂无患者档案")).toBeVisible();
  });

  test("2. 患者列表卡片内容正确", async ({
    doctorPage,
    doctor,
    request,
    steps,
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
    await completePatientIntake(request, p1);

    await doctorPage.goto("/doctor/patients");

    await steps.capture(doctorPage, "患者列表页面", "显示已注册患者列表");

    // Footer text changed from "最近 · N位患者" to "共 N 位患者" (PatientsPage footer)
    await expect(doctorPage.getByText(/共 \d+ 位患者/)).toBeVisible();
    await expect(doctorPage.getByText("张三E2E06a").first()).toBeVisible();
    await expect(doctorPage.getByText("李四E2E06a").first()).toBeVisible();

    // 2.3 — no ISO timestamps visible
    const body = await doctorPage.locator("body").innerText();
    expect(body).not.toMatch(/\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/);

    await steps.capture(doctorPage, "验证患者卡片内容", "患者姓名和数量显示正确");
  });

  test("3. 文本搜索实时过滤", async ({
    doctorPage,
    doctor,
    request,
    steps,
  }) => {
    await registerPatient(request, doctor.doctorId, { name: "张秀兰E2E06b", yearOfBirth: 1955 });
    await registerPatient(request, doctor.doctorId, { name: "李建国E2E06b", yearOfBirth: 1962 });

    await doctorPage.goto("/doctor/patients");

    const search = doctorPage.getByPlaceholder(/搜索患者/);
    await search.fill("张秀兰");
    await expect(doctorPage.getByText("张秀兰E2E06b").first()).toBeVisible();
    await expect(doctorPage.getByText("李建国E2E06b")).toBeHidden();

    await steps.capture(doctorPage, "搜索过滤患者", "搜索张秀兰后只显示匹配患者");

    await search.fill("张三E2E06unique");
    // When no patient matches, PatientsPage shows an EmptyState "无匹配患者".
    // The old "+ 新建患者「...」" autocomplete row was removed in the v2 redesign.
    await expect(doctorPage.getByText(/无匹配患者/)).toBeVisible();

    await steps.capture(doctorPage, "新建患者提示", "搜索不存在的名字后显示新建选项");
  });

  // Skip: NL search requires LLM backend
  test.skip("4. 自然语言搜索 — 男性患者（BUG-06回归）", async ({
    doctorPage,
    doctor,
    request,
    steps,
  }) => {
    const male1 = await registerPatient(request, doctor.doctorId, {
      name: "王伟E2E06c",
      gender: "male",
    });
    await registerPatient(request, doctor.doctorId, {
      name: "陈霞E2E06c",
      gender: "female",
    });
    await completePatientIntake(request, male1);

    await doctorPage.goto("/doctor/patients");

    const search = doctorPage.getByPlaceholder(/搜索患者/);
    await search.fill("最近来诊的男性");

    // Wait for debounced request + UI update.
    await expect(doctorPage.getByText("王伟E2E06c").first()).toBeVisible({ timeout: 5_000 });
    // Female patient should NOT be in results.
    await expect(doctorPage.getByText("陈霞E2E06c")).toBeHidden();
  });

  test("4. 自然语言搜索 — 无匹配显示空状态", async ({ doctorPage, steps }) => {
    await doctorPage.goto("/doctor/patients");
    const search = doctorPage.getByPlaceholder(/搜索患者/);
    await search.fill("xyznotapatient");
    // PatientsPage empty state when search yields no matches is "无匹配患者"
    // (EmptyState title in PatientsPage). Old text "未找到患者" was removed.
    await expect(
      doctorPage.getByText(/无匹配患者/).first(),
    ).toBeVisible({ timeout: 5_000 });

    await steps.capture(doctorPage, "搜索无结果状态", "搜索不存在患者后显示未找到提示");
  });
});
