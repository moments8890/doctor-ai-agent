// ChatTab — 沟通 tab content for the doctor detail surface.
// Composes the left chat list and the right chat thread inside a 280px / 1fr
// grid card. Empty state renders when no patient is selected.
//
// Mockup reference: docs/specs/2026-04-24-admin-modern-mockup-v3.html
//   `.chat-shell` (the outer 280px / 1fr grid wrapper).
//
// Data flow:
//   - `related.messages.items[]` is the source of truth for the list and
//     thread. The list dedupes by patient_id, the thread filters by the
//     active patient_id and reorders ascending by timestamp.
//   - `related.patients.items[]` is consulted (when present) to show risk
//     pills + a per-patient header (name/gender/age/diagnosis). The current
//     /related shape does not expose `ai_suggestion_id` on messages — see
//     ChatThread.jsx TODO.

import { useEffect, useMemo, useState } from "react";
import ChatList from "./ChatList";
import ChatThread from "./ChatThread";
import { COLOR, FONT, RADIUS, SHADOW } from "../tokens";

function buildPatientIndex(patientItems) {
  const idx = {};
  if (!Array.isArray(patientItems)) return idx;
  for (const p of patientItems) {
    if (!p || p.id == null) continue;
    idx[String(p.id)] = {
      id: p.id,
      name: p.name,
      gender: p.gender,
      age: p.age,
      diagnosis: p.diagnosis || p.condition,
      last_visit: p.last_visit,
      risk: p.risk,
      unread: p.unread || false,
    };
  }
  return idx;
}

function EmptyState() {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        background: COLOR.bgCardAlt,
        color: COLOR.text3,
        gap: 8,
        padding: 24,
        textAlign: "center",
      }}
    >
      <span
        className="material-symbols-outlined"
        style={{ fontSize: 36, color: COLOR.text4 }}
      >
        forum
      </span>
      <div style={{ fontSize: FONT.body, color: COLOR.text2, fontWeight: 500 }}>
        从左侧选择患者查看会话
      </div>
      <div style={{ fontSize: FONT.sm }}>
        AI 解析与起草会作为脚注挂在原始消息下方
      </div>
    </div>
  );
}

export default function ChatTab({ related }) {
  const messages = related?.messages?.items || [];
  const patients = related?.patients?.items || [];

  const patientsById = useMemo(() => buildPatientIndex(patients), [patients]);

  // Pick the first available patient as default selection.
  const firstPatientId = useMemo(() => {
    for (const m of messages) {
      if (m && m.patient_id != null) return m.patient_id;
    }
    return null;
  }, [messages]);

  const [activeId, setActiveId] = useState(firstPatientId);

  // If the first available patient changes (e.g. data refresh) and we
  // haven't picked anything yet, seed the active id.
  useEffect(() => {
    if (activeId == null && firstPatientId != null) {
      setActiveId(firstPatientId);
    }
  }, [activeId, firstPatientId]);

  const activeKey = activeId != null ? String(activeId) : null;
  const activeMessages = useMemo(
    () => (activeKey ? messages.filter((m) => String(m.patient_id) === activeKey) : []),
    [activeKey, messages],
  );
  const activePatient = activeKey
    ? patientsById[activeKey] || {
        id: activeId,
        name: messages.find((m) => String(m.patient_id) === activeKey)?.patient_name,
      }
    : null;

  return (
    <div
      data-v3="chat-shell"
      style={{
        display: "grid",
        gridTemplateColumns: "280px 1fr",
        height: 700,
        background: COLOR.bgCard,
        border: `1px solid ${COLOR.borderSubtle}`,
        borderRadius: RADIUS.lg,
        overflow: "hidden",
        boxShadow: SHADOW.s1,
        marginTop: 16,
      }}
    >
      <ChatList
        messages={messages}
        activeId={activeId}
        onSelect={setActiveId}
        patientsById={patientsById}
      />
      {activePatient ? (
        <ChatThread patient={activePatient} messages={activeMessages} />
      ) : (
        <EmptyState />
      )}
    </div>
  );
}
