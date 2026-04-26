/**
 * Workflow 03 — My AI tab overview
 *
 * Mirrors docs/qa/workflows/03-my-ai-overview.md.
 */
import { test, expect } from "./fixtures/doctor-auth";
import {
  addKnowledgeText,
  addPersonaRule,
  completePatientIntake,
} from "./fixtures/seed";

test.describe("工作流 03 — AI助手概览", () => {
  test("已配置医生 — 所有区域正常渲染", async ({
    doctorPage,
    doctor,
    patient,
    request,
    steps,
  }) => {
    // Seed: 2 knowledge items, 1 persona rule, 1 completed intake.
    // category must be a valid enum: custom|diagnosis|followup|medication.
    await addKnowledgeText(request, doctor, "高血压头痛需先排除高血压脑病");
    await addKnowledgeText(request, doctor, "回访48小时血压记录");
    await addPersonaRule(request, doctor, "reply_style", "口语化回复，像微信聊天");
    await completePatientIntake(request, patient);

    await doctorPage.goto("/doctor/my-ai");

    // 1.1 — shell
    await expect(doctorPage.getByText("AI助手").first()).toBeVisible();
    // NOTE: Disclaimer "本服务为AI生成内容，结果仅供参考" was removed from
    // MyAIPage in the v2 card-layout redesign. No replacement disclaimer exists.

    await steps.capture(doctorPage, "打开AI助手页面", "页面外壳可见");

    // 2.2 — hero AI name: "XXX的助手"
    const aiNameLocator = doctorPage.getByText(new RegExp(`${doctor.name}.*助手`));
    await expect(aiNameLocator).toBeVisible();
    const aiNameText = await aiNameLocator.textContent();
    expect(aiNameText).not.toContain("医生医生");

    // 2.3 — AI风格 subtitle exists
    await expect(doctorPage.getByText(/AI风格/)).toBeVisible();

    // NOTE: The 3 stat columns (待处理 / 今日完成 / 7天引用) were removed
    // in the v2 card-layout redesign. MyAIPage now shows hero banner +
    // quick-action tiles + 今日关注 + 最近使用.

    // 4 — quick action tiles (no "快捷工具" section header anymore; tiles
    // render directly as labels on the action card)
    await expect(doctorPage.getByText("新建病历")).toBeVisible();
    await expect(doctorPage.getByText("预问诊码")).toBeVisible();

    // 6 — knowledge quick action (section header "我的知识" was removed in
    // the v2 redesign; knowledge is now reached via the "知识库" quick action)
    await expect(doctorPage.getByText("知识库")).toBeVisible();

    await steps.capture(doctorPage, "验证快捷工具和知识区", "快捷工具和我的知识区域可见");

    // 6.4 — relative date must NOT be "-1天前" (BUG-01 gate)
    const bodyText = await doctorPage.locator("body").innerText();
    expect(bodyText).not.toMatch(/-1天前/);
  });

  test("新医生 — 风格空状态渲染", async ({ doctorPage, steps }) => {
    await doctorPage.goto("/doctor/my-ai");

    // Registration auto-seeds 3 knowledge items via preseed_service, so
    // the knowledge section is never truly empty. Only persona is empty.

    await steps.capture(doctorPage, "新医生AI助手页面", "未配置AI风格的初始状态");

    // 5.3 — persona empty hint
    await expect(doctorPage.getByText("设置你的AI风格")).toBeVisible();

    // Knowledge quick action still renders (section header "我的知识" was
    // removed; knowledge is reached via the "知识库" quick action tile)
    await expect(doctorPage.getByText("知识库")).toBeVisible();

    await steps.capture(doctorPage, "验证空状态提示", "显示设置AI风格提示和知识区域");
  });

  test("导航 — 点击入口跳转正确子页面", async ({ doctorPage, steps }) => {
    await doctorPage.goto("/doctor/my-ai");

    await steps.capture(doctorPage, "AI助手页面初始状态", "准备测试导航");

    // Click the subtitle text containing "AI风格" to navigate to persona
    await doctorPage.getByText(/AI风格/).first().click();
    await expect(doctorPage).toHaveURL(/\/doctor\/settings\/persona/);

    await steps.capture(doctorPage, "跳转到AI风格页", "点击AI风格后进入风格设置页");

    await doctorPage.goBack();

    // Click "知识库" quick-action tile to navigate to knowledge management.
    // (The old "管理" link was removed; the knowledge tile is the entry point.)
    await doctorPage.goto("/doctor/my-ai");
    await doctorPage.getByText("知识库").first().click();
    await expect(doctorPage).toHaveURL(/\/doctor\/settings\/knowledge/);

    await steps.capture(doctorPage, "跳转到知识管理页", "点击管理后进入知识列表页");
  });
});
