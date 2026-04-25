/**
 * Patient app smoke gallery — captures viewport-clipped PNGs of every
 * key patient surface into public/wiki/smoke-shots/patient-NN-*.png so
 * the wiki gallery (wiki-smoke-gallery.html) can surface them.
 *
 * Pattern: based on 24-patient-shell.spec.ts — seeds the zustand auth
 * store directly via addInitScript, then stubs every backend endpoint
 * the rendered surface touches with realistic-looking data so renders
 * never show empty / loading states.
 *
 * Mobile viewport (390×844, iPhone 13) inherited from playwright.config.ts.
 *
 * To regenerate the gallery, see:
 *   docs/qa/e2e-guide.md (smoke gallery section)
 *
 * Quick command (assumes vite on :5173, no real backend needed —
 * route stubs intercept before they hit the proxy):
 *
 *   npx playwright test tests/e2e/00-patient-smoke-gallery.spec.ts
 */
import { test } from "@playwright/test";

const SHOTS_DIR = "public/wiki/smoke-shots";

const SEEDED_AUTH = {
  state: {
    token: "seeded-patient-token",
    patientId: "1",
    patientName: "张小明",
    doctorId: "seeded_doctor",
    doctorName: "李医生",
  },
  version: 0,
};

const ME = {
  patient_id: 1,
  patient_name: "张小明",
  doctor_id: "seeded_doctor",
  doctor_name: "李医生",
};

const RECORDS = [
  {
    id: 42,
    record_type: "visit",
    structured: {
      chief_complaint: "头痛 3 天，伴恶心呕吐",
      present_illness:
        "患者 3 天前无明显诱因出现头痛，以前额及双侧颞部为主，呈持续性胀痛，伴恶心，无呕吐。无视物模糊，无肢体活动障碍。睡眠及饮食欠佳。",
      past_history: "高血压病史 5 年，规律服药",
      allergy_history: "否认药物及食物过敏",
    },
    diagnosis_status: "completed",
    status: "completed",
    treatment_plan: {
      medications: [
        { name: "对乙酰氨基酚", dose: "500mg", frequency: "tid" },
        { name: "硝苯地平缓释片", dose: "30mg", frequency: "qd" },
      ],
      follow_up: "1 周后门诊复查血压",
      lifestyle: "低盐低脂饮食，避免熬夜，每日测量血压",
    },
    created_at: "2026-04-20T10:00:00Z",
  },
  {
    id: 41,
    record_type: "interview_summary",
    structured: { chief_complaint: "高血压复诊咨询" },
    created_at: "2026-04-15T08:30:00Z",
  },
  {
    id: 40,
    record_type: "dictation",
    structured: { chief_complaint: "感冒、咽痛 2 天" },
    created_at: "2026-04-10T16:00:00Z",
  },
];

const TASKS = [
  {
    id: 7,
    task_type: "follow_up",
    title: "1 周后复查血压",
    content:
      "请前往社区诊所或自备血压计，每日早晚各测量一次血压，并记录数值。复查时请将记录提供给医生。",
    status: "pending",
    due_at: "2026-04-27T10:00:00Z",
    source_type: "manual",
    created_at: "2026-04-20T10:00:00Z",
    completed_at: null,
    source_record_id: 42,
  },
  {
    id: 6,
    task_type: "general",
    title: "服药提醒：晚餐后服用降压药",
    content: "晚餐后 30 分钟服用硝苯地平缓释片 30mg",
    status: "completed",
    due_at: null,
    source_type: "manual",
    created_at: "2026-04-19T08:00:00Z",
    completed_at: "2026-04-19T20:30:00Z",
    source_record_id: null,
  },
];

const CHAT_MESSAGES = [
  {
    id: 101,
    source: "patient",
    content: "医生您好，我最近头痛比较严重",
    created_at: "2026-04-22T09:30:00Z",
  },
  {
    id: 102,
    source: "ai",
    content:
      "您好！请问头痛持续多久了？是持续性还是阵发性的？是否伴有恶心、视物模糊等症状？",
    created_at: "2026-04-22T09:30:30Z",
  },
  {
    id: 103,
    source: "patient",
    content: "持续 3 天了，还伴有恶心",
    created_at: "2026-04-22T09:31:00Z",
  },
  {
    id: 104,
    source: "doctor",
    content:
      "建议先量一下血压。如果血压偏高，请按时服用降压药并尽快门诊就诊。",
    created_at: "2026-04-22T10:05:00Z",
  },
];

