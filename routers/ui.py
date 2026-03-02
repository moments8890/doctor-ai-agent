from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy import func, select

from db.crud import get_all_records_for_doctor, get_system_prompt, get_records_for_patient, get_all_patients, upsert_system_prompt
from db.engine import AsyncSessionLocal
from db.models import MedicalRecordDB

router = APIRouter(tags=["ui"])


_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Doctor AI Chat</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&display=swap');

    :root {
      --bg-start: #f6f2ea;
      --bg-end: #dce9e6;
      --panel: #fffdf7;
      --ink: #1b2a33;
      --muted: #5f6f7a;
      --accent: #0d7a70;
      --accent-soft: #dbf1ee;
      --doctor: #f3f7ff;
      --agent: #f2fcf6;
      --danger: #c03535;
      --border: #d5ddd7;
      --shadow: 0 16px 40px rgba(19, 45, 50, 0.12);
      --radius: 18px;
    }

    * {
      box-sizing: border-box;
    }

    body {
      margin: 0;
      min-height: 100vh;
      font-family: "IBM Plex Sans", "PingFang SC", "Hiragino Sans GB", sans-serif;
      color: var(--ink);
      background:
        radial-gradient(1200px 800px at 80% -10%, rgba(13, 122, 112, 0.18), transparent 55%),
        radial-gradient(900px 600px at -15% 105%, rgba(182, 115, 64, 0.17), transparent 55%),
        linear-gradient(140deg, var(--bg-start), var(--bg-end));
      display: grid;
      place-items: center;
      padding: 24px 14px;
    }

    .app {
      width: min(980px, 100%);
      height: min(88vh, 840px);
      background: color-mix(in srgb, var(--panel) 92%, white 8%);
      border: 1px solid var(--border);
      border-radius: 24px;
      box-shadow: var(--shadow);
      overflow: hidden;
      display: grid;
      grid-template-rows: auto 1fr auto;
      animation: rise 420ms ease-out;
    }

    .topbar {
      display: flex;
      gap: 12px;
      align-items: center;
      justify-content: space-between;
      padding: 14px 18px;
      border-bottom: 1px solid var(--border);
      background:
        linear-gradient(90deg, rgba(13, 122, 112, 0.08), transparent 28%),
        linear-gradient(0deg, #fff, #fff);
    }

    .brand {
      display: flex;
      align-items: center;
      gap: 10px;
      font-weight: 700;
      letter-spacing: 0.2px;
    }

    .pulse {
      width: 12px;
      height: 12px;
      border-radius: 999px;
      background: var(--accent);
      box-shadow: 0 0 0 0 rgba(13, 122, 112, 0.5);
      animation: pulse 1.8s infinite;
    }

    .doctor {
      display: flex;
      gap: 8px;
      align-items: center;
      color: var(--muted);
      font-size: 14px;
    }

    .doctor input {
      border: 1px solid var(--border);
      background: #fff;
      border-radius: 12px;
      font: inherit;
      padding: 8px 10px;
      min-width: 180px;
      color: var(--ink);
      outline: none;
    }

    .doctor input:focus {
      border-color: var(--accent);
      box-shadow: 0 0 0 3px rgba(13, 122, 112, 0.14);
    }

    #messages {
      overflow: auto;
      padding: 18px;
      display: flex;
      flex-direction: column;
      gap: 14px;
      background:
        linear-gradient(transparent 96%, rgba(27, 42, 51, 0.03) 96%) 0 0 / 100% 28px;
    }

    .msg {
      max-width: min(80ch, 88%);
      border-radius: var(--radius);
      padding: 11px 13px;
      line-height: 1.45;
      border: 1px solid var(--border);
      white-space: pre-wrap;
      word-wrap: break-word;
      transform-origin: left top;
      animation: pop 220ms ease-out;
    }

    .msg.user {
      align-self: flex-end;
      background: var(--doctor);
      border-bottom-right-radius: 7px;
    }

    .msg.agent {
      align-self: flex-start;
      background: var(--agent);
      border-bottom-left-radius: 7px;
    }

    .msg.error {
      align-self: center;
      color: var(--danger);
      background: #fff2f2;
    }

    .record {
      margin-top: 10px;
      background: #fff;
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 10px;
      font-size: 14px;
    }

    .record-title {
      font-weight: 700;
      color: #0b5e57;
      margin-bottom: 8px;
    }

    .record-row {
      margin: 5px 0;
    }

    .composer {
      padding: 14px;
      border-top: 1px solid var(--border);
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 10px;
      background: #fff;
    }

    textarea {
      width: 100%;
      resize: none;
      min-height: 52px;
      max-height: 160px;
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 12px;
      font: inherit;
      line-height: 1.4;
      outline: none;
      background: #fff;
    }

    textarea:focus {
      border-color: var(--accent);
      box-shadow: 0 0 0 3px rgba(13, 122, 112, 0.14);
    }

    button {
      border: 0;
      border-radius: 14px;
      padding: 0 18px;
      min-width: 92px;
      background: linear-gradient(160deg, #0d7a70, #0f665f);
      color: #fff;
      font: inherit;
      font-weight: 600;
      cursor: pointer;
      transition: transform 120ms ease, filter 120ms ease;
    }

    button:hover {
      filter: brightness(1.06);
    }

    button:active {
      transform: translateY(1px);
    }

    button:disabled {
      opacity: 0.6;
      cursor: not-allowed;
    }

    @media (max-width: 800px) {
      .app {
        height: 92vh;
      }
      .topbar {
        flex-direction: column;
        align-items: stretch;
      }
      .doctor input {
        min-width: 0;
        width: 100%;
      }
      .composer {
        grid-template-columns: 1fr;
      }
      button {
        min-height: 44px;
      }
    }

    @keyframes rise {
      from { opacity: 0; transform: translateY(10px); }
      to { opacity: 1; transform: translateY(0); }
    }

    @keyframes pop {
      from { opacity: 0; transform: translateY(6px) scale(0.995); }
      to { opacity: 1; transform: translateY(0) scale(1); }
    }

    @keyframes pulse {
      0% { box-shadow: 0 0 0 0 rgba(13, 122, 112, 0.42); }
      70% { box-shadow: 0 0 0 10px rgba(13, 122, 112, 0); }
      100% { box-shadow: 0 0 0 0 rgba(13, 122, 112, 0); }
    }
  </style>
</head>
<body>
  <main class="app">
    <header class="topbar">
      <div class="brand">
        <span class="pulse"></span>
        <span>Doctor AI Chat</span>
      </div>
      <label class="doctor">
        <span>Doctor ID</span>
        <input id="doctorId" value="web_doctor" />
      </label>
    </header>

    <section id="messages"></section>

    <form class="composer" id="chatForm">
      <textarea id="input" placeholder="输入病历口述、建档、查询等内容..." required></textarea>
      <button id="sendBtn" type="submit">发送</button>
    </form>
  </main>

  <script>
    const form = document.getElementById("chatForm");
    const input = document.getElementById("input");
    const sendBtn = document.getElementById("sendBtn");
    const messages = document.getElementById("messages");
    const doctorIdEl = document.getElementById("doctorId");
    const history = [];

    const recordLabels = [
      ["chief_complaint", "主诉"],
      ["history_of_present_illness", "现病史"],
      ["past_medical_history", "既往史"],
      ["physical_examination", "体格检查"],
      ["auxiliary_examinations", "辅助检查"],
      ["diagnosis", "诊断"],
      ["treatment_plan", "治疗方案"],
      ["follow_up_plan", "随访计划"]
    ];

    function escapeHtml(text) {
      return text
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
    }

    function appendMessage(role, text) {
      const el = document.createElement("article");
      el.className = "msg " + role;
      el.textContent = text;
      messages.appendChild(el);
      messages.scrollTop = messages.scrollHeight;
      return el;
    }

    function appendRecord(container, record) {
      const wrap = document.createElement("div");
      wrap.className = "record";
      wrap.innerHTML = '<div class="record-title">结构化病历</div>';

      for (const [key, label] of recordLabels) {
        if (record[key]) {
          const row = document.createElement("div");
          row.className = "record-row";
          row.innerHTML = "<strong>[" + label + "]</strong> " + escapeHtml(String(record[key]));
          wrap.appendChild(row);
        }
      }

      container.appendChild(wrap);
    }

    function setBusy(busy) {
      sendBtn.disabled = busy;
      sendBtn.textContent = busy ? "发送中..." : "发送";
      input.disabled = busy;
    }

    appendMessage("agent", "您好，我是门诊助手。您可以直接说：建档、记录病历、查询患者。");

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const text = input.value.trim();
      const doctorId = doctorIdEl.value.trim() || "web_doctor";
      if (!text) return;

      appendMessage("user", text);
      input.value = "";
      setBusy(true);

      try {
        const response = await fetch("/api/records/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text, history, doctor_id: doctorId })
        });

        if (!response.ok) {
          const detail = await response.text();
          throw new Error("HTTP " + response.status + ": " + detail);
        }

        const data = await response.json();
        const msgEl = appendMessage("agent", data.reply || "收到。");
        if (data.record) appendRecord(msgEl, data.record);
        history.push({ role: "user", content: text });
        history.push({ role: "assistant", content: data.reply || "" });
      } catch (err) {
        appendMessage("error", "请求失败: " + (err?.message || String(err)));
      } finally {
        setBusy(false);
        input.focus();
      }
    });

    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        form.requestSubmit();
      }
    });
  </script>
