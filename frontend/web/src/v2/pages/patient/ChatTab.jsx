/**
 * ChatTab — AI health assistant general chat (v2, antd-mobile).
 *
 * Ported from src/pages/patient/ChatTab.jsx.
 * Key behaviours preserved:
 *   - Message polling (10s visible / 60s hidden)
 *   - Optimistic patient messages with de-duplication on poll
 *   - Unread count tracking via LAST_SEEN_CHAT_KEY
 *   - Doctor / AI / patient / system message rendering
 *   - keyboardAwareStyle + useScrollOnKeyboard
 *   - ChatBubble + ChatComposer from v2
 *
 * 2026-04-26: removed in-chat QuickActions card. New-intake CTA lives in
 * the navbar (PatientPage right slot, "+ 新问诊"), records access via
 * the tab nav. The card was duplicating both affordances.
 */

import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { SpinLoading } from "antd-mobile";
import { usePatientApi } from "../../../api/PatientApiContext";
import ChatBubble from "../../ChatBubble";
import ChatConfirmGate from "../../components/ChatConfirmGate";
import ChatDedupPrompt from "../../components/ChatDedupPrompt";
import IntakeBanner from "../../components/IntakeBanner";
import ChatComposer from "../../ChatComposer";
import { keyboardAwareStyle, useScrollOnKeyboard } from "../../keyboard";
import { APP, FONT, RADIUS } from "../../theme";

const LAST_SEEN_CHAT_KEY = "patient_last_seen_chat";

// ---------------------------------------------------------------------------
// Message renderers
// ---------------------------------------------------------------------------

function DoctorMessage({ msg, doctorName }) {
  const time = msg.created_at
    ? new Date(msg.created_at).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" })
    : "";
  return (
    <div style={{ ...styles.msgRow, justifyContent: "flex-start", marginBottom: 12 }}>
      <div style={{ ...styles.avatar, background: APP.accent, color: APP.white }}>
        {(doctorName || "医")[0]}
      </div>
      <div>
        <div
          style={{
            maxWidth: "72vw",
            padding: "9px 13px",
            borderRadius: "18px 18px 18px 4px",
            background: APP.surface,
            boxShadow: "0 1px 3px rgba(0,0,0,0.08)",
            fontSize: FONT.md,
            color: APP.text1,
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
          }}
        >
          {msg.content}
        </div>
        <div style={styles.msgMeta}>
          {doctorName || "医生"}
          {time ? ` · ${time}` : ""}
        </div>
      </div>
    </div>
  );
}

