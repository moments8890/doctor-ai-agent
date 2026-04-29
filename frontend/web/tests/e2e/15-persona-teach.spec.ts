/**
 * Workflow 15 — Persona teach-by-example
 *
 * Mirrors docs/qa/workflows/15-persona-teach.md.
 *
 * The spec intercepts the teach API endpoint to return canned results,
 * keeping tests deterministic without a live LLM.
 */
import { test, expect } from "./fixtures/doctor-auth";

const TEACH_URL = "**/api/manage/persona/teach?doctor_id=*";

const SAMPLE_REPLY = "你好，根据你描述的症状和检查结果来看，目前血压控制得还不错。建议继续目前的药物方案，同时注意低盐饮食和适当运动。下次复诊我们再看看需不需要调整用药。有任何不舒服随时联系我哦~";

const FAKE_EXTRACTED = [
  { field: "reply_style", text: "温暖亲切，使用语气词" },
  { field: "structure", text: "先肯定现状，再给建议，最后安排复诊" },
  { field: "closing", text: "有任何不舒服随时联系我" },
];

test.describe("工作流 15 — 教AI学偏好", () => {
  test("1. 页面外壳正确渲染", async ({ doctorPage, steps }) => {
    await doctorPage.goto("/doctor/settings/teach");

    // step 1.1 — header
    await expect(doctorPage.getByText("教AI新偏好")).toBeVisible();

    // step 1.2 — instructional text
    await expect(
      doctorPage.getByText(/粘贴一段你满意的回复.*风格偏好.*待确认队列/),
    ).toBeVisible();
    await steps.capture(doctorPage, "教AI页面加载完成");

    // step 1.3 — textarea placeholder
    await expect(
      doctorPage.getByPlaceholder("粘贴一段你满意的回复示例…"),
    ).toBeVisible();

    // step 1.4 — character counter (antd-mobile TextArea showCount renders
    // as "0/2000" without spaces — old "0 / 2000" string is gone).
    await expect(doctorPage.getByText(/0\s*\/\s*2000/)).toBeVisible();

    // step 1.5 — submit button visible but disabled. The page uses an
    // antd-mobile <Button>, which renders a real <button disabled>; query
    // by role and check the disabled attribute (the legacy spec checked
    // AppButton opacity, which no longer applies).
    const submitBtn = doctorPage.getByRole("button", { name: "开始分析" });
    await expect(submitBtn).toBeVisible();
    await expect(submitBtn).toBeDisabled();
    await steps.capture(doctorPage, "验证按钮禁用状态");
  });

  test("2. 输入验证启用/禁用提交按钮", async ({ doctorPage, steps }) => {
    await doctorPage.goto("/doctor/settings/teach");

    const textarea = doctorPage.getByPlaceholder("粘贴一段你满意的回复示例…");
    const submitBtn = doctorPage.getByRole("button", { name: "开始分析" });

    // step 2.1 — spaces only keeps button disabled (source: !text.trim()).
    await textarea.fill("   ");
    await expect(submitBtn).toBeDisabled();

    // step 2.2 — real text enables the button.
    await textarea.fill("你好，这是一段测试回复");
    await expect(submitBtn).toBeEnabled();
    await steps.capture(doctorPage, "输入文本后按钮启用");

    // step 2.2 — counter updates (character count depends on exact text length)
    await expect(doctorPage.getByText(/\d+\s*\/\s*2000/).first()).toBeVisible();

    // step 2.3 — clear text re-disables.
    await textarea.fill("");
    await expect(submitBtn).toBeDisabled();
    await expect(doctorPage.getByText(/0\s*\/\s*2000/)).toBeVisible();
    await steps.capture(doctorPage, "清空后按钮重新禁用");
  });

  test("3. 分析成功显示提取的规则", async ({ doctorPage, steps }) => {
    await doctorPage.route(TEACH_URL, (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ extracted: FAKE_EXTRACTED, count: 3 }),
      }),
    );

    await doctorPage.goto("/doctor/settings/teach");

    const textarea = doctorPage.getByPlaceholder("粘贴一段你满意的回复示例…");
    await textarea.fill(SAMPLE_REPLY);

    const submitBtn = doctorPage.getByText("开始分析", { exact: true });
    await submitBtn.click();

    // step 3.2 — results appear
    await expect(doctorPage.getByText(/发现 3 条偏好.*待确认队列/)).toBeVisible();

    // Each extracted rule visible
    await expect(doctorPage.getByText("温暖亲切，使用语气词")).toBeVisible();
    await expect(doctorPage.getByText("先肯定现状，再给建议，最后安排复诊")).toBeVisible();
    await expect(doctorPage.getByText("有任何不舒服随时联系我").first()).toBeVisible();

    // Field labels visible
    await expect(doctorPage.getByText("回复风格")).toBeVisible();
    await expect(doctorPage.getByText("回复结构")).toBeVisible();
    await expect(doctorPage.getByText("常用结尾语")).toBeVisible();
    await steps.capture(doctorPage, "分析结果显示提取规则");
  });

  test("4. 未发现规则显示兜底提示", async ({ doctorPage, steps }) => {
    await doctorPage.route(TEACH_URL, (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ extracted: [], count: 0 }),
      }),
    );

    await doctorPage.goto("/doctor/settings/teach");

    await doctorPage.getByPlaceholder("粘贴一段你满意的回复示例…").fill("你好");
    await doctorPage.getByText("开始分析", { exact: true }).click();

    // step 4.1 — empty result message
    await expect(
      doctorPage.getByText("未发现明显的风格偏好，请尝试粘贴更完整的回复"),
    ).toBeVisible();
    await steps.capture(doctorPage, "未发现偏好提示");
  });

  test("5. API报错显示错误提示", async ({ doctorPage, steps }) => {
    await doctorPage.route(TEACH_URL, (route) =>
      route.fulfill({ status: 500, body: "Internal Server Error" }),
    );

    await doctorPage.goto("/doctor/settings/teach");

    await doctorPage.getByPlaceholder("粘贴一段你满意的回复示例…").fill(SAMPLE_REPLY);
    await doctorPage.getByText("开始分析", { exact: true }).click();

    // step 5.1 — error message
    await expect(doctorPage.getByText("分析失败，请重试")).toBeVisible();

    // step 5.1 — textarea re-enabled
    await expect(
      doctorPage.getByPlaceholder("粘贴一段你满意的回复示例…"),
    ).toBeEnabled();
    // Button re-enabled (opacity 1)
    await expect(
      doctorPage.getByText("开始分析", { exact: true }),
    ).toHaveCSS("opacity", "1");
    await steps.capture(doctorPage, "API错误后恢复可用");
  });
});