</body>
</html>
"""


@router.get("/chat", response_class=HTMLResponse)
async def chat_page():
    return HTMLResponse(content=_HTML)


_MANAGE_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Doctor Console</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;700&family=Noto+Sans+SC:wght@400;500;700&display=swap');

    :root {
      --bg: #eef3f7;
      --ink: #102330;
      --muted: #5d7585;
      --panel: #ffffff;
      --line: #d6e0e6;
      --accent: #005f73;
      --accent-2: #8f5f00;
      --danger: #bd2a2a;
      --shadow: 0 18px 44px rgba(16, 35, 48, 0.14);
      --radius: 16px;
    }

    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Noto Sans SC", sans-serif;
      background:
        radial-gradient(1000px 520px at 85% -5%, rgba(0, 95, 115, 0.18), transparent 62%),
        radial-gradient(850px 500px at -10% 105%, rgba(143, 95, 0, 0.16), transparent 62%),
        var(--bg);
      min-height: 100vh;
      color: var(--ink);
      padding: 20px 12px;
    }

    .wrap {
      width: min(1120px, 100%);
      margin: 0 auto;
      display: grid;
      gap: 14px;
    }

    .head {
      background: var(--panel);
      border: 1px solid var(--line);
      box-shadow: var(--shadow);
      border-radius: var(--radius);
      padding: 14px;
      display: grid;
      gap: 10px;
    }

    .title {
      font-family: "Space Grotesk", "Noto Sans SC", sans-serif;
      font-weight: 700;
      font-size: 22px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
    }

    .title a {
      text-decoration: none;
      color: var(--accent);
      font-size: 14px;
    }

    .bar {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 10px;
    }

    .bar input {
      min-width: 0;
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 10px;
      font: inherit;
      outline: none;
    }

    .bar button, .btn {
      border: 0;
      border-radius: 12px;
      padding: 10px 14px;
      background: linear-gradient(160deg, var(--accent), #0a4f5e);
      color: #fff;
      font-weight: 700;
      cursor: pointer;
    }

    .tabs {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
    }

    .tab {
      border: 1px solid var(--line);
      background: #fff;
      color: var(--ink);
      border-radius: 999px;
      padding: 7px 12px;
      cursor: pointer;
      font-weight: 600;
    }

    .tab.active {
      background: var(--accent);
      color: #fff;
      border-color: var(--accent);
    }

    .panel {
      display: none;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      box-shadow: var(--shadow);
      padding: 14px;
    }

    .panel.active { display: block; }
    .note { color: var(--muted); font-size: 13px; margin-bottom: 10px; }
    .count { font-weight: 700; font-size: 14px; color: var(--accent-2); }

    .cards {
      display: grid;
      gap: 10px;
    }

    .card {
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 10px;
      background: #fff;
    }

    .row {
      display: flex;
      justify-content: space-between;
      gap: 8px;
      flex-wrap: wrap;
    }

    .row strong {
      font-family: "Space Grotesk", "Noto Sans SC", sans-serif;
      letter-spacing: 0.2px;
    }

    textarea {
      width: 100%;
      min-height: 200px;
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 10px;
      font: inherit;
      outline: none;
      resize: vertical;
    }

    .error { color: var(--danger); font-weight: 600; }
    .ok { color: #007749; font-weight: 600; }
    .small { font-size: 13px; color: var(--muted); }

    @media (max-width: 780px) {
      .bar { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <main class="wrap">
    <section class="head">
      <div class="title">
        <span>Doctor Management Console</span>
        <a href="/chat">Open Chat</a>
      </div>
      <div class="bar">
        <input id="doctorId" value="web_doctor" />
        <button id="reloadBtn">Load</button>
      </div>
      <div class="tabs">
        <button class="tab active" data-tab="patients">Patients</button>
        <button class="tab" data-tab="records">Records</button>
        <button class="tab" data-tab="custom">Customization</button>
      </div>
    </section>

    <section id="patients" class="panel active">
      <div class="note">当前医生下患者列表。点击“View Records”查看该患者最近病历。</div>
      <div id="patientsCount" class="count"></div>
      <div id="patientsList" class="cards"></div>
    </section>

    <section id="records" class="panel">
      <div class="note">最近病历记录（支持按患者筛选）。</div>
      <div class="small">Patient ID filter: <input id="patientFilter" style="width:120px;margin-left:8px;" /></div>
      <div id="recordsCount" class="count" style="margin-top:8px;"></div>
      <div id="recordsList" class="cards"></div>
    </section>

    <section id="custom" class="panel">
      <div class="note">可编辑结构化病历系统提示词。保存后约 60 秒内生效。</div>
      <div class="small">Key: structuring</div>
      <textarea id="promptBase"></textarea>
      <button id="saveBase" class="btn" style="margin-top:8px;">Save Base Prompt</button>
      <div class="small" style="margin-top:14px;">Key: structuring.extension</div>
      <textarea id="promptExt"></textarea>
      <button id="saveExt" class="btn" style="margin-top:8px;">Save Extension</button>
      <div id="saveState" class="small" style="margin-top:10px;"></div>
    </section>
  </main>

  <script>
    const doctorEl = document.getElementById("doctorId");
    const reloadBtn = document.getElementById("reloadBtn");
    const tabs = document.querySelectorAll(".tab");
    const panels = document.querySelectorAll(".panel");
    const patientsCount = document.getElementById("patientsCount");
    const patientsList = document.getElementById("patientsList");
    const patientFilter = document.getElementById("patientFilter");
    const recordsCount = document.getElementById("recordsCount");
    const recordsList = document.getElementById("recordsList");
    const promptBase = document.getElementById("promptBase");
    const promptExt = document.getElementById("promptExt");
    const saveState = document.getElementById("saveState");

    function esc(text) {
      return String(text || "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;");
    }

    function doctorId() {
      return doctorEl.value.trim() || "web_doctor";
    }

    function setTab(id) {
      tabs.forEach(t => t.classList.toggle("active", t.dataset.tab === id));
      panels.forEach(p => p.classList.toggle("active", p.id === id));
    }

    tabs.forEach(t => t.addEventListener("click", () => setTab(t.dataset.tab)));

    async function loadPatients() {
      const res = await fetch(`/api/manage/patients?doctor_id=${encodeURIComponent(doctorId())}`);
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      patientsCount.textContent = `Total: ${data.items.length}`;
      patientsList.innerHTML = "";
      for (const p of data.items) {
        const card = document.createElement("article");
        card.className = "card";
        const info = [p.gender, p.year_of_birth ? `${new Date().getFullYear() - p.year_of_birth}岁` : null].filter(Boolean).join(" / ");
        card.innerHTML = `
          <div class="row">
            <strong>${esc(p.name)}</strong>
            <span class="small">id=${p.id} | ${esc(info)} | records=${p.record_count}</span>
          </div>
          <div class="small">created: ${esc(p.created_at || "-")}</div>
          <button class="btn" data-pid="${p.id}" style="margin-top:8px;">View Records</button>
        `;
        card.querySelector("button").addEventListener("click", () => {
          setTab("records");
          patientFilter.value = String(p.id);
          loadRecords();
        });
        patientsList.appendChild(card);
      }
      if (!data.items.length) {
        patientsList.innerHTML = '<div class="small">No patients yet.</div>';
      }
    }

    async function loadRecords() {
      const pid = patientFilter.value.trim();
      const url = new URL("/api/manage/records", window.location.origin);
      url.searchParams.set("doctor_id", doctorId());
      if (pid) url.searchParams.set("patient_id", pid);
      const res = await fetch(url);
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      recordsCount.textContent = `Total: ${data.items.length}`;
      recordsList.innerHTML = "";
      for (const r of data.items) {
        const card = document.createElement("article");
        card.className = "card";
        card.innerHTML = `
          <div class="row">
            <strong>${esc(r.patient_name || "未关联患者")}</strong>
            <span class="small">record_id=${r.id} | ${esc(r.created_at || "-")}</span>
          </div>
          <div class="small"><b>主诉</b>: ${esc(r.chief_complaint || "-")}</div>
          <div class="small"><b>诊断</b>: ${esc(r.diagnosis || "-")}</div>
          <div class="small"><b>治疗</b>: ${esc(r.treatment_plan || "-")}</div>
        `;
        recordsList.appendChild(card);
      }
      if (!data.items.length) {
        recordsList.innerHTML = '<div class="small">No records.</div>';
      }
    }

    async function loadPrompts() {
      const res = await fetch("/api/manage/prompts");
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      promptBase.value = data.structuring || "";
      promptExt.value = data.structuring_extension || "";
    }

    async function savePrompt(key, content) {
      const res = await fetch(`/api/manage/prompts/${encodeURIComponent(key)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content })
      });
      if (!res.ok) throw new Error(await res.text());
    }

    async function loadAll() {
      saveState.textContent = "";
      try {
        await Promise.all([loadPatients(), loadRecords(), loadPrompts()]);
      } catch (err) {
        saveState.innerHTML = `<span class="error">Load failed: ${esc(err.message || err)}</span>`;
      }
    }

    reloadBtn.addEventListener("click", loadAll);
    document.getElementById("saveBase").addEventListener("click", async () => {
      saveState.textContent = "Saving base prompt...";
      try {
        await savePrompt("structuring", promptBase.value);
        saveState.innerHTML = '<span class="ok">Base prompt saved.</span>';
      } catch (err) {
        saveState.innerHTML = `<span class="error">Save failed: ${esc(err.message || err)}</span>`;
      }
    });
    document.getElementById("saveExt").addEventListener("click", async () => {
      saveState.textContent = "Saving extension prompt...";
      try {
        await savePrompt("structuring.extension", promptExt.value);
        saveState.innerHTML = '<span class="ok">Extension prompt saved.</span>';
      } catch (err) {
        saveState.innerHTML = `<span class="error">Save failed: ${esc(err.message || err)}</span>`;
      }
    });

    patientFilter.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        loadRecords();
      }
    });

    loadAll();
  </script>
</body>
</html>
"""


