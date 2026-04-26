/**
 * Workflow 00 — Seed smoke
 *
 * Runs first. Verifies every fixture helper in fixtures/seed.ts against the
 * real backend before any workflow spec tries to use it. The 11 workflow
 * specs depend entirely on seeded state — if any seed helper 404s, every
 * downstream test fails with opaque selector errors. This file catches
 * contract drift at its source.
 *
 * Scope:
 *   - registerDoctor → 2xx, response shape has doctor_id + token
 *   - registerPatient → 2xx, response has patient_id + token
 *   - authenticateDoctorPage → localStorage "doctor-session" blob written
 *   - addKnowledgeText → 2xx
 *   - addPersonaRule → 2xx
 *   - sendPatientMessage → 2xx
 *   - completePatientIntake → returns record_id
 *   - backend /api/health → 2xx (frontend is reachable separately)
 *
 * This is not a UI test. It only hits the backend API and asserts 2xx. If
 * all of these pass the rest of the suite has a fighting chance; if any
 * fail, STOP and fix the fixture/contract before running any workflow spec.
 */
import {
  test,
  expect,
  API_BASE_URL,
  registerDoctor,
  registerPatient,
  authenticateDoctorPage,
} from "./fixtures/doctor-auth";
import {
  addKnowledgeText,
  addPersonaRule,
  sendPatientMessage,
  completePatientIntake,
} from "./fixtures/seed";

test.describe("工作流 00 — 基础冒烟测试", () => {
  test("后端健康检查可达", async ({ request, steps }) => {
    const res = await request.get(`${API_BASE_URL}/healthz`);
    expect(
      res.ok(),
      `backend not reachable at ${API_BASE_URL} — start the server first (see docs/qa/workflows/README.md §shared pre-flight)`,
    ).toBeTruthy();
  });

  test("注册医生返回ID和令牌", async ({ request, steps }) => {
    const doctor = await registerDoctor(request);
    expect(doctor.doctorId, "doctor_id missing in register response").toBeTruthy();
    expect(doctor.token, "token missing in register response").toBeTruthy();
    expect(doctor.name).toBeTruthy();
  });

  test("注册患者返回ID和令牌并关联医生", async ({
    request,
    steps,
  }) => {
    const doctor = await registerDoctor(request);
    const patient = await registerPatient(request, doctor.doctorId);
    expect(patient.patientId).toBeTruthy();
    expect(patient.token).toBeTruthy();
    expect(patient.doctorId).toBe(doctor.doctorId);
    expect(patient.gender).toBe("男");
  });

  test("医生登录写入会话存储", async ({
    page,
    request,
    steps,
  }) => {
    const doctor = await registerDoctor(request);
    await authenticateDoctorPage(page, doctor);

    const session = await page.evaluate(() =>
      localStorage.getItem("doctor-session"),
    );
    expect(session, "doctor-session blob must be set").toBeTruthy();
    const parsed = JSON.parse(session!);
    expect(parsed.state.doctorId).toBe(doctor.doctorId);
    // Login generates a fresh JWT (different iat/exp), so only check truthy.
    expect(parsed.state.accessToken).toBeTruthy();
    expect(parsed.state.doctorName).toBe(doctor.name);

    // Belt-and-braces unified_auth_* keys that App.jsx reads in DEV_MODE.
    const unifiedToken = await page.evaluate(() =>
      localStorage.getItem("unified_auth_token"),
    );
    expect(unifiedToken).toBeTruthy();
  });

  test("添加知识文本接口正常", async ({
    request,
    steps,
  }) => {
    const doctor = await registerDoctor(request);
    const result = await addKnowledgeText(
      request,
      doctor,
      "头痛鉴别要点：高血压患者新发头痛需先排除高血压脑病",
    );
    // Only asserts the call didn't throw — the helper already throws on non-2xx.
    // We do not assert a specific response shape because the backend has evolved.
    expect(result).toBeTruthy();
  });

  test("添加风格规则接口正常", async ({
    request,
    steps,
  }) => {
    const doctor = await registerDoctor(request);
    const result = await addPersonaRule(
      request,
      doctor,
      "reply_style",
      "口语化回复，像微信聊天",
    );
    expect(result).toBeTruthy();
  });

  test("发送患者消息接口正常", async ({
    request,
    steps,
  }) => {
    const doctor = await registerDoctor(request);
    const patient = await registerPatient(request, doctor.doctorId);
    // Helper throws on failure — reaching the assertion is the success signal.
    await sendPatientMessage(request, patient, "医生，我今天血压有点高。");
  });

  test("完成患者问诊返回记录ID", async ({ request, steps }) => {
    const doctor = await registerDoctor(request);
    const patient = await registerPatient(request, doctor.doctorId);
    // Seed a knowledge rule so the intake has context for diagnosis later.
    await addKnowledgeText(
      request,
      doctor,
      "高血压患者头痛需排除高血压脑病与颅内出血",
    );
    const { recordId } = await completePatientIntake(request, patient);
    expect(recordId).toBeTruthy();
  });
});
