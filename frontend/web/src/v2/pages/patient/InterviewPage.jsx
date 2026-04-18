/**
 * InterviewPage — full-screen pre-consultation interview (v2, antd-mobile).
 *
 * Ported from src/pages/patient/InterviewPage.jsx.
 * Key behaviours preserved:
 *   - Session lifecycle: start → turns → confirm/cancel
 *   - Suggestion chips (ChatComposer built-in support)
 *   - Selected-chip tokens combined with typed text before send
 *   - Progress bar + % display in NavBar
 *   - Summary sheet with field checklist
 *   - Exit dialog (save vs abandon)
 *   - keyboardAwareStyle + useScrollOnKeyboard
 */

import { useEffect, useRef, useState } from "react";
import { NavBar, ProgressBar, Button, SpinLoading, Dialog, Toast } from "antd-mobile";
import { CheckCircleFill, CloseCircleOutline } from "antd-mobile-icons";
import { usePatientApi } from "../../../api/PatientApiContext";
import ChatBubble from "../../ChatBubble";
import ChatComposer from "../../ChatComposer";
import { keyboardAwareStyle, useScrollOnKeyboard } from "../../keyboard";
import { APP, FONT, RADIUS } from "../../theme";

const FIELD_LABELS = {
  chief_complaint: "主诉",
  present_illness: "现病史",
  past_history: "既往史",
  allergy_history: "过敏史",
  family_history: "家族史",
  personal_history: "个人史",
  marital_reproductive: "婚育史",
};

const ALL_FIELDS = [
  "chief_complaint",
  "present_illness",
  "past_history",
  "allergy_history",
  "family_history",
  "personal_history",
  "marital_reproductive",
];

// ---------------------------------------------------------------------------
// Summary sheet (inline popup)
// ---------------------------------------------------------------------------

