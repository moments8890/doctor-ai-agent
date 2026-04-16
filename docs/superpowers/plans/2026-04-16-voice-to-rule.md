# Voice → Rule Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a doctor speak a short clinical rule into the WeChat miniapp, have it transcribed + LLM-extracted, confirm inline, and save to their knowledge base.

**Architecture:** New native miniapp page (mic can't work in web-view) calls a new backend endpoint that bundles ASR + LLM extraction behind one HTTP round-trip. Candidate saves through the existing `POST /api/manage/knowledge` — no DB migration, no write-API changes. React side gets a small bridge helper and a mic button in `AddKnowledgeSubpage`.

**Tech Stack:** Python/FastAPI backend, Tencent Cloud ASR (`16k_zh_medical`), `src/agent/llm.py:structured_call` with Pydantic for the LLM contract, WeChat miniapp native (WXML/WXSS/JS), React 18 + MUI on the webview side.

**Spec:** `docs/superpowers/specs/2026-04-16-voice-to-rule-design.md`

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `src/agent/prompts/voice_to_rule.md` | Create | LLM prompt; strict JSON output contract for `{content, category, error}` |
| `src/channels/web/doctor_dashboard/knowledge_handlers.py` | Modify | Add handler for `POST /api/manage/knowledge/voice-extract` |
| `tests/prompts/cases/voice-to-rule.yaml` | Create | 15–20 eval scenarios for the extraction prompt |
| `tests/integration/test_voice_extract.py` | Create | 6–8 handler integration tests with fixture audio |
| `tests/fixtures/audio/*.mp3` | Create | Small audio fixtures (silence, short rule, long story) |
| `frontend/miniprogram/pages/add-rule/add-rule.js` | Create | Native page logic — state machine, recorder, upload, save |
| `frontend/miniprogram/pages/add-rule/add-rule.wxml` | Create | UI template |
| `frontend/miniprogram/pages/add-rule/add-rule.wxss` | Create | Styles (hardcoded theme hex; see spec) |
| `frontend/miniprogram/pages/add-rule/add-rule.json` | Create | Page config |
| `frontend/miniprogram/app.json` | Modify | Register new page |
| `frontend/miniprogram/app.js` | Modify | Add `wx.getUpdateManager` on launch |
| `frontend/web/src/utils/miniappBridge.js` | Create | `isInMiniapp()` + `openAddRuleVoice()` helpers |
| `frontend/web/src/pages/doctor/subpages/AddKnowledgeSubpage.jsx` | Modify | Delete dead voice scaffold; add mic button wired to bridge |

---

# Phase 1 — Backend

## Task 1: Define the Pydantic response model

**Files:**
- Modify: `src/channels/web/doctor_dashboard/knowledge_handlers.py`

- [ ] **Step 1: Add the Pydantic models at the top of `knowledge_handlers.py` (after existing imports, near the other `BaseModel` classes around line 35)**

```python
from enum import Enum
from typing import Literal

class VoiceExtractError(str, Enum):
    no_rule_found = "no_rule_found"
    multi_rule_detected = "multi_rule_detected"
    audio_unclear = "audio_unclear"
    too_long = "too_long"
    internal = "internal"


class VoiceRuleCandidate(BaseModel):
    content: str
    category: KnowledgeCategory


class VoiceExtractLLMResult(BaseModel):
    """Raw LLM output shape — strict JSON contract enforced via structured_call."""
    content: str | None = None
    category: KnowledgeCategory | None = None
    error: Literal["no_rule_found", "multi_rule_detected"] | None = None


class VoiceExtractResponse(BaseModel):
    """HTTP response shape returned to miniapp."""
    transcript: str
    candidate: VoiceRuleCandidate | None = None
    error: str | None = None
```

- [ ] **Step 2: Commit**

```bash
git add src/channels/web/doctor_dashboard/knowledge_handlers.py
git commit -m "feat(knowledge): add voice-extract Pydantic models"
```

---

## Task 2: Write the extraction prompt

**Files:**
- Create: `src/agent/prompts/voice_to_rule.md`

- [ ] **Step 1: Write the prompt file**

```markdown
# Voice → Rule Extraction

You receive a Chinese voice-memo transcript from a specialist doctor. Your job is to extract AT MOST ONE clinical rule from the transcript and output strict JSON.

## Input

Transcript (ASR output, may contain filler words or minor ASR noise):
{{transcript}}

Doctor specialty (may be empty):
{{specialty}}

## Output

Return a single JSON object with this exact shape:

```json
{
  "content": "<rule text in Chinese>" | null,
  "category": "custom" | "diagnosis" | "followup" | "medication" | null,
  "error": null | "no_rule_found" | "multi_rule_detected"
}
```

On success: `content` is the rule, `category` is one of the four values, `error` is null.
On handled failure: `content` and `category` are null, `error` is one of the two error codes.

### Error codes

- `no_rule_found` — transcript is a story, general observation, or question with no extractable clinical rule.
- `multi_rule_detected` — transcript clearly contains TWO OR MORE distinct clinical rules. Do NOT silently pick one.

### Category guide

- `diagnosis` — rules for diagnosing/assessing conditions (e.g., "当 X 症状出现时，考虑 Y")
- `followup` — rules for follow-up schedules and monitoring (e.g., "术后 X 天复查 Y")
- `medication` — rules for drug choice, dosing, contraindications
- `custom` — anything else (patient communication style, red flags, operational rules)

## Few-shot examples

### Example 1: clean followup rule
Transcript: "前交通动脉瘤术后第二周要关注记忆问题"
Specialty: "神经外科"
Output:
```json
{
  "content": "前交通动脉瘤术后第二周关注患者记忆变化，复诊时询问近期记忆清晰度",
  "category": "followup",
  "error": null
}
```

### Example 2: diagnosis rule with drug context
Transcript: "嗯那个服用抗凝药的患者如果出现新发头痛加重要警惕脑出血"
Specialty: "神经外科"
Output:
```json
{
  "content": "服用抗凝药的患者出现新发头痛或头痛加重时，警惕脑出血，建议立即影像学检查",
  "category": "diagnosis",
  "error": null
}
```

### Example 3: medication rule
Transcript: "阿托伐他汀二十毫克晚上睡前吃"
Specialty: ""
Output:
```json
{
  "content": "阿托伐他汀 20mg 晚上睡前服用",
  "category": "medication",
  "error": null
}
```

### Example 4: long story, no rule
Transcript: "今天遇到一个很有意思的病例啊患者五十多岁男性来的时候就是说头痛我就觉得可能是..."
Specialty: "神经外科"
Output:
```json
{
  "content": null,
  "category": null,
  "error": "no_rule_found"
}
```

### Example 5: multi-rule memo
Transcript: "前交通术后两周看记忆，另外如果患者有高血压要控制收缩压在140以下"
Specialty: "神经外科"
Output:
```json
{
  "content": null,
  "category": null,
  "error": "multi_rule_detected"
}
```

### Example 6: ambiguous (short, barely a rule)
Transcript: "注意观察"
Specialty: ""
Output:
```json
{
  "content": null,
  "category": null,
  "error": "no_rule_found"
}
```

## Constraints

- Output JSON ONLY — no commentary, no markdown fences, no explanation.
- `content` must be in Chinese, clinically precise, ≤500 characters.
- Filter out filler words ("嗯", "那个", "就是说") and ASR noise.
- If in doubt between extracting and rejecting, prefer `no_rule_found`.
- Do NOT invent content not present in the transcript.
```

- [ ] **Step 2: Commit**

```bash
git add src/agent/prompts/voice_to_rule.md
git commit -m "feat(prompts): add voice_to_rule extraction prompt"
```

---

## Task 3: Write prompt eval cases

**Files:**
- Create: `tests/prompts/cases/voice-to-rule.yaml`

- [ ] **Step 1: Write the YAML eval file**

```yaml
# Test cases for voice_to_rule.md
# Prompt: Chinese voice transcript → {content, category, error} JSON

- description: "clean followup rule for neurosurgery"
  options:
    prompts: [voice-to-rule]
  vars:
    transcript: "前交通动脉瘤术后第二周要关注记忆问题"
    specialty: "神经外科"
  assert:
    - type: is-json
    - type: javascript
      value: |
        const o = JSON.parse(output);
        return o.error === null && o.category === 'followup' && o.content && o.content.includes('记忆');

- description: "diagnosis rule with drug context"
  options:
    prompts: [voice-to-rule]
  vars:
    transcript: "嗯那个服用抗凝药的患者如果出现新发头痛加重要警惕脑出血"
    specialty: "神经外科"
  assert:
    - type: is-json
    - type: javascript
      value: |
        const o = JSON.parse(output);
        return o.error === null && o.category === 'diagnosis' && o.content.includes('抗凝');

- description: "medication rule with dosing"
  options:
    prompts: [voice-to-rule]
  vars:
    transcript: "阿托伐他汀二十毫克晚上睡前吃"
    specialty: ""
  assert:
    - type: is-json
    - type: javascript
      value: |
        const o = JSON.parse(output);
        return o.error === null && o.category === 'medication' && o.content.includes('阿托伐他汀') && o.content.includes('20');

- description: "long story no rule → no_rule_found"
  options:
    prompts: [voice-to-rule]
  vars:
    transcript: "今天遇到一个很有意思的病例啊患者五十多岁男性来的时候就是说头痛我就觉得可能是硬膜下血肿然后做了CT确实是但是后来处理得很顺利"
    specialty: "神经外科"
  assert:
    - type: is-json
    - type: javascript
      value: |
        const o = JSON.parse(output);
        return o.error === 'no_rule_found' && o.content === null;

- description: "multi-rule memo → multi_rule_detected, not silently picked"
  options:
    prompts: [voice-to-rule]
  vars:
    transcript: "前交通术后两周看记忆，另外如果患者有高血压要控制收缩压在140以下"
    specialty: "神经外科"
  assert:
    - type: is-json
    - type: javascript
      value: |
        const o = JSON.parse(output);
        return o.error === 'multi_rule_detected' && o.content === null;

- description: "too short / ambiguous → no_rule_found"
  options:
    prompts: [voice-to-rule]
  vars:
    transcript: "注意观察"
    specialty: ""
  assert:
    - type: is-json
    - type: javascript
      value: |
        const o = JSON.parse(output);
        return o.error === 'no_rule_found';

- description: "custom / communication style rule"
  options:
    prompts: [voice-to-rule]
  vars:
    transcript: "回复患者的时候要尽量用大白话不要用太多专业术语"
    specialty: ""
  assert:
    - type: is-json
    - type: javascript
      value: |
        const o = JSON.parse(output);
        return o.error === null && o.category === 'custom';

- description: "red flag as custom rule"
  options:
    prompts: [voice-to-rule]
  vars:
    transcript: "术后患者如果出现瞳孔不等大立刻联系我不管几点"
    specialty: "神经外科"
  assert:
    - type: is-json
    - type: javascript
      value: |
        const o = JSON.parse(output);
        return o.error === null && o.content.includes('瞳孔');

- description: "followup schedule with time window"
  options:
    prompts: [voice-to-rule]
  vars:
    transcript: "开颅术后第一个月每周回访一次之后每个月一次"
    specialty: "神经外科"
  assert:
    - type: is-json
    - type: javascript
      value: |
        const o = JSON.parse(output);
        return o.error === null && o.category === 'followup';

- description: "filler-heavy transcript extracts cleanly"
  options:
    prompts: [voice-to-rule]
  vars:
    transcript: "嗯就是那个呃术后第三天要拆线就这样"
    specialty: ""
  assert:
    - type: is-json
    - type: javascript
      value: |
        const o = JSON.parse(output);
        return o.error === null && !o.content.includes('嗯') && !o.content.includes('呃');

- description: "drug with contraindication"
  options:
    prompts: [voice-to-rule]
  vars:
    transcript: "对磺胺过敏的病人不能用甘露醇要换成呋塞米"
    specialty: ""
  assert:
    - type: is-json
    - type: javascript
      value: |
        const o = JSON.parse(output);
        return o.error === null && o.category === 'medication' && o.content.includes('磺胺');

- description: "question (not a rule) → no_rule_found"
  options:
    prompts: [voice-to-rule]
  vars:
    transcript: "这个病人怎么办啊"
    specialty: ""
  assert:
    - type: is-json
    - type: javascript
      value: |
        const o = JSON.parse(output);
        return o.error === 'no_rule_found';

- description: "empty specialty variable handled"
  options:
    prompts: [voice-to-rule]
  vars:
    transcript: "高血压患者收缩压要控制在140以下"
    specialty: ""
  assert:
    - type: is-json
    - type: javascript
      value: |
        const o = JSON.parse(output);
        return o.error === null;

- description: "output is pure JSON with no markdown fence"
  options:
    prompts: [voice-to-rule]
  vars:
    transcript: "术后第三天拆线"
    specialty: ""
  assert:
    - type: javascript
      value: |
        // Must not wrap JSON in ```json fences
        return !output.trim().startsWith('```');

- description: "diagnosis with threshold"
  options:
    prompts: [voice-to-rule]
  vars:
    transcript: "GCS评分低于八分的要考虑气管插管"
    specialty: "神经外科"
  assert:
    - type: is-json
    - type: javascript
      value: |
        const o = JSON.parse(output);
        return o.error === null && o.category === 'diagnosis' && o.content.includes('GCS');
```

- [ ] **Step 2: Run the eval suite (even though it will likely pass baselines trivially — this verifies the test scaffolding hooks up)**

Run: `/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest tests/prompts/ -k voice_to_rule --rootdir=/Volumes/ORICO/Code/doctor-ai-agent -v`

Expected: tests run (may all pass or some fail depending on provider — failures are useful signal).

- [ ] **Step 3: Commit**

```bash
git add tests/prompts/cases/voice-to-rule.yaml
git commit -m "test(prompts): add voice-to-rule eval cases"
```

---

## Task 4: Build the extraction function

**Files:**
- Modify: `src/channels/web/doctor_dashboard/knowledge_handlers.py`
- Test: `tests/core/test_voice_extraction.py`

- [ ] **Step 1: Write the failing unit test**

Create `tests/core/test_voice_extraction.py`:

```python
"""Unit tests for voice→rule extraction helper (mocks the LLM)."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch

from channels.web.doctor_dashboard.knowledge_handlers import (
    VoiceExtractLLMResult,
    extract_rule_from_transcript,
)
from db.models.doctor import KnowledgeCategory


@pytest.mark.asyncio
async def test_extract_returns_candidate_on_clean_transcript():
    fake_llm_result = VoiceExtractLLMResult(
        content="术后第二周关注记忆变化",
        category=KnowledgeCategory.followup,
        error=None,
    )
    with patch(
        "channels.web.doctor_dashboard.knowledge_handlers._call_voice_extract_llm",
        new=AsyncMock(return_value=fake_llm_result),
    ):
        result = await extract_rule_from_transcript(
            transcript="前交通动脉瘤术后第二周要关注记忆问题",
            specialty="神经外科",
        )
    assert result.error is None
    assert result.content == "术后第二周关注记忆变化"
    assert result.category == KnowledgeCategory.followup


@pytest.mark.asyncio
async def test_extract_propagates_no_rule_error():
    fake = VoiceExtractLLMResult(content=None, category=None, error="no_rule_found")
    with patch(
        "channels.web.doctor_dashboard.knowledge_handlers._call_voice_extract_llm",
        new=AsyncMock(return_value=fake),
    ):
        result = await extract_rule_from_transcript(transcript="一段闲聊", specialty="")
    assert result.error == "no_rule_found"
    assert result.content is None


@pytest.mark.asyncio
async def test_extract_propagates_multi_rule_error():
    fake = VoiceExtractLLMResult(content=None, category=None, error="multi_rule_detected")
    with patch(
        "channels.web.doctor_dashboard.knowledge_handlers._call_voice_extract_llm",
        new=AsyncMock(return_value=fake),
    ):
        result = await extract_rule_from_transcript(transcript="两条规则", specialty="")
    assert result.error == "multi_rule_detected"


@pytest.mark.asyncio
async def test_extract_handles_empty_transcript():
    # Empty transcript bypasses LLM and returns audio_unclear sentinel
    result = await extract_rule_from_transcript(transcript="", specialty="")
    assert result.error == "audio_unclear"
    assert result.content is None
    assert result.category is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest tests/core/test_voice_extraction.py --rootdir=/Volumes/ORICO/Code/doctor-ai-agent -v`

Expected: `ImportError: cannot import name 'extract_rule_from_transcript'` or similar.

- [ ] **Step 3: Implement the extraction function in `knowledge_handlers.py`**

Add below the Pydantic models from Task 1:

```python
import pathlib as _pathlib

from agent.llm import structured_call
from infra.llm.client import load_prompt

_VOICE_PROMPT_PATH = (
    _pathlib.Path(__file__).resolve().parents[4]
    / "src" / "agent" / "prompts" / "voice_to_rule.md"
)


async def _call_voice_extract_llm(
    transcript: str,
    specialty: str,
) -> VoiceExtractLLMResult:
    """Call the LLM with voice_to_rule prompt. Returns structured result."""
    prompt_template = _VOICE_PROMPT_PATH.read_text(encoding="utf-8")
    filled = prompt_template.replace(
        "{{transcript}}", transcript
    ).replace("{{specialty}}", specialty or "")
    return await structured_call(
        messages=[{"role": "user", "content": filled}],
        response_model=VoiceExtractLLMResult,
        op_name="voice_to_rule",
        env_var="ROUTING_LLM",
        temperature=0.1,
        max_tokens=600,
    )


async def extract_rule_from_transcript(
    transcript: str,
    specialty: str,
) -> VoiceExtractResponse:
    """Extract a candidate rule from an ASR transcript.

    Returns VoiceExtractResponse with one of:
      - candidate populated, error=None (success)
      - candidate=None, error="audio_unclear" (empty transcript)
      - candidate=None, error="no_rule_found" | "multi_rule_detected"
    """
    if not transcript.strip():
        return VoiceExtractResponse(
            transcript="",
            candidate=None,
            error="audio_unclear",
        )

    llm_result = await _call_voice_extract_llm(transcript, specialty)

    if llm_result.error:
        return VoiceExtractResponse(
            transcript=transcript,
            candidate=None,
            error=llm_result.error,
        )

    if llm_result.content and llm_result.category:
        return VoiceExtractResponse(
            transcript=transcript,
            candidate=VoiceRuleCandidate(
                content=llm_result.content,
                category=llm_result.category,
            ),
            error=None,
        )

    # LLM returned neither candidate nor error — treat as no-rule
    return VoiceExtractResponse(
        transcript=transcript,
        candidate=None,
        error="no_rule_found",
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest tests/core/test_voice_extraction.py --rootdir=/Volumes/ORICO/Code/doctor-ai-agent -v`

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/channels/web/doctor_dashboard/knowledge_handlers.py tests/core/test_voice_extraction.py
git commit -m "feat(knowledge): voice transcript → rule candidate extraction"
```

---

## Task 5: Build the FastAPI handler

**Files:**
- Modify: `src/channels/web/doctor_dashboard/knowledge_handlers.py`

- [ ] **Step 1: Add the route handler below the existing knowledge routes**

```python
from services.asr.provider import transcribe_audio_bytes, get_asr_provider, ASRProvider


_MAX_AUDIO_BYTES = 10 * 1024 * 1024  # 10MB — longer than 60s at 96kbps


@router.post("/api/manage/knowledge/voice-extract")
async def voice_extract(
    file: UploadFile = File(...),
    doctor_id: str = Query(...),
    authorization: Optional[str] = Header(default=None),
    session: AsyncSession = Depends(get_db),
):
    """Receive audio from miniapp, run ASR + LLM extract, return candidate."""
    # Mirror /api/transcribe: fail fast if ASR provider is not configured
    if get_asr_provider() == ASRProvider.browser:
        raise HTTPException(
            400,
            "ASR provider not configured on server (ASR_PROVIDER=browser).",
        )

    resolved = _resolve_ui_doctor_id(doctor_id, authorization)

    # Read audio bytes; enforce size cap
    audio_bytes = await file.read()
    if len(audio_bytes) == 0:
        return VoiceExtractResponse(
            transcript="",
            candidate=None,
            error="audio_unclear",
        )
    if len(audio_bytes) > _MAX_AUDIO_BYTES:
        return VoiceExtractResponse(
            transcript="",
            candidate=None,
            error="too_long",
        )

    # 1. ASR (shared service module — same call site as /api/transcribe)
    try:
        transcript = await transcribe_audio_bytes(audio_bytes, filename=file.filename or "audio.mp3")
    except Exception:
        raise HTTPException(502, "ASR provider error")

    # 2. Fetch doctor specialty (nullable) for prompt context
    specialty = await _get_doctor_specialty(session, resolved) or ""

    # 3. Extract via LLM
    try:
        result = await extract_rule_from_transcript(transcript=transcript, specialty=specialty)
    except Exception:
        raise HTTPException(502, "Extraction error")

    return result


async def _get_doctor_specialty(session: AsyncSession, doctor_id: str) -> str | None:
    from sqlalchemy import select
    from db.models.doctor import Doctor

    stmt = select(Doctor.specialty).where(Doctor.id == doctor_id)
    row = (await session.execute(stmt)).scalar_one_or_none()
    return row
```

- [ ] **Step 2: Commit**

```bash
git add src/channels/web/doctor_dashboard/knowledge_handlers.py
git commit -m "feat(api): POST /api/manage/knowledge/voice-extract handler"
```

---

## Task 6: Integration tests for the handler

**Files:**
- Create: `tests/integration/test_voice_extract.py`
- Create: `tests/fixtures/audio/silence_1s.mp3` (near-silent 1-second MP3, hand-crafted or via `ffmpeg -f lavfi -i anullsrc -t 1 -ar 16000 -ac 1 tests/fixtures/audio/silence_1s.mp3`)
- Create: `tests/fixtures/audio/short_tone.mp3` (a 3-second tone — `ffmpeg -f lavfi -i "sine=frequency=440:duration=3" -ar 16000 -ac 1 tests/fixtures/audio/short_tone.mp3`)

- [ ] **Step 1: Generate audio fixtures**

```bash
mkdir -p tests/fixtures/audio
ffmpeg -f lavfi -i anullsrc=channel_layout=mono:sample_rate=16000 -t 1 -c:a libmp3lame -b:a 96k tests/fixtures/audio/silence_1s.mp3 -y
ffmpeg -f lavfi -i "sine=frequency=440:duration=3" -ar 16000 -ac 1 -c:a libmp3lame -b:a 96k tests/fixtures/audio/short_tone.mp3 -y
```

Expected: two files exist, each <50KB.

- [ ] **Step 2: Write failing integration tests**

```python
"""Integration tests for POST /api/manage/knowledge/voice-extract."""
from __future__ import annotations

import pathlib
import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient


FIXTURES = pathlib.Path(__file__).parent.parent / "fixtures" / "audio"


@pytest.mark.asyncio
async def test_voice_extract_empty_file(async_client: AsyncClient, authed_doctor_id: str):
    """Empty upload returns audio_unclear."""
    files = {"file": ("empty.mp3", b"", "audio/mpeg")}
    resp = await async_client.post(
        f"/api/manage/knowledge/voice-extract?doctor_id={authed_doctor_id}",
        files=files,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["error"] == "audio_unclear"
    assert body["candidate"] is None


@pytest.mark.asyncio
async def test_voice_extract_happy_path(async_client: AsyncClient, authed_doctor_id: str):
    """Valid audio → valid transcript → valid candidate returned."""
    audio = (FIXTURES / "short_tone.mp3").read_bytes()

    with patch(
        "services.asr.provider.transcribe_audio_bytes",
        new=AsyncMock(return_value="术后第三天拆线"),
    ), patch(
        "channels.web.doctor_dashboard.knowledge_handlers._call_voice_extract_llm",
        new=AsyncMock(return_value=type("R", (), {
            "content": "术后第三天拆线",
            "category": "followup",
            "error": None,
        })()),
    ):
        resp = await async_client.post(
            f"/api/manage/knowledge/voice-extract?doctor_id={authed_doctor_id}",
            files={"file": ("rec.mp3", audio, "audio/mpeg")},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["error"] is None
    assert body["candidate"]["content"] == "术后第三天拆线"
    assert body["candidate"]["category"] == "followup"


@pytest.mark.asyncio
async def test_voice_extract_no_rule_found(async_client: AsyncClient, authed_doctor_id: str):
    """Transcript produced but LLM returns no_rule_found."""
    audio = (FIXTURES / "short_tone.mp3").read_bytes()

    with patch(
        "services.asr.provider.transcribe_audio_bytes",
        new=AsyncMock(return_value="今天天气不错"),
    ), patch(
        "channels.web.doctor_dashboard.knowledge_handlers._call_voice_extract_llm",
        new=AsyncMock(return_value=type("R", (), {
            "content": None, "category": None, "error": "no_rule_found",
        })()),
    ):
        resp = await async_client.post(
            f"/api/manage/knowledge/voice-extract?doctor_id={authed_doctor_id}",
            files={"file": ("rec.mp3", audio, "audio/mpeg")},
        )
    assert resp.status_code == 200
    assert resp.json()["error"] == "no_rule_found"


@pytest.mark.asyncio
async def test_voice_extract_multi_rule(async_client: AsyncClient, authed_doctor_id: str):
    """Multi-rule transcript produces multi_rule_detected, not silent pick."""
    audio = (FIXTURES / "short_tone.mp3").read_bytes()

    with patch(
        "services.asr.provider.transcribe_audio_bytes",
        new=AsyncMock(return_value="规则一 规则二"),
    ), patch(
        "channels.web.doctor_dashboard.knowledge_handlers._call_voice_extract_llm",
        new=AsyncMock(return_value=type("R", (), {
            "content": None, "category": None, "error": "multi_rule_detected",
        })()),
    ):
        resp = await async_client.post(
            f"/api/manage/knowledge/voice-extract?doctor_id={authed_doctor_id}",
            files={"file": ("rec.mp3", audio, "audio/mpeg")},
        )
    assert resp.status_code == 200
    assert resp.json()["error"] == "multi_rule_detected"


@pytest.mark.asyncio
async def test_voice_extract_oversize_returns_too_long(async_client: AsyncClient, authed_doctor_id: str):
    big = b"\x00" * (11 * 1024 * 1024)  # 11MB — over cap
    resp = await async_client.post(
        f"/api/manage/knowledge/voice-extract?doctor_id={authed_doctor_id}",
        files={"file": ("big.mp3", big, "audio/mpeg")},
    )
    assert resp.status_code == 200
    assert resp.json()["error"] == "too_long"


@pytest.mark.asyncio
async def test_voice_extract_asr_failure_returns_502(async_client: AsyncClient, authed_doctor_id: str):
    audio = (FIXTURES / "short_tone.mp3").read_bytes()
    with patch(
        "services.asr.provider.transcribe_audio_bytes",
        new=AsyncMock(side_effect=RuntimeError("tencent down")),
    ):
        resp = await async_client.post(
            f"/api/manage/knowledge/voice-extract?doctor_id={authed_doctor_id}",
            files={"file": ("rec.mp3", audio, "audio/mpeg")},
        )
    assert resp.status_code == 502
```

- [ ] **Step 3: Run tests to verify they pass**

Run: `/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest tests/integration/test_voice_extract.py --rootdir=/Volumes/ORICO/Code/doctor-ai-agent -v`

Expected: 6 passed. If `async_client` / `authed_doctor_id` fixtures don't already exist in `tests/integration/conftest.py`, check existing tests like `test_patient_chat_llm_e2e.py` for the fixture pattern and add them as needed.

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_voice_extract.py tests/fixtures/audio/
git commit -m "test(integration): voice-extract handler coverage"
```

---

# Phase 2 — Miniapp Native Page

> These tasks have no automated test layer (miniapp native is manual-only per spec). Each task ends with "verify in WeChat DevTools" + real-device note before commit.

## Task 7: Native page scaffold

**Files:**
- Create: `frontend/miniprogram/pages/add-rule/add-rule.js`
- Create: `frontend/miniprogram/pages/add-rule/add-rule.wxml`
- Create: `frontend/miniprogram/pages/add-rule/add-rule.wxss`
- Create: `frontend/miniprogram/pages/add-rule/add-rule.json`
- Modify: `frontend/miniprogram/app.json`

- [ ] **Step 1: Write `add-rule.json`**

```json
{
  "navigationBarTitleText": "语音添加规则",
  "navigationBarBackgroundColor": "#ffffff",
  "navigationBarTextStyle": "black",
  "backgroundColor": "#f7f7f7"
}
```

- [ ] **Step 2: Write `add-rule.wxss`**

```css
.page {
  min-height: 100vh;
  background: #f7f7f7;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 48rpx 32rpx;
  box-sizing: border-box;
}

.hint {
  color: #8a8a8a;
  font-size: 28rpx;
  text-align: center;
  max-width: 560rpx;
  margin: 32rpx 0 48rpx;
  line-height: 1.6;
}

.mic-btn {
  width: 240rpx;
  height: 240rpx;
  border-radius: 50%;
  background: #07C160;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 8rpx 24rpx rgba(7, 193, 96, 0.25);
}

.mic-btn.recording {
  background: #ff4d4f;
  transform: scale(1.05);
}

.mic-icon {
  color: #ffffff;
  font-size: 88rpx;
}

.timer {
  color: #8a8a8a;
  font-size: 32rpx;
  margin-top: 32rpx;
  font-variant-numeric: tabular-nums;
}

.label {
  color: #8a8a8a;
  font-size: 26rpx;
  margin-top: 16rpx;
}

.card {
  background: #ffffff;
  border-radius: 16rpx;
  padding: 32rpx;
  margin-top: 32rpx;
  width: 100%;
  box-shadow: 0 2rpx 12rpx rgba(0, 0, 0, 0.04);
}

.badge {
  display: inline-block;
  padding: 4rpx 16rpx;
  border-radius: 999rpx;
  font-size: 24rpx;
  margin-bottom: 16rpx;
}
.badge-custom { background: #f0f0f0; color: #555; }
.badge-diagnosis { background: #e6f4ff; color: #1677ff; }
.badge-followup { background: #e8f5e9; color: #07C160; }
.badge-medication { background: #fff7e6; color: #fa8c16; }

.content {
  color: #1a1a1a;
  font-size: 32rpx;
  line-height: 1.6;
  margin-bottom: 32rpx;
}

.btn-row {
  display: flex;
  gap: 16rpx;
}

.btn {
  flex: 1;
  height: 80rpx;
  border-radius: 12rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 30rpx;
}

.btn-primary { background: #07C160; color: #ffffff; }
.btn-secondary { background: #ffffff; color: #333333; border: 2rpx solid #e0e0e0; }
.btn-tertiary { background: transparent; color: #8a8a8a; }

.transcript {
  margin-top: 24rpx;
  padding-top: 24rpx;
  border-top: 1rpx solid #f0f0f0;
  color: #8a8a8a;
  font-size: 26rpx;
}

.error-msg {
  color: #333;
  font-size: 30rpx;
  margin: 48rpx 0;
  text-align: center;
}
```

- [ ] **Step 3: Write initial `add-rule.wxml` with idle state only**

```xml
<view class="page">
  <!-- idle state -->
  <view wx:if="{{state === 'idle'}}" class="mic-btn" bindtouchstart="onMicPressStart" bindtouchend="onMicPressEnd">
    <text class="mic-icon">🎙</text>
  </view>
  <view wx:if="{{state === 'idle'}}" class="hint">长按说话，例如：{{hintText}}</view>
  <view wx:if="{{state === 'idle'}}" class="label">松开结束</view>
</view>
```

- [ ] **Step 4: Write `add-rule.js` with initial state**

```javascript
// frontend/miniprogram/pages/add-rule/add-rule.js
const config = require('../../config.js');

Page({
  data: {
    state: 'idle', // idle | recording | processing | candidate | error | perm_denied | saving
    hintText: '前交通动脉瘤术后第二周要关注记忆问题',
    elapsed: 0,
    transcript: '',
    candidate: null,
    errorCode: null,
  },

  onMicPressStart() {
    // TODO next task: start recording with permission handling
    console.log('press start');
  },

  onMicPressEnd() {
    console.log('press end');
  },
});
```

- [ ] **Step 5: Register the page in `app.json`**

Open `frontend/miniprogram/app.json` and add `"pages/add-rule/add-rule"` to the `"pages"` array. Example:

```diff
 {
   "pages": [
     "pages/login/login",
     "pages/doctor/doctor",
     "pages/voice/voice",
-    "pages/voice-test/voice-test"
+    "pages/voice-test/voice-test",
+    "pages/add-rule/add-rule"
   ],
   ...
 }
```

- [ ] **Step 6: Verify in WeChat DevTools**

Open WeChat DevTools, compile, and manually navigate to `/pages/add-rule/add-rule` via the "Navigate" tab. Confirm the page loads with the mic button visible and hint text.

- [ ] **Step 7: Commit**

```bash
git add frontend/miniprogram/pages/add-rule frontend/miniprogram/app.json
git commit -m "feat(miniapp): scaffold native add-rule page (idle state)"
```

---

## Task 8: Recording state + `wx.getRecorderManager`

**Files:**
- Modify: `frontend/miniprogram/pages/add-rule/add-rule.js`
- Modify: `frontend/miniprogram/pages/add-rule/add-rule.wxml`

- [ ] **Step 1: Update `add-rule.js` to drive recording**

Replace the existing `Page({...})` body:

```javascript
const config = require('../../config.js');

const RECORDER_OPTIONS = {
  duration: 60000,          // hard cap 60s
  sampleRate: 16000,
  numberOfChannels: 1,
  encodeBitRate: 96000,
  format: 'mp3',
};

const MIN_RECORDING_MS = 1000;

Page({
  data: {
    state: 'idle',
    hintText: '前交通动脉瘤术后第二周要关注记忆问题',
    elapsed: 0,
    transcript: '',
    candidate: null,
    errorCode: null,
  },

  onLoad() {
    this.recorderManager = wx.getRecorderManager();
    this._recordStartTs = 0;
    this._timerHandle = null;

    this.recorderManager.onStart(() => {
      this._recordStartTs = Date.now();
      this.setData({ state: 'recording', elapsed: 0 });
      this._timerHandle = setInterval(() => {
        this.setData({ elapsed: Math.floor((Date.now() - this._recordStartTs) / 1000) });
      }, 250);
    });

    this.recorderManager.onStop((res) => {
      if (this._timerHandle) {
        clearInterval(this._timerHandle);
        this._timerHandle = null;
      }
      const duration = Date.now() - this._recordStartTs;
      if (duration < MIN_RECORDING_MS) {
        // discard too-short recording
        this.setData({ state: 'idle' });
        return;
      }
      this._handleRecordingFinished(res.tempFilePath);
    });

    this.recorderManager.onError((err) => {
      console.warn('recorder error', err);
      this.setData({ state: 'error', errorCode: 'internal' });
    });
  },

  onUnload() {
    if (this._timerHandle) clearInterval(this._timerHandle);
  },

  onHide() {
    // app backgrounded mid-recording — stop and discard
    if (this.data.state === 'recording') {
      try { this.recorderManager.stop(); } catch (_) {}
      this.setData({ state: 'idle' });
    }
  },

  onMicPressStart() {
    wx.authorize({
      scope: 'scope.record',
      success: () => this.recorderManager.start(RECORDER_OPTIONS),
      fail: () => this.setData({ state: 'perm_denied' }),
    });
  },

  onMicPressEnd() {
    if (this.data.state === 'recording') {
      this.recorderManager.stop();
    }
  },

  _handleRecordingFinished(tempFilePath) {
    this.setData({ state: 'processing' });
    // next task: upload the file
  },

  onOpenSetting() {
    wx.openSetting({
      success: (res) => {
        if (res.authSetting['scope.record']) {
          this.setData({ state: 'idle' });
        }
      },
    });
  },

  onCancel() {
    wx.navigateBack();
  },
});
```

- [ ] **Step 2: Update `add-rule.wxml` for the new states**

Replace contents:

```xml
<view class="page">
  <!-- idle -->
  <view wx:if="{{state === 'idle'}}">
    <view class="mic-btn" bindtouchstart="onMicPressStart" bindtouchend="onMicPressEnd">
      <text class="mic-icon">🎙</text>
    </view>
    <view class="hint">长按说话，例如：{{hintText}}</view>
    <view class="label">松开结束</view>
  </view>

  <!-- recording -->
  <view wx:if="{{state === 'recording'}}">
    <view class="mic-btn recording" bindtouchend="onMicPressEnd">
      <text class="mic-icon">🎙</text>
    </view>
    <view class="timer">{{elapsed}}s</view>
    <view class="label">松开结束</view>
  </view>

  <!-- processing -->
  <view wx:if="{{state === 'processing'}}">
    <view class="hint">正在识别…</view>
  </view>

  <!-- perm_denied -->
  <view wx:if="{{state === 'perm_denied'}}">
    <view class="error-msg">需要录音权限才能使用此功能</view>
    <view class="btn-row">
      <view class="btn btn-primary" bindtap="onOpenSetting">去设置</view>
      <view class="btn btn-secondary" bindtap="onCancel">取消</view>
    </view>
  </view>
</view>
```

- [ ] **Step 3: Verify in WeChat DevTools + real device**

- In DevTools, open the page, press-and-hold the mic — timer should tick up; release → state "processing" stays (upload not wired yet).
- On first launch of a real device, pressing mic should prompt WeChat's permission dialog. Deny → state transitions to `perm_denied`. Tap "去设置" opens system settings.

- [ ] **Step 4: Commit**

```bash
git add frontend/miniprogram/pages/add-rule
git commit -m "feat(miniapp): recording + permission flow for add-rule page"
```

---

## Task 9: Upload + response handling

**Files:**
- Modify: `frontend/miniprogram/pages/add-rule/add-rule.js`
- Modify: `frontend/miniprogram/pages/add-rule/add-rule.wxml`

- [ ] **Step 1: Implement upload in `_handleRecordingFinished` and add candidate + error rendering**

Replace the placeholder `_handleRecordingFinished` and add new handlers:

```javascript
_handleRecordingFinished(tempFilePath) {
  this.setData({ state: 'processing', uploadStart: Date.now() });

  const token = wx.getStorageSync('token') || '';
  const doctorId = wx.getStorageSync('doctorId') || '';

  wx.uploadFile({
    url: `${config.apiBase}/api/manage/knowledge/voice-extract?doctor_id=${encodeURIComponent(doctorId)}`,
    filePath: tempFilePath,
    name: 'file',
    header: {
      'Authorization': `Bearer ${token}`,
    },
    timeout: 15000,
    success: (res) => this._onExtractResponse(res),
    fail: () => this.setData({ state: 'error', errorCode: 'network' }),
  });
},

_onExtractResponse(res) {
  if (res.statusCode !== 200) {
    this.setData({ state: 'error', errorCode: 'network' });
    return;
  }
  let body;
  try {
    body = JSON.parse(res.data);
  } catch (_) {
    this.setData({ state: 'error', errorCode: 'internal' });
    return;
  }
  if (body.error) {
    this.setData({
      state: 'error',
      errorCode: body.error,
      transcript: body.transcript || '',
    });
    return;
  }
  if (body.candidate) {
    this.setData({
      state: 'candidate',
      candidate: body.candidate,
      transcript: body.transcript || '',
    });
    return;
  }
  this.setData({ state: 'error', errorCode: 'internal' });
},

onReRecord() {
  this.setData({ state: 'idle', candidate: null, errorCode: null, transcript: '' });
},
```

- [ ] **Step 2: Add category-label mapping helper at top of the file**

Add after `const RECORDER_OPTIONS = {...};`:

```javascript
const CATEGORY_META = {
  custom:     { label: '自定义', badgeClass: 'badge-custom' },
  diagnosis:  { label: '诊断',   badgeClass: 'badge-diagnosis' },
  followup:   { label: '随访',   badgeClass: 'badge-followup' },
  medication: { label: '用药',   badgeClass: 'badge-medication' },
};

function categoryMeta(key) {
  return CATEGORY_META[key] || CATEGORY_META.custom;
}
```

And inside `Page({...})` as a method:

```javascript
_decorate(candidate) {
  if (!candidate) return candidate;
  const meta = categoryMeta(candidate.category);
  return { ...candidate, _label: meta.label, _badgeClass: meta.badgeClass };
},
```

Then in `_onExtractResponse`, replace the candidate setData block:

```javascript
if (body.candidate) {
  this.setData({
    state: 'candidate',
    candidate: this._decorate(body.candidate),
    transcript: body.transcript || '',
  });
  return;
}
```

- [ ] **Step 3: Update `add-rule.wxml` to render candidate + error states**

Add these blocks before the closing `</view>`:

```xml
  <!-- candidate -->
  <view wx:if="{{state === 'candidate'}}" class="card">
    <view class="badge {{candidate._badgeClass}}">{{candidate._label}}</view>
    <view class="content">{{candidate.content}}</view>
    <view class="btn-row">
      <view class="btn btn-primary" bindtap="onSave">保存</view>
      <view class="btn btn-secondary" bindtap="onReRecord">重说</view>
    </view>
    <view wx:if="{{transcript}}" class="transcript">原话：{{transcript}}</view>
  </view>

  <!-- error -->
  <view wx:if="{{state === 'error'}}">
    <view class="error-msg">{{errorCopy[errorCode] || '出错了，请重试'}}</view>
    <view class="btn-row">
      <view class="btn btn-primary" bindtap="onReRecord">重说</view>
      <view class="btn btn-secondary" bindtap="onCancel">取消</view>
    </view>
    <view wx:if="{{transcript}}" class="transcript">原话：{{transcript}}</view>
  </view>
```

Add `errorCopy` to `data`:

```javascript
data: {
  state: 'idle',
  hintText: '前交通动脉瘤术后第二周要关注记忆问题',
  elapsed: 0,
  transcript: '',
  candidate: null,
  errorCode: null,
  errorCopy: {
    audio_unclear: '没听清楚，请靠近麦克风再说一次',
    no_rule_found: '没找到明确的规则。试试说：「当 X 时，要 Y」',
    multi_rule_detected: '听起来像多条规则，请一次说一条',
    too_long: '录音超过 1 分钟，请分条说明',
    network: '网络异常，请重试',
    rate_limited: '今日额度已用完，请明天再试',
    internal: '出错了，请重试',
  },
},
```

- [ ] **Step 4: Verify end-to-end with backend running**

Start backend (`./cli.py start --host 0.0.0.0 --provider groq` or similar), open the page in WeChat DevTools, record a short Chinese rule, observe:
- Processing spinner appears
- Candidate card appears with content + category badge
- "查看原话" section shows the transcript
- "重说" returns to idle; "保存" not yet wired (next task)

- [ ] **Step 5: Commit**

```bash
git add frontend/miniprogram/pages/add-rule
git commit -m "feat(miniapp): upload audio + render candidate/error for add-rule"
```

---

## Task 10: Save candidate + navigateBack

**Files:**
- Modify: `frontend/miniprogram/pages/add-rule/add-rule.js`
- Modify: `frontend/miniprogram/pages/add-rule/add-rule.wxml`

- [ ] **Step 1: Add save handler to `add-rule.js`**

```javascript
onSave() {
  if (!this.data.candidate) return;
  this.setData({ state: 'saving' });

  const token = wx.getStorageSync('token') || '';
  const doctorId = wx.getStorageSync('doctorId') || '';

  wx.request({
    url: `${config.apiBase}/api/manage/knowledge?doctor_id=${encodeURIComponent(doctorId)}`,
    method: 'POST',
    header: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    data: {
      content: this.data.candidate.content,
      category: this.data.candidate.category,
    },
    timeout: 10000,
    success: (res) => {
      if (res.statusCode === 200 && res.data && res.data.status === 'ok') {
        wx.showToast({ title: '已保存', icon: 'success', duration: 1500 });
        setTimeout(() => wx.navigateBack(), 1500);
      } else {
        wx.showToast({ title: '保存失败', icon: 'none' });
        this.setData({ state: 'candidate' });
      }
    },
    fail: () => {
      wx.showToast({ title: '网络异常', icon: 'none' });
      this.setData({ state: 'candidate' });
    },
  });
},
```

- [ ] **Step 2: Add saving state to `add-rule.wxml`**

Add before the error block:

```xml
  <!-- saving -->
  <view wx:if="{{state === 'saving'}}">
    <view class="hint">正在保存…</view>
  </view>
```

- [ ] **Step 3: Verify end-to-end**

Record a memo, confirm candidate → save → toast "已保存" → navigateBack. Return to the knowledge list in the webview; newly-saved rule should appear on next refresh.

- [ ] **Step 4: Commit**

```bash
git add frontend/miniprogram/pages/add-rule
git commit -m "feat(miniapp): save voice candidate to KB"
```

---

## Task 11: `wx.getUpdateManager` in `app.js`

**Files:**
- Modify: `frontend/miniprogram/app.js`

- [ ] **Step 1: Add update-manager wiring in `App({...}).onLaunch`**

Find the `onLaunch` function in `app.js` and add at the end of its body:

```javascript
const updateManager = wx.getUpdateManager();
updateManager.onUpdateReady(() => {
  wx.showModal({
    title: '更新提示',
    content: '新版本已准备好，是否重启应用？',
    success: (res) => { if (res.confirm) updateManager.applyUpdate(); },
  });
});
updateManager.onUpdateFailed(() => {
  console.warn('miniapp update failed');
});
```

- [ ] **Step 2: Verify**

Hard to test locally — but the function is idempotent and WeChat checks for updates on every app launch. The modal only appears when a new version is staged.

- [ ] **Step 3: Commit**

```bash
git add frontend/miniprogram/app.js
git commit -m "feat(miniapp): prompt users to update on new miniapp version"
```

---

# Phase 3 — React Webview

## Task 12: miniappBridge.js helper

**Files:**
- Create: `frontend/web/src/utils/miniappBridge.js`
- Create: `frontend/web/src/utils/__tests__/miniappBridge.test.js`

- [ ] **Step 1: Write failing Vitest test**

```javascript
// frontend/web/src/utils/__tests__/miniappBridge.test.js
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

describe('miniappBridge', () => {
  let originalEnv;
  let originalWx;

  beforeEach(() => {
    originalEnv = window.__wxjs_environment;
    originalWx = window.wx;
  });

  afterEach(() => {
    window.__wxjs_environment = originalEnv;
    window.wx = originalWx;
  });

  it('isInMiniapp returns false in browser', async () => {
    delete window.__wxjs_environment;
    const { isInMiniapp } = await import('../miniappBridge.js?t=1');
    expect(isInMiniapp()).toBe(false);
  });

  it('isInMiniapp returns true when __wxjs_environment is miniprogram', async () => {
    window.__wxjs_environment = 'miniprogram';
    const { isInMiniapp } = await import('../miniappBridge.js?t=2');
    expect(isInMiniapp()).toBe(true);
  });

  it('openAddRuleVoice is a no-op when not in miniapp', async () => {
    delete window.__wxjs_environment;
    const { openAddRuleVoice } = await import('../miniappBridge.js?t=3');
    const spy = vi.fn();
    window.wx = { miniProgram: { navigateTo: spy } };
    openAddRuleVoice();
    expect(spy).not.toHaveBeenCalled();
  });

  it('openAddRuleVoice calls navigateTo when in miniapp', async () => {
    window.__wxjs_environment = 'miniprogram';
    const spy = vi.fn();
    window.wx = { miniProgram: { navigateTo: spy } };
    const { openAddRuleVoice } = await import('../miniappBridge.js?t=4');
    openAddRuleVoice();
    expect(spy).toHaveBeenCalledWith(expect.objectContaining({ url: '/pages/add-rule/add-rule' }));
  });

  it('openAddRuleVoice invokes onStaleVersion on navigateTo fail', async () => {
    window.__wxjs_environment = 'miniprogram';
    const onStaleVersion = vi.fn();
    window.wx = {
      miniProgram: {
        navigateTo: (opts) => opts.fail && opts.fail(),
      },
    };
    const { openAddRuleVoice } = await import('../miniappBridge.js?t=5');
    openAddRuleVoice({ onStaleVersion });
    expect(onStaleVersion).toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend/web && npm run test -- miniappBridge`
Expected: module not found.

- [ ] **Step 3: Write `miniappBridge.js`**

```javascript
// frontend/web/src/utils/miniappBridge.js
// Bridge between the React SPA (running inside WeChat miniapp web-view)
// and native miniapp pages. In a regular browser, these helpers are no-ops.

// WeChat injects window.__wxjs_environment === "miniprogram" inside miniapp
// web-view; this matches the existing convention used by utils/env.js.
export function isInMiniapp() {
  return typeof window !== "undefined"
    && window.__wxjs_environment === "miniprogram";
}

export function openAddRuleVoice({ onStaleVersion } = {}) {
  if (!isInMiniapp()) return;
  const nav = window.wx && window.wx.miniProgram && window.wx.miniProgram.navigateTo;
  if (typeof nav !== "function") return;
  nav({
    url: "/pages/add-rule/add-rule",
    fail: () => { if (onStaleVersion) onStaleVersion(); },
  });
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend/web && npm run test -- miniappBridge`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add frontend/web/src/utils/miniappBridge.js frontend/web/src/utils/__tests__/miniappBridge.test.js
git commit -m "feat(web): miniapp bridge helper for native page navigation"
```

---

## Task 13: Add mic button to AddKnowledgeSubpage + delete dead scaffold

**Files:**
- Modify: `frontend/web/src/pages/doctor/subpages/AddKnowledgeSubpage.jsx`

- [ ] **Step 1: Delete the dead voice-recording scaffold**

Open `frontend/web/src/pages/doctor/subpages/AddKnowledgeSubpage.jsx`. Remove these lines (currently around lines 64, 75–80):

```javascript
// REMOVE:
const [showVoice, setShowVoice] = useState(false);
...
// ── Voice input state ──
const [voiceRecording, setVoiceRecording] = useState(false);
const voiceRecRef = useRef(null);
const voiceTimerRef = useRef(null);
const [voiceSeconds, setVoiceSeconds] = useState(0);
```

If any function bodies reference `voiceRecording`, `voiceRecRef`, `voiceTimerRef`, `voiceSeconds`, or `showVoice`, delete those functions/handlers too — they were never wired and can't work in miniapp web-view.

- [ ] **Step 2: Import the bridge helper and add the mic entry**

At the top of the file, add:

```javascript
import { isInMiniapp, openAddRuleVoice } from "../../../utils/miniappBridge";
import Toast, { useToast } from "../../../components/Toast";
```

(If `Toast`/`useToast` are already imported, skip that line.)

Near the other input-method tabs/buttons (look for the text/file/URL tab or button row), add a new entry that renders only in miniapp:

```jsx
{isInMiniapp() && (
  <Box
    onClick={() => openAddRuleVoice({
      onStaleVersion: () => showToast("请更新小程序到最新版本"),
    })}
    sx={{
      display: "flex", alignItems: "center", gap: 1,
      p: 2, border: `1px solid ${COLOR.border}`, borderRadius: `${RADIUS.md}px`,
      cursor: "pointer", bgcolor: COLOR.surface,
    }}
  >
    <MicIcon sx={{ color: COLOR.primary }} />
    <Typography sx={{ fontSize: TYPE.body }}>语音添加规则</Typography>
  </Box>
)}
```

(Adjust the JSX parent to wherever the existing "+ 添加" controls live. The design system expects `ListCard`/`AppButton` primitives — if the existing buttons use those, use the same primitive here for consistency.)

- [ ] **Step 3: Run lint + Vitest**

Run: `cd frontend/web && npm run test -- miniappBridge && npm run lint 2>&1 | tail -20`
Expected: tests pass; no lint errors on the changes.

- [ ] **Step 4: Manual verification**

Start dev server (`./cli.py start`), open `/doctor/settings/knowledge/add` in a normal browser — the mic button should NOT appear (not in miniapp). In WeChat DevTools simulator with the webview pointed at the same URL, the button should appear and clicking it should `navigateTo` the native page.

- [ ] **Step 5: Commit**

```bash
git add frontend/web/src/pages/doctor/subpages/AddKnowledgeSubpage.jsx
git commit -m "feat(web): voice-to-rule mic entry in AddKnowledgeSubpage; drop dead scaffold"
```

---

# Self-review (done by planner; left here for executor visibility)

**Spec coverage check** (every spec section has a task):

| Spec section | Task(s) |
|---|---|
| Summary / architecture | Tasks 1–13 collectively |
| Key decision 1 (clinical rules only) | Task 4 (uses `KnowledgeCategory`) |
| Key decision 2 (native miniapp page) | Tasks 7–10 |
| Key decision 3 (simple schema matching write API) | Task 1 (models), Task 10 (save) |
| Key decision 4 (dedicated page, not extending pages/voice) | Task 7 creates new dir |
| Key decision 5 (shared ASR + new prompt file) | Task 5 (handler uses `transcribe_audio_bytes`), Task 2 (voice_to_rule.md) |
| Key decision 6 (reject multi-rule) | Task 2 (prompt), Task 3 (eval case), Task 4 (propagation) |
| Backend endpoint contract | Tasks 1, 4, 5, 6 |
| Native page UI + state machine | Tasks 7, 8, 9, 10 |
| Privacy section | No task (spec-documented; no code action other than not retaining audio, already enforced by `provider.py`) |
| Rollout steps 1–2 (backend land) | Tasks 1–6 |
| Rollout step 3 (miniapp land) | Tasks 7–11 |
| Rollout step 4 (React button) | Tasks 12–13 |
| Stale-miniapp-cache mitigation | Task 11 (getUpdateManager), Task 12 (fail handler) |
| Rate limiting deferred to v1.1 | Not implemented (spec explicitly defers) |

**Placeholder scan:** no "TBD"/"fill in"/"similar to Task N"/unclosed references.

**Type consistency:** `VoiceExtractResponse` / `VoiceRuleCandidate` / `VoiceExtractLLMResult` / `KnowledgeCategory` used consistently across tasks 1, 4, 5, 6. `isInMiniapp` / `openAddRuleVoice` exported from `miniappBridge.js` in Task 12 are the exact names imported in Task 13. State names (`idle`/`recording`/`processing`/`candidate`/`error`/`saving`/`perm_denied`) match across Tasks 7–10.

**Known gap (spec-flagged, not plan-fixable):** `logs/llm_calls.jsonl` persists transcripts; suppressing this is a cross-cutting change outside v1 scope. The spec documents this honestly; no task here attempts to change it.

---

# Execution notes

- Python tests: `/Volumes/ORICO/Code/doctor-ai-agent/.venv/bin/python -m pytest --rootdir=/Volumes/ORICO/Code/doctor-ai-agent ...` (per repo memory).
- Frontend Vitest: `cd frontend/web && npm run test -- <pattern>`.
- Miniapp verification: WeChat DevTools simulator + at least one iOS real device + one Android real device before submitting miniapp release.
- **Order:** Phase 1 first (can merge freely, no user-visible change); then Phase 2 (submits miniapp release — 3–7 day WeChat review); only AFTER miniapp is approved and rolled out, land Phase 3 (React button).
- Commits are small and scoped per task — keeps bisect useful if something regresses.
