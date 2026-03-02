# E2E Test Expansion Plan

## Objective

Increase confidence in critical end-to-end behaviors with deterministic integration tests that are stable in CI and meaningful for regression prevention.

## Scope

Add integration coverage for:

1. Task API lifecycle (`list`, `filter`, `complete`)
2. Manage patients grouped view correctness
3. Manage records raw-field payload correctness

## Test Design Principles

- Prefer deterministic DB-seeded setup over LLM-dependent setup for non-LLM flows.
- Use unique `doctor_id` per test (`inttest_*`) to isolate data.
- Assert response structure and key field semantics, not just status codes.
- Keep tests small and independent.

## Planned Cases

### Case 1: Task API roundtrip

- Seed two pending `doctor_tasks` rows for one doctor.
- Call `GET /api/tasks?doctor_id=...` and assert both are returned.
- Complete one task via `PATCH /api/tasks/{id}`.
- Call `GET /api/tasks?doctor_id=...&status=pending` and assert only remaining pending task is returned.

### Case 2: Manage patients grouped categories

- Seed patients for one doctor across:
  - `high_risk`
  - `new`
  - `NULL` category (should map to `uncategorized`)
- Call `GET /api/manage/patients/grouped`.
- Assert group counts and expected fixed bucket behavior.

### Case 3: Manage records raw field payload

- Seed one patient and one medical record with all core fields.
- Call `GET /api/manage/records?doctor_id=...`.
- Assert raw fields exist and values match DB seed:
  - `history_of_present_illness`
  - `past_medical_history`
  - `physical_examination`
  - `auxiliary_examinations`
  - `follow_up_plan`

## Implementation Tasks

1. Add new integration test module:
- `tests/integration/test_manage_tasks_pipeline.py`

2. Add small local DB helper utilities in that test file:
- direct `sqlite3` inserts for deterministic fixtures
- per-test explicit cleanup by `doctor_id` for `doctor_tasks/patients/medical_records`

3. Improve integration cleanup fixture:
- extend `tests/integration/conftest.py` cleanup to include `doctor_tasks` rows for `inttest_%`

## Validation

- Run:
  - `bash tools/test.sh integration`
  - optionally `bash tools/test.sh integration-full`
- Ensure new tests are marked `@pytest.mark.integration` and skipped cleanly when server/Ollama unavailable.

## Exit Criteria

- New integration module merged and green in CI.
- No flakiness observed in at least two consecutive CI runs.
- Tests remain deterministic without depending on LLM output for these API contracts.

## 今日 E2E 场景覆盖（中文）

当前 E2E（集成测试）覆盖分为两类：

1. 医生输入驱动（`tests/integration/test_text_pipeline.py`）
- 单轮输入：包含姓名时，能直接完成结构化并落库
- 缺少姓名的两轮流程：先追问姓名，再用姓名补全并落库
- 急诊语义输入：病历可生成且能持久化
- 稀疏输入防幻觉：未提及治疗时，`treatment_plan` 应为 `null`
- 同名二次就诊：同一患者新增病历，不应重复建患者档案
- 对话查询能力：`查询某患者病历` 与 `所有患者` 的回复内容正确

2. 确定性 API 流程（`tests/integration/test_manage_tasks_pipeline.py`）
- 任务流转：任务列表 -> 完成任务 -> pending 过滤校验
- 患者分组：`/api/manage/patients/grouped` 分组计数正确
- 病历原始字段视图：`/api/manage/records` 返回关键原始字段且值与 DB 一致

补充说明：
- 集成测试依赖运行中的服务与 Ollama，不可用时会自动跳过。
- 测试 DB 路径会优先读取 `.env` 中的 `PATIENTS_DB_PATH`，避免“服务写入路径”与“测试校验路径”不一致。