function SummarySheet({ collected, status, confirming, onResumeInput, onConfirm, onClose }) {
  return (
    <div style={summaryStyles.overlay} onClick={onClose}>
      <div style={summaryStyles.sheet} onClick={(e) => e.stopPropagation()}>
        <div style={summaryStyles.header}>已收集信息</div>
        <div style={summaryStyles.body}>
          {ALL_FIELDS.map((f) => {
            const val = collected[f];
            return (
              <div key={f} style={summaryStyles.fieldRow}>
                <span style={{ color: val ? APP.primary : APP.border, marginRight: 6, fontSize: FONT.main }}>
                  {val ? <CheckCircleFill style={{ fontSize: FONT.main }} /> : <CloseCircleOutline style={{ fontSize: FONT.main }} />}
                </span>
                <div>
                  <div style={{ fontSize: FONT.sm, color: APP.text4 }}>{FIELD_LABELS[f]}</div>
                  {val && (
                    <div style={{ fontSize: FONT.md, color: APP.text1, marginTop: 2 }}>{val}</div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
        <div style={summaryStyles.footer}>
          <Button
            block
            style={summaryStyles.resumeBtn}
            onClick={onResumeInput}
          >
            继续补充
          </Button>
          {status === "reviewing" && (
            <Button
              block
              color="primary"
              style={summaryStyles.confirmBtn}
              loading={confirming}
              disabled={confirming}
              onClick={onConfirm}
            >
              确认提交
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}

const summaryStyles = {
  overlay: {
    position: "absolute",
    inset: 0,
    background: "rgba(0,0,0,0.4)",
    display: "flex",
    flexDirection: "column",
    justifyContent: "flex-end",
    zIndex: 200,
  },
  sheet: {
    background: APP.surface,
    borderRadius: `${RADIUS.xl}px ${RADIUS.xl}px 0 0`,
    maxHeight: "75vh",
    display: "flex",
    flexDirection: "column",
  },
  header: {
    padding: "16px 16px 8px",
    fontSize: 16,
    fontWeight: 600,
    color: APP.text1,
    borderBottom: `1px solid ${APP.border}`,
    flexShrink: 0,
  },
  body: {
    flex: 1,
    overflowY: "auto",
    padding: "12px 16px",
    display: "flex",
    flexDirection: "column",
    gap: 14,
  },
  fieldRow: {
    display: "flex",
    alignItems: "flex-start",
  },
  footer: {
    padding: "12px 16px",
    display: "flex",
    flexDirection: "column",
    gap: 8,
    flexShrink: 0,
    borderTop: `1px solid ${APP.border}`,
  },
  resumeBtn: {
    background: APP.surfaceAlt,
    border: "none",
    color: APP.text1,
  },
  confirmBtn: {
    marginTop: 0,
  },
};

// ---------------------------------------------------------------------------
// InterviewPage — main export
// ---------------------------------------------------------------------------

export default function InterviewPage({ token, onBack }) {
  const { interviewStart, interviewTurn, interviewConfirm, interviewCancel } =
    usePatientApi();

  const [sessionId, setSessionId] = useState("");
  const [messages, setMessages] = useState([]);
  const [collected, setCollected] = useState({});
  const [progress, setProgress] = useState({ filled: 0, total: 7 });
  const [status, setStatus] = useState("interviewing");
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [showSummary, setShowSummary] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [suggestions, setSuggestions] = useState(() => {
    const params = new URLSearchParams(window.location.search);
    const starter = params.get("starter_suggestions");
    return starter
      ? starter
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean)
      : [];
  });
  const [selectedSuggestions, setSelectedSuggestions] = useState([]);
  const [reviewReady, setReviewReady] = useState(false);
  const [reviewHintShown, setReviewHintShown] = useState(false);

  const chatEndRef = useRef(null);
  useScrollOnKeyboard(chatEndRef);

  const canSupplement = reviewReady && status !== "confirmed";
  const canInput = status === "interviewing" || canSupplement;

  // Start session
  useEffect(() => {
    (async () => {
      try {
        const data = await interviewStart(token);
        setSessionId(data.session_id);
        setCollected(data.collected || {});
        setProgress(data.progress);
        setStatus(data.status);
        setMessages([{ role: "assistant", content: data.reply }]);
        if (data.ready_to_review || data.status === "reviewing") {
          setReviewReady(true);
          if (!reviewHintShown) {
            setReviewHintShown(true);
            setTimeout(() => setShowSummary(true), 300);
          }
        }
      } catch (err) {
        if (err?.status === 401) console.warn("auth expired");
        setMessages([{ role: "assistant", content: "无法启动问诊，请稍后重试。" }]);
      }
    })();
  }, [token]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  function handleToggleSuggestion(text) {
    setSelectedSuggestions((prev) =>
      prev.includes(text) ? prev.filter((s) => s !== text) : [...prev, text]
    );
  }

  async function handleSend(typedText) {
    const parts = [...selectedSuggestions];
    if (typedText?.trim()) parts.push(typedText.trim());
    const text = parts.join("，");
    if (!text || sending || !canInput) return;

    setInput("");
    setSuggestions([]);
    setSelectedSuggestions([]);
    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setSending(true);

    try {
      const data = await interviewTurn(token, sessionId, text);
      setMessages((prev) => [...prev, { role: "assistant", content: data.reply }]);
      setCollected(data.collected || {});
      setProgress(data.progress);
      setStatus(data.status);
      setSuggestions(data.suggestions || []);
      setSelectedSuggestions([]);
      if (data.ready_to_review || data.status === "reviewing") {
        setReviewReady(true);
        if (!reviewHintShown) {
          setReviewHintShown(true);
          setTimeout(() => setShowSummary(true), 800);
        }
      }
    } catch (err) {
      if (err?.status === 401) return;
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: "系统暂时繁忙，请重新发送您的回答。" },
      ]);
    } finally {
      setSending(false);
    }
  }

  async function handleConfirm() {
    setConfirming(true);
    try {
      const data = await interviewConfirm(token, sessionId);
      setStatus("confirmed");
      setShowSummary(false);
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: data.message },
      ]);
    } catch (err) {
      if (err?.status === 401) return;
      Toast.show({ content: "提交失败，请稍后重试。", position: "center" });
    } finally {
      setConfirming(false);
    }
  }

  async function handleBackPress() {
    if (status === "confirmed") {
      onBack();
      return;
    }
    const result = await Dialog.confirm({
      title: "退出问诊",
      content: "您要保存进度还是重新开始？",
      cancelText: "保存退出",
      confirmText: "放弃重来",
    });
    // Dialog.confirm resolves true=confirm (放弃重来), false/catch=cancel (保存退出)
    if (result) {
      try {
        await interviewCancel(token, sessionId);
      } catch {}
    }
    onBack();
  }

  function handleResumeInput() {
    setShowSummary(false);
    setStatus("interviewing");
  }

  const progressPct = progress.total
    ? Math.round((progress.filled / progress.total) * 100)
    : 0;

  return (
    <div style={{ ...pageStyle, position: "relative" }}>
      {/* NavBar */}
      <NavBar
        onBack={handleBackPress}
        right={
          status !== "confirmed" ? (
            <span
              style={{
                fontSize: FONT.main,
                color: reviewReady ? APP.primary : APP.text4,
                fontWeight: reviewReady ? 600 : 400,
                cursor: reviewReady ? "pointer" : "default",
              }}
              onClick={reviewReady ? () => setShowSummary(true) : undefined}
            >
              {reviewReady ? "提交" : `${progressPct}%`}
            </span>
          ) : null
        }
        style={{
          "--height": "44px",
          background: APP.surface,
          borderBottom: `1px solid ${APP.border}`,
          flexShrink: 0,
        }}
      >
        新建病历
      </NavBar>

      {/* Progress bar */}
      <div style={styles.progressWrap}>
        <ProgressBar
          percent={progressPct}
          style={{ "--fill-color": APP.primary, "--track-color": APP.border }}
        />
        <div style={styles.progressLabel}>{progressPct}%</div>
      </div>

      {/* Chat messages */}
      <div style={styles.chatArea}>
        {messages.map((msg, i) => (
          <div key={i} style={{ marginBottom: 12 }}>
            <ChatBubble role={msg.role === "user" ? "user" : "assistant"} content={msg.content} />
          </div>
        ))}
        {sending && (
          <div style={{ paddingLeft: 44, paddingBottom: 8 }}>
            <SpinLoading color={APP.primary} style={{ "--size": "20px" }} />
          </div>
        )}
        <div ref={chatEndRef} />
      </div>

      {/* Input (hidden when confirmed) */}
      {canInput && (
        <ChatComposer
          value={input}
          onChange={setInput}
          onSend={(text) => {
            setInput("");
            handleSend(text);
          }}
          disabled={sending}
          placeholder="请输入…"
          suggestions={suggestions}
          selectedSuggestions={selectedSuggestions}
          onToggleSuggestion={handleToggleSuggestion}
        />
      )}

      {status === "confirmed" && (
        <div style={styles.confirmedBar}>
          <Button
            color="primary"
            block
            onClick={onBack}
            style={{ maxWidth: 200 }}
          >
            返回病历
          </Button>
        </div>
      )}

      {/* Summary overlay */}
      {showSummary && (
        <SummarySheet
          collected={collected}
          status={status}
          confirming={confirming}
          onResumeInput={handleResumeInput}
          onConfirm={handleConfirm}
          onClose={handleResumeInput}
        />
      )}
    </div>
  );
}

const pageStyle = {
  display: "flex",
  flexDirection: "column",
  height: "100%",
  overflow: "hidden",
  background: APP.surfaceAlt,
};

const styles = {
  progressWrap: {
    padding: "6px 16px 4px",
    background: APP.surface,
    borderBottom: `1px solid ${APP.borderLight}`,
    flexShrink: 0,
  },
  progressLabel: {
    fontSize: 11,
    color: APP.text4,
    marginTop: 3,
  },
  chatArea: {
    flex: 1,
    overflowY: "auto",
    padding: "12px 0",
  },
  confirmedBar: {
    padding: "12px 16px",
    background: APP.surfaceAlt,
    borderTop: `1px solid ${APP.border}`,
    display: "flex",
    justifyContent: "center",
    flexShrink: 0,
  },
};