test.describe("patient smoke gallery", () => {
  test.beforeEach(async ({ page }) => {
    // Seed auth + onboarding-done flags before any script runs.
    await page.addInitScript((auth) => {
      localStorage.setItem("patient-portal-auth", JSON.stringify(auth));
      // Both keys needed: PatientPage reads patient_portal_patient_id from
      // legacy localStorage, then constructs patient_onboarding_done_<id>.
      localStorage.setItem("patient_portal_patient_id", "1");
      localStorage.setItem("patient_onboarding_done_1", "1");
    }, SEEDED_AUTH);

    // Stub every endpoint touched by patient surfaces with realistic data.
    await page.route("**/api/patient/me", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(ME),
      }),
    );
    await page.route("**/api/patient/records", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(RECORDS),
      }),
    );
    await page.route(/\/api\/patient\/records\/\d+$/, (route) => {
      const url = route.request().url();
      const m = url.match(/\/records\/(\d+)/);
      const id = m ? Number(m[1]) : null;
      const rec = RECORDS.find((r) => r.id === id) || RECORDS[0];
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(rec),
      });
    });
    await page.route("**/api/patient/tasks", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(TASKS),
      }),
    );
    await page.route(/\/api\/patient\/tasks\/\d+$/, (route) => {
      const url = route.request().url();
      const m = url.match(/\/tasks\/(\d+)/);
      const id = m ? Number(m[1]) : null;
      const task = TASKS.find((t) => t.id === id) || TASKS[0];
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(task),
      });
    });
    await page.route(/\/api\/patient\/chat\/messages.*/, (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(CHAT_MESSAGES),
      }),
    );
  });

  test("01 — chat tab", async ({ page }) => {
    await page.goto("/patient/chat");
    await page.waitForSelector("text=新问诊");
    await page.waitForSelector("text=查看病历");
    // Wait for the welcome / first AI bubble to render.
    await page.waitForSelector("text=AI助手");
    await page.waitForTimeout(400);
    await page.screenshot({
      path: `${SHOTS_DIR}/patient-01-chat.png`,
      fullPage: false,
    });
  });

  test("02 — records timeline (unified)", async ({ page }) => {
    // As of 2026-04-24, RecordsTab is a single chronological timeline —
    // view toggle and type filter were dropped (YAGNI for sub-5-record audience).
    await page.goto("/patient/records");
    await page.waitForSelector("text=门诊记录");
    await page.waitForSelector("text=预问诊");
    // Month section header is rendered by groupByMonth → "2026年4月".
    await page.waitForSelector("text=/2026年.月/");
    await page.waitForTimeout(300);
    await page.screenshot({
      path: `${SHOTS_DIR}/patient-02-records-timeline.png`,
      fullPage: false,
    });
  });

  test("04 — record detail", async ({ page }) => {
    await page.goto("/patient/records/42");
    await page.waitForSelector("text=病历详情");
    await page.waitForSelector("text=主诉");
    await page.waitForSelector("text=诊断与用药");
    await page.waitForTimeout(300);
    await page.screenshot({
      path: `${SHOTS_DIR}/patient-04-record-detail.png`,
      fullPage: false,
    });
  });

  test("05 — tasks tab", async ({ page }) => {
    await page.goto("/patient/tasks");
    await page.waitForSelector("text=待完成");
    await page.waitForSelector("text=1 周后复查血压");
    await page.waitForTimeout(300);
    await page.screenshot({
      path: `${SHOTS_DIR}/patient-05-tasks.png`,
      fullPage: false,
    });
  });

  test("06 — task detail", async ({ page }) => {
    await page.goto("/patient/tasks/7");
    await page.waitForSelector("text=任务详情");
    await page.waitForSelector("text=1 周后复查血压");
    await page.waitForSelector("text=标记完成");
    await page.waitForTimeout(300);
    await page.screenshot({
      path: `${SHOTS_DIR}/patient-06-task-detail.png`,
      fullPage: false,
    });
  });

  test("07 — my page (profile)", async ({ page }) => {
    await page.goto("/patient/profile");
    await page.waitForSelector("text=我的医生");
    await page.waitForSelector("text=通用");
    await page.waitForSelector("text=退出登录");
    await page.waitForTimeout(300);
    await page.screenshot({
      path: `${SHOTS_DIR}/patient-07-mypage.png`,
      fullPage: false,
    });
  });

  test("08 — font popup open on my page", async ({ page }) => {
    await page.goto("/patient/profile");
    await page.waitForSelector("text=字体大小");
    await page.getByText("字体大小", { exact: true }).click();
    // Popup contains 标准 / 大 / 特大 radios.
    await page.waitForSelector("text=特大");
    await page.waitForTimeout(400);
    await page.screenshot({
      path: `${SHOTS_DIR}/patient-08-font-popup.png`,
      fullPage: false,
    });
  });

  test("09 — about subpage", async ({ page }) => {
    await page.goto("/patient/profile/about");
    await page.waitForSelector("text=应用信息");
    await page.waitForSelector("text=患者助手");
    await page.waitForSelector("text=法律信息");
    await page.waitForTimeout(300);
    await page.screenshot({
      path: `${SHOTS_DIR}/patient-09-about.png`,
      fullPage: false,
    });
  });

  test("10 — privacy subpage", async ({ page }) => {
    await page.goto("/patient/profile/privacy");
    await page.waitForSelector("text=隐私政策");
    // Stable section heading from PrivacyContent.
    await page.waitForSelector("text=一、我们收集的信息");
    await page.waitForTimeout(300);
    await page.screenshot({
      path: `${SHOTS_DIR}/patient-10-privacy.png`,
      fullPage: false,
    });
  });
});
