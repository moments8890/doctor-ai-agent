/**
 * @route /doctor/patients/:patientId?view=chat
 *
 * v2 PatientChatPage — message timeline + reply composer.
 * Full-screen subpage (hides TabBar). antd-mobile only. No MUI.
 *
 * Core features:
 * - Fetch + display patient chat messages (patient side + doctor/AI replies)
 * - AI draft cards with "edit" and "confirm send" actions
 * - ChatComposer at bottom (keyboard-aware)
 * - NavBar with patient name + back button
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { NavBar, SpinLoading, Button, Toast, Dialog } from "antd-mobile";
import { LeftOutline } from "antd-mobile-icons";
import { useApi } from "../../../api/ApiContext";
import { useDoctorStore } from "../../../store/doctorStore";
import { nowTs } from "../../../utils/time";
import ChatComposer from "../../ChatComposer";
import { keyboardAwareStyle, useScrollOnKeyboard } from "../../keyboard";
import { APP, FONT } from "../../theme";

// ── Message bubble ─────────────────────────────────────────────────

function MessageBubble({ msg, patientName }) {
  const isPatient =
    msg.role === "patient" ||
    msg.sender_type === "patient" ||
    msg.source === "patient" ||
    msg.direction === "inbound";
  const isDoctor =
    msg.role === "doctor" ||
    msg.sender_type === "doctor" ||
    msg.source === "doctor";

  const time = msg.created_at
    ? new Date(msg.created_at).toLocaleTimeString("zh-CN", {
        hour: "2-digit",
        minute: "2-digit",
      })
    : "";

  const bubbleColor = isPatient
    ? APP.surface
    : isDoctor
    ? APP.wechatGreen
    : APP.surface;

  return (
    <div
      style={{
        display: "flex",
        flexDirection: isPatient ? "row" : "row-reverse",
        alignItems: "flex-end",
        gap: 8,
        padding: "4px 12px",
      }}
    >
      {/* Avatar */}
      <div
        style={{
          width: 34,
          height: 34,
          borderRadius: "50%",
          background: isPatient ? APP.accent : APP.primary,
          color: APP.white,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: FONT.sm,
          fontWeight: 600,
          flexShrink: 0,
        }}
      >
        {isPatient ? (patientName || "患")[0] : isDoctor ? "我" : "AI"}
      </div>

      {/* Bubble + timestamp */}
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: isPatient ? "flex-start" : "flex-end",
          gap: 3,
          maxWidth: "72%",
        }}
      >
        {!isPatient && !isDoctor && (
          <span style={{ fontSize: FONT.xs, color: APP.text4, fontWeight: 500 }}>
            AI
          </span>
        )}
        <div
          style={{
            background: bubbleColor,
            borderRadius: isPatient
              ? "14px 14px 14px 3px"
              : "14px 14px 3px 14px",
            padding: "9px 13px",
            fontSize: FONT.md,
            color: APP.text1,
            lineHeight: "1.6",
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
            boxShadow: isDoctor ? "none" : "0 1px 3px rgba(0,0,0,0.07)",
          }}
        >
          {msg.content || msg.text || ""}
        </div>
        {time && (
          <span style={{ fontSize: FONT.xs, color: APP.text4 }}>{time}</span>
        )}
      </div>
    </div>
  );
}

// ── AI Draft card (inline after patient message) ────────────────────

function AIDraftCard({ draft, onEdit, onSend }) {
  const text = draft.draft_text || draft.content || "";
  if (!text) return null;

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "row-reverse",
        alignItems: "flex-end",
        gap: 8,
        padding: "4px 12px",
        marginTop: 4,
      }}
    >
      {/* AI avatar */}
      <div
        style={{
          width: 34,
          height: 34,
          borderRadius: "50%",
          background: APP.primary,
          color: APP.white,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: FONT.sm,
          fontWeight: 600,
          flexShrink: 0,
        }}
      >
        AI
      </div>

      {/* Draft bubble */}
      <div
        style={{
          maxWidth: "78%",
          background: APP.primaryLight,
          border: `1px solid ${APP.primary}30`,
          borderRadius: RADIUS.lg,
          padding: "10px 14px",
        }}
      >
        <div
          style={{
            fontSize: FONT.xs,
            color: APP.primary,
            fontWeight: 600,
            marginBottom: 6,
          }}
        >
          AI起草回复 · 待你确认
        </div>
        <div
          style={{
            fontSize: FONT.main,
            color: APP.text1,
            lineHeight: "1.65",
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
          }}
        >
          {text}
        </div>
        <div
          style={{
            display: "flex",
            justifyContent: "flex-end",
            gap: 16,
            marginTop: 10,
            paddingTop: 8,
            borderTop: `0.5px solid #07C16020`,
          }}
        >
          <span
            style={{
              fontSize: FONT.sm,
              color: APP.text4,
              cursor: "pointer",
            }}
            onClick={() => onEdit?.(draft)}
          >
            修改
          </span>
          <span
            style={{
              fontSize: FONT.sm,
              color: APP.primary,
              fontWeight: 600,
              cursor: "pointer",
            }}
            onClick={() => onSend?.(draft)}
          >
            确认发送 ›
          </span>
        </div>
      </div>
    </div>
  );
}