function SystemMessage({ msg, onTap }) {
  return (
    <div
      style={styles.systemCard}
      onClick={onTap || undefined}
    >
      <span style={styles.systemDot} />
      <span style={{ fontSize: FONT.main, color: APP.text2, flex: 1 }}>{msg.content}</span>
      {onTap && <span style={{ fontSize: FONT.sm, color: APP.primary, marginLeft: 8 }}>查看 &rsaquo;</span>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// ChatTab — main export
// ---------------------------------------------------------------------------

export default function ChatTab({
  token,
  doctorName,
  onUnreadCountChange,
}) {
  const navigate = useNavigate();
  const { getPatientChatMessages, sendPatientChat, confirmPatientChatDraft, dedupDecisionPatientChat } = usePatientApi();

  const welcomeMsg = {
    source: "ai",
    content: `您好！我是${doctorName || "医生"}的AI助手。有什么健康问题可以问我。`,
  };

  const [messages, setMessages] = useState([welcomeMsg]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [lastMsgId, setLastMsgId] = useState(null);
  // Intake state — derived from POST /chat triage_category. The chat endpoint
  // does not yet return session_id or turn_count; we track turn count
  // client-side (incremented per successful intake response) and treat the
  // session as "active" while the most recent reply is symptom_report.
  // Intake banner state — driven by the chat response's collected dict.
  // Banner shows progress 已完成 N/6 步 + expandable per-step detail.
  const [intakeActive, setIntakeActive] = useState(false);
  const [intakeCollected, setIntakeCollected] = useState({});
  // suggestions[lastAiMsgId] = chip text array; rendered above the
  // composer. Cleared when the patient sends another turn.
  const [latestSuggestions, setLatestSuggestions] = useState([]);
  const chatEndRef = useRef(null);
  const pollingRef = useRef(null);
  const visibleRef = useRef(true);
  useScrollOnKeyboard(chatEndRef);

  // Polling
  useEffect(() => {
    let cancelled = false;

    async function poll() {
      try {
        const data = await getPatientChatMessages(token, lastMsgId);
        if (cancelled) return;
        if (Array.isArray(data) && data.length > 0) {
          setMessages((prev) => {
            const existingIds = new Set(prev.filter((m) => m.id).map((m) => m.id));
            const newMsgs = data.filter((m) => !existingIds.has(m.id));
            if (newMsgs.length === 0) return prev;
            const cleaned = prev.filter((m) => {
              if (!m._local) return true;
              return !newMsgs.some(
                (nm) => nm.source === "patient" && nm.content === m.content
              );
            });
            return [...cleaned, ...newMsgs];
          });
          setLastMsgId(Math.max(...data.map((m) => m.id)));
        }
      } catch (err) {
        if (err?.status === 401) console.warn("auth expired");
      }
    }

    function startPolling() {
      if (pollingRef.current) clearInterval(pollingRef.current);
      const interval = visibleRef.current ? 10_000 : 60_000;
      pollingRef.current = setInterval(poll, interval);
    }

    function handleVisibility() {
      visibleRef.current = !document.hidden;
      startPolling();
    }

    poll();
    startPolling();
    document.addEventListener("visibilitychange", handleVisibility);
    return () => {
      cancelled = true;
      if (pollingRef.current) clearInterval(pollingRef.current);
      document.removeEventListener("visibilitychange", handleVisibility);
    };
  }, [token]); // eslint-disable-line react-hooks/exhaustive-deps

  // Scroll to bottom on new messages
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Mark messages as seen while the chat tab is mounted — prevents new incoming
  // messages from inflating the badge for a user who is actively reading.
  useEffect(() => {
    if (messages.length === 0) return;
    localStorage.setItem(LAST_SEEN_CHAT_KEY, String(Date.now()));
    onUnreadCountChange?.(0);
  }, [messages, onUnreadCountChange]);

  async function sendConfirmation(draft_id, action) {
    try {
      await confirmPatientChatDraft(token, draft_id, action);
    } catch (err) {
      if (err?.status === 401) return;
      console.warn("confirmPatientChatDraft failed:", err?.message);
    }
  }

  async function sendDedupDecision(draft_id, action) {
    try {
      await dedupDecisionPatientChat(token, draft_id, action);
    } catch (err) {
      if (err?.status === 401) return;
      console.warn("dedupDecisionPatientChat failed:", err?.message);
    }
  }

  async function handleSend(text) {
    if (!text || sending) return;
    setMessages((prev) => [
      ...prev,
      { source: "patient", content: text, _local: true, _ts: Date.now() },
    ]);
    // A new patient turn invalidates the previous AI bubble's chip set.
    setLatestSuggestions([]);
    setSending(true);
    try {
      const resp = await sendPatientChat(token, text);
      // Drive intake banner + chip rendering from the chat response.
      // resp shape: { reply, triage_category, ai_handled, suggestions,
      // intake_active, collected, ... }
      if (resp?.intake_active) {
        setIntakeActive(true);
        setIntakeCollected(resp.collected || {});
      } else {
        setIntakeActive(false);
        setIntakeCollected({});
      }
      // Suggestions ride on the response once backend wires them through.
      // Defensive: accept either an array or a comma-separated string.
      const raw = resp?.suggestions;
      const list = Array.isArray(raw)
        ? raw
        : typeof raw === "string"
          ? raw.split(",").map((s) => s.trim()).filter(Boolean)
          : [];
      setLatestSuggestions(list.slice(0, 4));
    } catch (err) {
      if (err?.status === 401) return;
      setMessages((prev) => [
        ...prev,
        { source: "ai", content: "系统繁忙，请稍后重试。" },
      ]);
    } finally {
      setSending(false);
    }
  }

  function handleCancelIntake() {
    // Backend cancel endpoint is not yet exposed on the chat router (would
    // need POST /chat/intake/cancel). For now this just hides the banner
    // client-side; 24h decay closes any abandoned intake_session row.
    setIntakeActive(false);
    setIntakeCollected({});
  }

  // Index of the last AI message in the list — the only AI bubble that
  // gets the suggestion chip row (suggestions are tied to the most recent
  // turn).
  const lastAiIndex = (() => {
    for (let i = messages.length - 1; i >= 0; i -= 1) {
      const m = messages[i];
      const src = m.source || (m.role === "user" ? "patient" : "ai");
      if (src === "ai" && !m.kind) return i;
    }
    return -1;
  })();

  function renderMessage(msg, i) {
    if (msg.kind === "confirm_gate") {
      return (
        <ChatConfirmGate
          key={msg.id ?? i}
          continuity={msg.continuity}
          onConfirm={() => sendConfirmation(msg.draft_id, "confirm")}
          onContinue={() => sendConfirmation(msg.draft_id, "continue")}
        />
      );
    }

    if (msg.kind === "dedup_prompt") {
      return (
        <ChatDedupPrompt
          key={msg.id ?? i}
          targetReviewed={msg.target_reviewed}
          onMerge={() => sendDedupDecision(msg.draft_id, "merge")}
          onNew={() => sendDedupDecision(msg.draft_id, "new")}
          onNeither={() => sendDedupDecision(msg.draft_id, "neither")}
        />
      );
    }

    const src = msg.source || (msg.role === "user" ? "patient" : "ai");

    if (src === "doctor") {
      return <DoctorMessage key={msg.id || i} msg={msg} doctorName={doctorName} />;
    }

    if (src === "system") {
      const parts = (msg.triage_category || "").split(":");
      const linkType = parts[1] || null;
      const linkId = parts[2] || null;
      let onTap = null;
      if (linkType === "record") onTap = () => navigate(`/patient/records/${linkId}`);
      else if (linkType === "task") onTap = () => navigate("/patient/tasks");
      return <SystemMessage key={msg.id || i} msg={msg} onTap={onTap} />;
    }

    if (src === "patient") {
      return (
        <div style={{ marginBottom: 12 }} key={msg.id || i}>
          <ChatBubble role="user" content={msg.content} />
        </div>
      );
    }

    // AI message with optional triage enrichment
    const isUrgent = msg.triage_category === "urgent";
    const isDiagnosis = msg.triage_category === "diagnosis_confirmation";
    // Suggestion chips moved into ChatComposer (matches doctor IntakePage
    // pattern). They render above the textarea where the patient's
    // attention already is, and tapping toggles the chip text in/out of
    // the textarea so multiple choices can be combined before sending.
    return (
      <div key={msg.id || i} style={{ marginBottom: 12 }}>
        {isDiagnosis ? (
          <div style={styles.diagnosisBubble}>{msg.content}</div>
        ) : (
          <ChatBubble role="assistant" content={msg.content} />
        )}
        {isUrgent && (
          <div style={styles.urgentBanner}>紧急情况，请立即就近就医</div>
        )}
        <div style={{ fontSize: FONT.xs, color: APP.text4, paddingLeft: 44, marginTop: 2 }}>
          {doctorName ? `${doctorName}的AI助手` : "AI健康助手"}
        </div>
      </div>
    );
  }

  return (
    <div style={keyboardAwareStyle}>
      {/* Active-intake banner sits above the message list. Hidden when no
          intake is active. */}
      {intakeActive && (
        <IntakeBanner
          collected={intakeCollected}
          onCancel={handleCancelIntake}
        />
      )}

      {/* Message list */}
      <div style={styles.msgList}>
        {messages.map(renderMessage)}
        {sending && (
          <div style={{ paddingLeft: 44, paddingBottom: 8 }}>
            <SpinLoading color={APP.primary} style={{ "--size": "20px" }} />
          </div>
        )}
        {!sending && messages.length > 0 &&
          (messages[messages.length - 1].source || (messages[messages.length - 1].role === "user" ? "patient" : "ai")) === "patient" && (
            <div style={styles.awaitingHint}>医生已收到您的消息，会尽快回复您</div>
        )}
        <div ref={chatEndRef} />
      </div>

      <ChatComposer
        value={input}
        onChange={setInput}
        onSend={(text) => {
          setInput("");
          handleSend(text);
        }}
        disabled={sending}
        placeholder="请输入…"
        safeBottom={false}
        suggestions={latestSuggestions}
      />
    </div>
  );
}

const styles = {
  msgList: {
    flex: 1,
    overflowY: "auto",
    padding: "12px 0",
  },
  awaitingHint: {
    textAlign: "center",
    fontSize: FONT.xs,
    color: APP.text4,
    padding: "4px 16px 12px",
  },
  msgRow: {
    display: "flex",
    alignItems: "flex-end",
    gap: 8,
    padding: "0 12px",
  },
  avatar: {
    flexShrink: 0,
    width: 32,
    height: 32,
    borderRadius: RADIUS.circle,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontSize: FONT.sm,
    fontWeight: 600,
  },
  msgMeta: {
    fontSize: FONT.xs,
    color: APP.text4,
    marginTop: 3,
    paddingLeft: 2,
  },
  systemCard: {
    display: "flex",
    alignItems: "center",
    margin: "4px 16px",
    padding: "10px 12px",
    background: APP.surface,
    borderRadius: RADIUS.md,
    borderLeft: `3px solid ${APP.primary}`,
    cursor: "pointer",
  },
  systemDot: {
    width: 8,
    height: 8,
    borderRadius: RADIUS.circle,
    background: APP.primary,
    marginRight: 10,
    flexShrink: 0,
  },
  diagnosisBubble: {
    margin: "0 44px 0 44px",
    padding: "9px 13px",
    borderRadius: RADIUS.lg,
    background: APP.primaryLight,
    fontSize: FONT.main,
    color: APP.primary,
    fontWeight: 500,
  },
  urgentBanner: {
    margin: "4px 44px 0 44px",
    padding: "6px 12px",
    borderRadius: RADIUS.md,
    background: APP.dangerLight,
    border: `0.5px solid ${APP.danger}`,
    fontSize: FONT.sm,
    color: APP.danger,
    fontWeight: 500,
  },
};