class PromptUpdate(BaseModel):
    content: str


@router.get("/manage", response_class=HTMLResponse)
async def manage_page():
    return HTMLResponse(content=_MANAGE_HTML)


def _fmt_ts(value: datetime | None) -> str | None:
    if not value:
        return None
    return value.strftime("%Y-%m-%d %H:%M:%S")


@router.get("/api/manage/patients")
async def manage_patients(doctor_id: str = Query(default="web_doctor")):
    async with AsyncSessionLocal() as db:
        patients = await get_all_patients(db, doctor_id)
        counts_result = await db.execute(
            select(MedicalRecordDB.patient_id, func.count(MedicalRecordDB.id))
            .where(MedicalRecordDB.doctor_id == doctor_id, MedicalRecordDB.patient_id.is_not(None))
            .group_by(MedicalRecordDB.patient_id)
        )
        count_map = {pid: count for pid, count in counts_result.all()}

    return {
        "doctor_id": doctor_id,
        "items": [
            {
                "id": p.id,
                "name": p.name,
                "gender": p.gender,
                "year_of_birth": p.year_of_birth,
                "created_at": _fmt_ts(p.created_at),
                "record_count": int(count_map.get(p.id, 0)),
            }
            for p in patients
        ],
    }


@router.get("/api/manage/records")
async def manage_records(
    doctor_id: str = Query(default="web_doctor"),
    patient_id: int | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
):
    async with AsyncSessionLocal() as db:
        if patient_id is not None:
            records = await get_records_for_patient(db, doctor_id, patient_id, limit=limit)
            patient_name = None
            patients = await get_all_patients(db, doctor_id)
            for p in patients:
                if p.id == patient_id:
                    patient_name = p.name
                    break
            items = [
                {
                    "id": r.id,
                    "patient_id": r.patient_id,
                    "patient_name": patient_name,
                    "chief_complaint": r.chief_complaint,
                    "diagnosis": r.diagnosis,
                    "treatment_plan": r.treatment_plan,
                    "created_at": _fmt_ts(r.created_at),
                }
                for r in records
            ]
        else:
            records = await get_all_records_for_doctor(db, doctor_id, limit=limit)
            items = [
                {
                    "id": r.id,
                    "patient_id": r.patient_id,
                    "patient_name": r.patient.name if r.patient else None,
                    "chief_complaint": r.chief_complaint,
                    "diagnosis": r.diagnosis,
                    "treatment_plan": r.treatment_plan,
                    "created_at": _fmt_ts(r.created_at),
                }
                for r in records
            ]

    return {"doctor_id": doctor_id, "items": items}


@router.get("/api/manage/prompts")
async def manage_prompts():
    async with AsyncSessionLocal() as db:
        base = await get_system_prompt(db, "structuring")
        ext = await get_system_prompt(db, "structuring.extension")
    return {
        "structuring": base.content if base else "",
        "structuring_extension": ext.content if ext else "",
    }


@router.put("/api/manage/prompts/{key}")
async def update_prompt(key: str, body: PromptUpdate):
    if key not in {"structuring", "structuring.extension"}:
        raise HTTPException(status_code=400, detail="Only structuring and structuring.extension are editable.")
    async with AsyncSessionLocal() as db:
        await upsert_system_prompt(db, key, body.content)
    return {"ok": True, "key": key}