// ── Edit banner (shown when editing a draft) ───────────────────────

function EditingBanner({ onCancel }) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "6px 14px",
        background: APP.primaryLight,
        borderBottom: `0.5px solid #07C16030`,
        flexShrink: 0,
      }}
    >
      <span style={{ fontSize: FONT.sm, color: APP.primary, fontWeight: 500 }}>
        正在编辑AI草稿
      </span>
      <span
        style={{ fontSize: FONT.sm, color: APP.text4, cursor: "pointer" }}
        onClick={onCancel}
      >
        取消
      </span>
    </div>
  );
}

// ── Main component ─────────────────────────────────────────────────

export default function PatientChatPage({ patientId: propPatientId }) {
  const params = useParams();
  const patientId = propPatientId || params.patientId;
  const navigate = useNavigate();
  const { doctorId } = useDoctorStore();
  const {
    getPatientChat,
    fetchDrafts,
    replyToPatient,
    editDraft,
    sendDraft,
    getPatients,
  } = useApi();

  const [patient, setPatient] = useState(null);
  const [messages, setMessages] = useState([]);
  const [drafts, setDrafts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [replyText, setReplyText] = useState("");
  const [editingDraft, setEditingDraft] = useState(null);

  const bottomRef = useRef(null);
  const hasScrolledRef = useRef(false);

  useScrollOnKeyboard(bottomRef);

  // ── Load patient info ──────────────────────────────────────────
  useEffect(() => {
    if (!patientId || !doctorId) return;
    getPatients(doctorId, {}, 200)
      .then((data) => {
        const items = Array.isArray(data) ? data : data?.items || [];
        const found = items.find((p) => String(p.id) === String(patientId));
        setPatient(found || { id: patientId, name: "患者" });
      })
      .catch(() => setPatient({ id: patientId, name: "患者" }));
  }, [patientId, doctorId]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Load messages ──────────────────────────────────────────────
  const refreshMessages = useCallback(async () => {
    if (!patientId || !doctorId) return;
    const data = await getPatientChat(patientId, doctorId);
    const msgs = Array.isArray(data?.messages) ? data.messages : [];
    msgs.sort((a, b) => (a.created_at || "").localeCompare(b.created_at || ""));
    setMessages(msgs);
  }, [patientId, doctorId, getPatientChat]);

  // ── Load drafts ────────────────────────────────────────────────
  const refreshDrafts = useCallback(async () => {
    if (!patientId || !doctorId) return;
    const data = await fetchDrafts(doctorId, { patientId });
    const all = Array.isArray(data) ? data : data?.pending_messages || [];
    const actual = all.filter((d) => d.type === "draft");
    actual.sort((a, b) => (a.created_at || "").localeCompare(b.created_at || ""));
    setDrafts(actual);
  }, [patientId, doctorId, fetchDrafts]);

  // ── Initial load ───────────────────────────────────────────────
  useEffect(() => {
    if (!patientId || !doctorId) return;
    setLoading(true);
    Promise.allSettled([refreshMessages(), refreshDrafts()]).finally(() =>
      setLoading(false)
    );
  }, [patientId, doctorId, refreshMessages, refreshDrafts]);

  // ── Scroll to bottom on new messages ──────────────────────────
  useEffect(() => {
    if (!bottomRef.current) return;
    bottomRef.current.scrollIntoView({
      behavior: hasScrolledRef.current ? "smooth" : "auto",
    });
    hasScrolledRef.current = true;
  }, [messages, drafts]);

  // ── Build draft lookup by source_message_id ────────────────────
  const messageIdSet = new Set(messages.map((m) => m.id));
  const pendingDrafts = drafts.filter(
    (d) => d.status !== "sent" && (d.draft_text || d.content)
  );
  const draftByMsgId = {};
  for (const d of pendingDrafts) {
    if (d.source_message_id && messageIdSet.has(d.source_message_id)) {
      draftByMsgId[d.source_message_id] = d;
    }
  }

  // ── Handlers ──────────────────────────────────────────────────
  async function handleSend(text) {
    const trimmed = (text || replyText).trim();
    if (!trimmed || sending) return;
    setSending(true);
    try {
      if (editingDraft) {
        await editDraft(editingDraft.id, doctorId, trimmed);
        await sendDraft(editingDraft.id, doctorId);
        setEditingDraft(null);
      } else {
        await replyToPatient(patientId, trimmed);
      }
      setReplyText("");
      await Promise.allSettled([refreshMessages(), refreshDrafts()]);
    } catch (e) {
      Toast.show({ content: `发送失败：${e.message}`, position: "bottom" });
    } finally {
      setSending(false);
    }
  }

  function handleEditDraft(draft) {
    setEditingDraft(draft);
    setReplyText(draft.draft_text || draft.content || "");
  }

  async function handleDraftSend(draft) {
    if (!draft?.id) return;
    setSending(true);
    try {
      await sendDraft(draft.id, doctorId);
      await Promise.allSettled([refreshMessages(), refreshDrafts()]);
    } catch (e) {
      Toast.show({ content: `发送失败：${e.message}`, position: "bottom" });
    } finally {
      setSending(false);
    }
  }

  function handleBack() {
    // Return to patient detail (records page) — strip ?view=chat
    navigate(`/doctor/patients/${patientId}`, { replace: true });
  }

  const patientName = patient?.name || "患者";

  // ── Render ─────────────────────────────────────────────────────
  return (
    <div style={keyboardAwareStyle}>
      {/* NavBar */}
      <NavBar
        backArrow={<LeftOutline />}
        onBack={handleBack}
        style={{
          "--height": "44px",
          "--border-bottom": `0.5px solid ${APP.border}`,
          backgroundColor: APP.surface,
          flexShrink: 0,
        }}
      >
        {patientName}
      </NavBar>

      {/* Messages area */}
      <div style={msgAreaStyle}>
        {loading && (
          <div style={styles.center}>
            <SpinLoading color="primary" style={{ "--size": "24px" }} />
          </div>
        )}

        {!loading && messages.length === 0 && pendingDrafts.length === 0 && (
          <div style={styles.emptyHint}>暂无消息</div>
        )}

        {messages.map((msg) => {
          const inlineDraft = draftByMsgId[msg.id];
          return (
            <div key={msg.id || msg.created_at}>
              <MessageBubble msg={msg} patientName={patientName} />
              {inlineDraft && (
                <AIDraftCard
                  draft={inlineDraft}
                  onEdit={handleEditDraft}
                  onSend={handleDraftSend}
                />
              )}
            </div>
          );
        })}

        {/* Orphan drafts (no matching source message) */}
        {pendingDrafts
          .filter((d) => !d.source_message_id || !messageIdSet.has(d.source_message_id))
          .map((draft) => (
            <AIDraftCard
              key={draft.id}
              draft={draft}
              onEdit={handleEditDraft}
              onSend={handleDraftSend}
            />
          ))}

        <div ref={bottomRef} />
      </div>

      {/* Edit draft banner */}
      {editingDraft && (
        <EditingBanner
          onCancel={() => {
            setEditingDraft(null);
            setReplyText("");
          }}
        />
      )}

      {/* Chat composer */}
      <ChatComposer
        value={replyText}
        onChange={setReplyText}
        onSend={handleSend}
        disabled={sending}
        placeholder={editingDraft ? "编辑回复内容..." : "直接回复患者..."}
        doctorId={doctorId}
      />
    </div>
  );
}

// ── Styles ─────────────────────────────────────────────────────────

const msgAreaStyle = {
  flex: 1,
  overflowY: "auto",
  display: "flex",
  flexDirection: "column",
  gap: 4,
  paddingTop: 12,
  paddingBottom: 8,
  background: APP.surfaceAlt,
};

const styles = {
  center: {
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    padding: "40px 0",
  },
  emptyHint: {
    textAlign: "center",
    padding: "48px 16px",
    fontSize: FONT.main,
    color: APP.text4,
  },
};
