/**
 * Workflow 02 — Doctor onboarding wizard
 *
 * Mirrors docs/qa/workflows/02-onboarding.md. This is the new-doctor
 * activation path; if a step here breaks, new doctors silently fail.
 */
import { test, expect } from "./fixtures/doctor-auth";

test.describe("Workflow 02 — Onboarding wizard", () => {
  test.beforeEach(async ({ doctorPage, doctor }) => {
    // Clear any stored wizard state from previous runs. Real keys come from
    // frontend/web/src/pages/doctor/onboardingWizardState.js.
    await doctorPage.evaluate((id) => {
      localStorage.removeItem(`onboarding_wizard_progress:${id}`);
      localStorage.removeItem(`onboarding_wizard_done:${id}`);
    }, doctor.doctorId);
  });

  test("1. Wizard shell renders step 1", async ({ doctorPage }) => {
    await doctorPage.goto("/doctor/onboarding?step=1");

    // 1.1 — header + progress + footer
    await expect(doctorPage.getByText("添加一条规则")).toBeVisible();
    await expect(doctorPage.getByText("步骤 1/3")).toBeVisible();
    await expect(doctorPage.getByRole("button", { name: "下一步" })).toBeDisabled();

    // 1.2 — context card
    await expect(doctorPage.getByText(/添加一条你的诊疗规则/)).toBeVisible();

    // 1.3 — three source rows
    for (const label of ["文件上传", "网址导入", "手动输入"]) {
      await expect(doctorPage.getByText(label)).toBeVisible();
    }
  });

  test("2. Step 1 — save text rule unlocks 下一步", async ({ doctorPage }) => {
    await doctorPage.goto("/doctor/onboarding?step=1");

    // 2.1 — tap manual input → routes to add-knowledge
    await doctorPage.getByText("手动输入").click();
    await expect(doctorPage).toHaveURL(/settings\/knowledge\/add.*source=text/);

    // 2.2 — fill and save (selector names are tentative; adjust to match
    // AddKnowledgeSubpage's actual form field labels).
    await doctorPage.getByLabel(/标题/).fill("高血压患者头痛鉴别要点");
    await doctorPage
      .getByLabel(/内容|正文/)
      .fill("高血压患者新发头痛 → 排除高血压脑病、颅内出血、后循环缺血");
    await doctorPage.getByRole("button", { name: /保存|确认/ }).click();

    // 2.3 — returned to wizard, params cleaned
    await expect(doctorPage).toHaveURL(/\/doctor\/onboarding/);
    const search = await doctorPage.evaluate(() => window.location.search);
    expect(search).not.toContain("saved=");

    // 2.4 / 2.5 — row shows 已完成, next button enabled
    await expect(doctorPage.getByText("已完成").first()).toBeVisible();
    await expect(doctorPage.getByRole("button", { name: "下一步" })).toBeEnabled();
  });

  test("3. Step 2 — confirm diagnosis + send reply unlocks advance", async ({
    doctorPage,
  }) => {
    // Assume step 1 satisfied via direct URL (spec isolates step 2).
    // For a full flow test, chain from test 2 via test.serial.
    await doctorPage.goto("/doctor/onboarding?step=2");

    // 3.2 — rule echo card visible
    await expect(doctorPage.getByText("你刚添加的规则")).toBeVisible();

    // 3.4 — diagnosis row 1
    const diagRow = doctorPage.getByText("高血压脑病/高血压急症").locator("..");
    await diagRow.click(); // 3.5

    // 3.7 — tap 确认发送
    await doctorPage.getByText("确认发送 ›").click();

    // 3.8 — 下一步 enabled
    await expect(doctorPage.getByRole("button", { name: "下一步" })).toBeEnabled();
  });

  test("4. Step 3 — complete navigates to /doctor", async ({ doctorPage }) => {
    await doctorPage.goto("/doctor/onboarding?step=3");

    // 4.1
    await expect(doctorPage.getByText("设置完成")).toBeVisible();

    // 4.5 — complete
    await doctorPage.getByRole("button", { name: "完成引导" }).click();
    await expect(doctorPage).toHaveURL(/\/doctor(\/|$|\?)/);
  });

  test("5. Skip with confirm dialog", async ({ doctorPage }) => {
    await doctorPage.goto("/doctor/onboarding?step=1");

    await doctorPage.getByRole("button", { name: "跳过引导" }).click();

    // Cancel LEFT grey / confirm RIGHT green per dialog convention
    await expect(doctorPage.getByText("跳过引导？")).toBeVisible();
    await doctorPage.getByRole("button", { name: "跳过" }).click();

    await expect(doctorPage).toHaveURL(/\/doctor/);
    // Reload — wizard should not re-appear
    await doctorPage.reload();
    await expect(doctorPage.getByText("添加一条规则")).toBeHidden();
  });
});
