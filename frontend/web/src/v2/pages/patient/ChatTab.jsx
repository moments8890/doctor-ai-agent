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

import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Dialog, SpinLoading, Toast } from "antd-mobile";
import { usePatientApi } from "../../../api/PatientApiContext";
import ChatBubble from "../../ChatBubble";
import ChatConfirmGate from "../../components/ChatConfirmGate";
import ChatDedupPrompt from "../../components/ChatDedupPrompt";
import IntakeBanner from "../../components/IntakeBanner";
import IntakeSubmitPopup from "../../components/IntakeSubmitPopup";
import CollapsedIntakeCard from "../../components/CollapsedIntakeCard";
import ChatComposer from "../../ChatComposer";
import { groupPastIntakes } from "../../intake/groupMessages";
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

// Stable key for chat messages. Local optimistic messages have no id;
// without prefixing, their fallback `i` collides with a polled msg whose
// real db id equals that index (e.g. local at i=29 vs polled msg.id=29).
function msgKey(msg, i) {
  if (msg?.id !== undefined && msg?.id !== null) return `db-${msg.id}`;
  if (msg?._ts) return `local-${msg._ts}`;
  return `idx-${i}`;
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
  const {
    getPatientChatMessages,
    sendPatientChat,
    confirmPatientChatDraft,
    dedupDecisionPatientChat,
    getIntakeStatus,
    cancelIntake,
    confirmIntake,
  } = usePatientApi();

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
  // Field names whose carried-forward values still need patient confirmation
  // (server-supplied via POST /chat + GET /chat/intake/status). Drives
  // banner progress: unconfirmed CF values render as "待采集" so progress
  // starts at 0/6 and increments only as the patient confirms each.
  const [unconfirmedCarryForward, setUnconfirmedCarryForward] = useState([]);
  // status string: "active" | "reviewing" | null — drives the 提交给医生
  // button on IntakeBanner. session_id needed to call confirmIntake().
  const [intakeStatus, setIntakeStatus] = useState(null);
  const [intakeSessionId, setIntakeSessionId] = useState(null);
  const [submitOpen, setSubmitOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  // session_id → "active" | "reviewing" | "confirmed" | "abandoned" | "expired".
  // Drives groupConfirmedIntakes() — only "confirmed" sessions collapse.
  // Local-only: built up from POST /chat responses + the on-confirm flip.
  const [sessionStatusMap, setSessionStatusMap] = useState({});
  // suggestions[lastAiMsgId] = chip text array; rendered above the
  // composer. Cleared when the patient sends another turn.
  const [latestSuggestions, setLatestSuggestions] = useState([]);
  const chatEndRef = useRef(null);
  const pollingRef = useRef(null);
  const visibleRef = useRef(true);
  useScrollOnKeyboard(chatEndRef);

  // On mount/reload, restore the IntakeBanner state from the backend so
  // the patient sees their in-progress intake without having to send
  // another message first. Silent restore — no modal, no "resume?" ask.
  // The banner itself communicates the active state with progress + 取消.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        if (!getIntakeStatus) return;
        const status = await getIntakeStatus(token);
        if (cancelled) return;
        if (status?.has_active) {
          setIntakeActive(true);
          setIntakeCollected(status.collected || {});
          setUnconfirmedCarryForward(status.unconfirmed_carry_forward || []);
          setIntakeStatus(status.status || "active");
          setIntakeSessionId(status.session_id || null);
          if (status.session_id && status.status) {
            setSessionStatusMap((prev) => ({
              ...prev,
              [status.session_id]: status.status,
            }));
          }
        }
      } catch (err) {
        if (err?.status === 401) return;
        // Non-fatal — banner just won't restore. Patient still sees chat.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token, getIntakeStatus]);

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
              return !newMsgs.some((nm) => {
                const nmSrc = nm.source || (nm.role === "user" ? "patient" : "ai");
                return nmSrc === m.source && nm.content === m.content;
              });
            });
            // Idempotent id-dedup. With two polls overlapping (state update
            // hasn't flushed before the next poll resolves), both callbacks
            // can see a `prev` missing id=125, both append it. Final pass
            // guarantees one row per id no matter what.
            const merged = [...cleaned, ...newMsgs];
            const seen = new Set();
            return merged.filter((m) => {
              if (!m.id) return true;
              if (seen.has(m.id)) return false;
              seen.add(m.id);
              return true;
            });
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
        setUnconfirmedCarryForward(resp.unconfirmed_carry_forward || []);
        setIntakeStatus(resp.status || "active");
        setIntakeSessionId(resp.session_id || null);
        if (resp.session_id && resp.status) {
          setSessionStatusMap((prev) => ({
            ...prev,
            [resp.session_id]: resp.status,
          }));
        }
      } else {
        setIntakeActive(false);
        setIntakeCollected({});
        setUnconfirmedCarryForward([]);
        setIntakeStatus(null);
        setIntakeSessionId(null);
      }
      // Optimistic AI bubble — the reply is already persisted server-side,
      // but the next poll is up to 10s away. Without this the chips render
      // before the message they belong to. Dedup happens on next poll
      // (matches local against polled by source+content).
      if (resp?.reply) {
        setMessages((prev) => [
          ...prev,
          {
            source: "ai",
            content: resp.reply,
            _local: true,
            _ts: Date.now(),
            intake_session_id: resp.session_id || null,
          },
        ]);
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
    Dialog.confirm({
      title: "取消问诊",
      content: "已采集的信息会保留，但问诊将结束。确定取消吗？",
      cancelText: "继续问诊",
      confirmText: "取消问诊",
      onConfirm: async () => {
        // Stamp the just-canceled session as "abandoned" in the local map
        // so its prior messages collapse with the right "已取消问诊" label.
        if (intakeSessionId) {
          setSessionStatusMap((prev) => ({
            ...prev,
            [intakeSessionId]: "abandoned",
          }));
        }
        setIntakeActive(false);
        setIntakeCollected({});
        setUnconfirmedCarryForward([]);
        setIntakeStatus(null);
        setIntakeSessionId(null);
        try {
          await cancelIntake?.(token);
        } catch (err) {
          if (err?.status === 401) return;
          // Non-fatal: 24h decay will close abandoned sessions either way.
          console.warn("cancelIntake failed:", err?.message);
        }
      },
    });
  }

  function handleOpenSubmit() {
    if (!intakeSessionId) return;
    setSubmitOpen(true);
  }

  async function handleSubmitIntake() {
    if (!intakeSessionId || submitting) return;
    setSubmitting(true);
    try {
      const result = await confirmIntake(token, intakeSessionId);
      const recordId = result?.record_id;
      // Mark this session confirmed so any messages tagged with it collapse
      // into a single CollapsedIntakeCard on the next render pass.
      const submittedId = intakeSessionId;
      setSessionStatusMap((prev) => ({ ...prev, [submittedId]: "confirmed" }));
      setSubmitOpen(false);
      setIntakeActive(false);
      setIntakeCollected({});
      setUnconfirmedCarryForward([]);
      setIntakeStatus(null);
      setIntakeSessionId(null);
      // Local system message — the engine writes its own DB record on
      // confirm, but the poller may take up to 10s to surface it. Give
      // immediate feedback. Patient sees this if they navigate back to
      // chat from the record page.
      setMessages((prev) => [
        ...prev,
        {
          source: "system",
          content: "✓ 问诊已提交，医生会尽快查看",
          _local: true,
          _ts: Date.now(),
        },
      ]);
      // Navigate to the freshly-created medical record so the patient
      // can see exactly what got submitted. Defensive: if record_id is
      // missing for any reason, stay on chat — the system message is
      // still visible.
      if (recordId) {
        navigate(`/patient/records/${recordId}`);
      }
    } catch (err) {
      if (err?.status === 401) {
        setSubmitOpen(false);
        return;
      }
      Toast.show({ icon: "fail", content: err?.message || "提交失败，请重试" });
    } finally {
      setSubmitting(false);
    }
  }

  // The most recent AI bubble — used to attach the inline 提交给医生 CTA
  // when the engine has flipped status to "reviewing". Reference is
  // captured by closure so renderMessage can check `msg === lastAiMsg`
  // without depending on render-item indices (which change after the
  // grouping pass).
  const lastAiMsg = (() => {
    for (let i = messages.length - 1; i >= 0; i -= 1) {
      const m = messages[i];
      const src = m.source || (m.role === "user" ? "patient" : "ai");
      if (src === "ai" && !m.kind) return m;
    }
    return null;
  })();

  function renderMessage(msg, i) {
    if (msg.kind === "confirm_gate") {
      return (
        <ChatConfirmGate
          key={msgKey(msg, i)}
          continuity={msg.continuity}
          onConfirm={() => sendConfirmation(msg.draft_id, "confirm")}
          onContinue={() => sendConfirmation(msg.draft_id, "continue")}
        />
      );
    }

    if (msg.kind === "dedup_prompt") {
      return (
        <ChatDedupPrompt
          key={msgKey(msg, i)}
          targetReviewed={msg.target_reviewed}
          onMerge={() => sendDedupDecision(msg.draft_id, "merge")}
          onNew={() => sendDedupDecision(msg.draft_id, "new")}
          onNeither={() => sendDedupDecision(msg.draft_id, "neither")}
        />
      );
    }

    const src = msg.source || (msg.role === "user" ? "patient" : "ai");

    if (src === "doctor") {
      return <DoctorMessage key={msgKey(msg, i)} msg={msg} doctorName={doctorName} />;
    }

    if (src === "system") {
      const parts = (msg.triage_category || "").split(":");
      const linkType = parts[1] || null;
      const linkId = parts[2] || null;
      let onTap = null;
      if (linkType === "record") onTap = () => navigate(`/patient/records/${linkId}`);
      else if (linkType === "task") onTap = () => navigate("/patient/tasks");
      return <SystemMessage key={msgKey(msg, i)} msg={msg} onTap={onTap} />;
    }

    if (src === "patient") {
      return (
        <div style={{ marginBottom: 12 }} key={msgKey(msg, i)}>
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
    // Inline 提交给医生 CTA — attaches to the latest AI bubble whenever the
    // engine has flipped status to reviewing AND the message belongs to
    // the active session. Catches the patient at the natural decision
    // moment without making them notice the top banner button.
    const showSubmitCta = (
      msg === lastAiMsg
      && intakeStatus === "reviewing"
      && intakeSessionId
      && (!msg.intake_session_id || msg.intake_session_id === intakeSessionId)
    );

    return (
      <div key={msgKey(msg, i)} style={{ marginBottom: 12 }}>
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
        {showSubmitCta && (
          <div style={styles.inlineSubmitWrap}>
            <button
              type="button"
              style={styles.inlineSubmitBtn}
              onClick={handleOpenSubmit}
            >
              查看并提交
            </button>
          </div>
        )}
      </div>
    );
  }

  // Build the render list: any past intake (session_id != current active)
  // collapses into a single card; the active session and non-intake
  // messages pass through. Memoized to skip re-walking on keystrokes.
  const renderItems = useMemo(
    () => groupPastIntakes(messages, sessionStatusMap, intakeSessionId),
    [messages, sessionStatusMap, intakeSessionId],
  );

  return (
    <div style={keyboardAwareStyle}>
      {/* Active-intake banner sits above the message list. Hidden when no
          intake is active. When status === "reviewing", the banner shows a
          提交给医生 button that opens IntakeSubmitPopup. */}
      {intakeActive && (
        <IntakeBanner
          collected={intakeCollected}
          status={intakeStatus}
          unconfirmedCarryForward={unconfirmedCarryForward}
          onSubmit={intakeSessionId ? handleOpenSubmit : undefined}
          onCancel={handleCancelIntake}
        />
      )}

      <IntakeSubmitPopup
        open={submitOpen}
        collected={intakeCollected}
        loading={submitting}
        onClose={() => (submitting ? null : setSubmitOpen(false))}
        onSubmit={handleSubmitIntake}
      />

      {/* Message list */}
      <div style={styles.msgList}>
        {renderItems.map((item, i) => {
          if (item.kind === "collapsed_intake") {
            // Same session_id can appear in two non-contiguous runs (split
            // by a doctor reply or system message). Each run becomes its
            // own card; key must include the first message's id (or list
            // index as a backstop) to stay unique across runs.
            const firstId = item.messages[0]?.id;
            const cardKey = `collapsed-${item.session_id}-${firstId ?? `idx${i}`}`;
            return (
              <CollapsedIntakeCard
                key={cardKey}
                messages={item.messages}
                status={item.status}
                renderMessage={renderMessage}
              />
            );
          }
          return renderMessage(item.message, i);
        })}
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
  inlineSubmitWrap: {
    display: "flex",
    justifyContent: "flex-start",
    paddingLeft: 44,
    marginTop: 8,
  },
  inlineSubmitBtn: {
    background: APP.primary,
    color: APP.white,
    border: "none",
    borderRadius: RADIUS.md,
    padding: "8px 16px",
    fontSize: FONT.md,
    fontWeight: 600,
    minHeight: 36,
    cursor: "pointer",
    fontFamily: "inherit",
  },
};
