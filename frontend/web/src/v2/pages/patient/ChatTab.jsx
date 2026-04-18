/**
 * ChatTab — AI health assistant general chat (v2, antd-mobile).
 *
 * Ported from src/pages/patient/ChatTab.jsx.
 * Key behaviours preserved:
 *   - QuickActions row ("新问诊", "我的病历")
 *   - Message polling (10s visible / 60s hidden)
 *   - Optimistic patient messages with de-duplication on poll
 *   - Unread count tracking via LAST_SEEN_CHAT_KEY
 *   - Doctor / AI / patient / system message rendering
 *   - keyboardAwareStyle + useScrollOnKeyboard
 *   - ChatBubble + ChatComposer from v2
 */

import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { SpinLoading } from "antd-mobile";
import { usePatientApi } from "../../../api/PatientApiContext";
import ChatBubble from "../../ChatBubble";
import ChatComposer from "../../ChatComposer";
import { keyboardAwareStyle, useScrollOnKeyboard } from "../../keyboard";
import { APP } from "../../theme";

const LAST_SEEN_CHAT_KEY = "patient_last_seen_chat";

// ---------------------------------------------------------------------------
// QuickActions
// ---------------------------------------------------------------------------

function QuickActions({ onNewInterview, onViewRecords }) {
  const items = [
    { label: "新问诊", subtitle: "AI帮您整理病情", emoji: "📋", onClick: onNewInterview },
    { label: "我的病历", subtitle: "查看历史记录", emoji: "📂", onClick: onViewRecords },
  ];
  return (
    <div style={styles.quickRow}>
      {items.map((a) => (
        <div key={a.label} style={styles.quickCard} onClick={a.onClick}>
          <span style={styles.quickEmoji}>{a.emoji}</span>
          <div>
            <div style={styles.quickTitle}>{a.label}</div>
            <div style={styles.quickSub}>{a.subtitle}</div>
          </div>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Message renderers
// ---------------------------------------------------------------------------

function DoctorMessage({ msg, doctorName }) {
  const time = msg.created_at
    ? new Date(msg.created_at).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" })
    : "";
  return (
    <div style={{ ...styles.msgRow, justifyContent: "flex-start", marginBottom: 12 }}>
      <div style={{ ...styles.avatar, background: APP.accent, color: "#fff" }}>
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
            fontSize: 15,
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
      <span style={{ fontSize: 14, color: APP.text2, flex: 1 }}>{msg.content}</span>
      {onTap && <span style={{ fontSize: 12, color: "#07C160", marginLeft: 8 }}>查看 &rsaquo;</span>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// ChatTab — main export
// ---------------------------------------------------------------------------

export default function ChatTab({
  token,
  doctorName,
  onNewInterview,
  onViewRecords,
  onUnreadCountChange,
}) {
  const navigate = useNavigate();
  const { getPatientChatMessages, sendPatientChat } = usePatientApi();

  const welcomeMsg = {
    source: "ai",
    content: `您好！我是${doctorName || "医生"}的AI助手。有什么健康问题可以问我。`,
  };

  const [messages, setMessages] = useState([welcomeMsg]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [lastMsgId, setLastMsgId] = useState(null);
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

  // Unread badge
  useEffect(() => {
    if (!onUnreadCountChange || messages.length === 0) return;
    const lastSeen = parseInt(localStorage.getItem(LAST_SEEN_CHAT_KEY) || "0", 10);
    const unread = messages.filter((m) => {
      const t = new Date(m.created_at).getTime();
      return t > lastSeen;
    }).length;
    onUnreadCountChange(unread);
  }, [messages, onUnreadCountChange]);

  async function handleSend(text) {
    if (!text || sending) return;
    setMessages((prev) => [
      ...prev,
      { source: "patient", content: text, _local: true, _ts: Date.now() },
    ]);
    setSending(true);
    try {
      await sendPatientChat(token, text);
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

  function renderMessage(msg, i) {
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
        <div style={{ fontSize: 11, color: APP.text4, paddingLeft: 44, marginTop: 2 }}>
          {doctorName ? `${doctorName}的AI助手` : "AI健康助手"}
        </div>
      </div>
    );
  }

  return (
    <div style={keyboardAwareStyle}>
      <QuickActions onNewInterview={onNewInterview} onViewRecords={onViewRecords} />

      {/* Message list */}
      <div style={styles.msgList}>
        {messages.map(renderMessage)}
        {sending && (
          <div style={{ paddingLeft: 44, paddingBottom: 8 }}>
            <SpinLoading color="#07C160" style={{ "--size": "20px" }} />
          </div>
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
      />
    </div>
  );
}

const styles = {
  quickRow: {
    display: "flex",
    gap: 10,
    padding: "12px 16px 8px",
    background: APP.surfaceAlt,
    flexShrink: 0,
  },
  quickCard: {
    flex: 1,
    background: APP.surface,
    borderRadius: 10,
    padding: "10px 12px",
    display: "flex",
    alignItems: "center",
    gap: 8,
    cursor: "pointer",
    boxShadow: "0 1px 3px rgba(0,0,0,0.06)",
    userSelect: "none",
  },
  quickEmoji: {
    fontSize: 22,
    flexShrink: 0,
  },
  quickTitle: {
    fontSize: 14,
    fontWeight: 600,
    color: APP.text1,
    lineHeight: 1.3,
  },
  quickSub: {
    fontSize: 11,
    color: APP.text4,
    marginTop: 2,
  },
  msgList: {
    flex: 1,
    overflowY: "auto",
    padding: "12px 0",
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
    borderRadius: "50%",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontSize: 12,
    fontWeight: 600,
  },
  msgMeta: {
    fontSize: 11,
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
    borderRadius: 8,
    borderLeft: "3px solid #07C160",
    cursor: "pointer",
  },
  systemDot: {
    width: 8,
    height: 8,
    borderRadius: "50%",
    background: "#07C160",
    marginRight: 10,
    flexShrink: 0,
  },
  diagnosisBubble: {
    margin: "0 44px 0 44px",
    padding: "9px 13px",
    borderRadius: 12,
    background: "#e7f8ee",
    fontSize: 14,
    color: "#07C160",
    fontWeight: 500,
  },
  urgentBanner: {
    margin: "4px 44px 0 44px",
    padding: "6px 12px",
    borderRadius: 8,
    background: "#fff0f0",
    border: "0.5px solid #FA5151",
    fontSize: 13,
    color: "#FA5151",
    fontWeight: 500,
  },
};
