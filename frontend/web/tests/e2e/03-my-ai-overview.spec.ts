/**
 * Workflow 03 — My AI tab overview
 *
 * Mirrors docs/qa/workflows/03-my-ai-overview.md.
 */
import { test, expect } from "./fixtures/doctor-auth";
import {
  addKnowledgeText,
  addPersonaRule,
  completePatientInterview,
} from "./fixtures/seed";

test.describe("Workflow 03 — My AI overview", () => {
  test("populated doctor — all sections render", async ({
    doctorPage,
    doctor,
    patient,
    request,
  }) => {
    // Seed: 2 knowledge items, 1 persona rule, 1 completed interview.
    // category must be a valid enum: custom|diagnosis|followup|medication.
    await addKnowledgeText(request, doctor, "高血压头痛需先排除高血压脑病");
    await addKnowledgeText(request, doctor, "回访48小时血压记录");
    await addPersonaRule(request, doctor, "reply_style", "口语化回复，像微信聊天");
    await completePatientInterview(request, patient);

    await doctorPage.goto("/doctor/my-ai");

    // 1.1 — shell
    await expect(doctorPage.getByText("我的AI").first()).toBeVisible();
    await expect(doctorPage.getByText("本服务为AI生成内容，结果仅供参考")).toBeVisible();

    // 2.2 — hero AI name: "XXX 的 AI" — no duplicate 医生
    const aiNameLocator = doctorPage.getByText(new RegExp(`${doctor.name}.*AI`));
    await expect(aiNameLocator).toBeVisible();
    const aiNameText = await aiNameLocator.textContent();
    expect(aiNameText).not.toContain("医生医生");

    // 2.3 — knowledge subtitle
    await expect(doctorPage.getByText(/已学会 \d+ 条知识/)).toBeVisible();

    // 2.5 — 3 stat columns
    for (const label of ["7天引用", "待确认", "今日处理"]) {
      await expect(doctorPage.getByText(label)).toBeVisible();
    }

    // 3.1 — CTA row (rendered as Box elements, not buttons)
    await expect(doctorPage.getByText("我的AI风格").first()).toBeVisible();
    await expect(doctorPage.getByText("我的知识库").first()).toBeVisible();

    // 4 — quick actions
    await expect(doctorPage.getByText("快捷入口")).toBeVisible();
    await expect(doctorPage.getByText("新建病历")).toBeVisible();
    await expect(doctorPage.getByText("患者预问诊码")).toBeVisible();

    // 5 — persona card (section title is "我的AI风格")
    await expect(doctorPage.getByText(/我的AI风格.*决定AI怎么说话/)).toBeVisible();
    await expect(doctorPage.getByText(/口语化回复/)).toBeVisible();

    // 6 — knowledge preview
    await expect(doctorPage.getByText(/我的知识库.*决定AI知道什么/)).toBeVisible();
    await expect(doctorPage.getByText(/全部 \d+ 条/)).toBeVisible();

    // 6.4 — relative date must NOT be "-1天前" (BUG-01 gate)
    const bodyText = await doctorPage.locator("body").innerText();
    expect(bodyText).not.toMatch(/-1天前/);
  });

  test("fresh doctor — persona empty state renders", async ({ doctorPage }) => {
    await doctorPage.goto("/doctor/my-ai");

    // Registration auto-seeds 3 knowledge items via preseed_service, so
    // the knowledge section is never truly empty. Only persona is empty.

    // 2.3 — knowledge subtitle reflects seeded items
    await expect(doctorPage.getByText(/已学会 \d+ 条知识/)).toBeVisible();

    // 5.3 — persona empty hint
    await expect(doctorPage.getByText("尚未设置，点击编辑开始配置")).toBeVisible();
  });

  test("navigation — CTAs route to correct subpages", async ({ doctorPage }) => {
    await doctorPage.goto("/doctor/my-ai");

    // CTA buttons are AppButton (Box), not role="button". Use getByText.
    // "我的AI风格" appears multiple times; click the first (CTA row).
    await doctorPage.getByText("我的AI风格").first().click();
    await expect(doctorPage).toHaveURL(/\/doctor\/settings\/persona/);
    await doctorPage.goBack();

    await doctorPage.getByText("我的知识库").first().click();
    await expect(doctorPage).toHaveURL(/\/doctor\/settings\/knowledge/);
  });
});
