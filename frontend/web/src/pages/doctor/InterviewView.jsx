/**
 * 病历采集视图：医生输入患者信息，AI提取字段并跟踪进度。
 * 显示在患者列表右侧（替代患者详情面板）。
 */
import { useEffect, useRef, useState } from "react";
import { Alert, Box, Button, CircularProgress, IconButton, LinearProgress, Stack, Typography } from "@mui/material";
import SendOutlinedIcon from "@mui/icons-material/SendOutlined";
import SmartToyOutlinedIcon from "@mui/icons-material/SmartToyOutlined";
import LocalHospitalOutlinedIcon from "@mui/icons-material/LocalHospitalOutlined";
import { doctorInterviewTurn, doctorInterviewConfirm, doctorInterviewCancel, doctorInterviewGetSession, confirmCarryForward } from "../../api";
import SubpageHeader from "./SubpageHeader";
import SuggestionChips from "../../components/SuggestionChips";
import CarryForwardCard from "./CarryForwardCard";
import { TYPE, ICON } from "../../theme";

function nowTs() {
  const d = new Date();
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

function MsgBubble({ msg }) {
  const isUser = msg.role === "user";
  return (
    <Box sx={{ display: "flex", flexDirection: isUser ? "row-reverse" : "row", alignItems: "flex-end", gap: 1, px: 1.5 }}>
      <Box sx={{ width: 32, height: 32, borderRadius: "4px", bgcolor: isUser ? "#5b9bd5" : "#07C160",
        display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
        {isUser ? <LocalHospitalOutlinedIcon sx={{ color: "#fff", fontSize: ICON.md }} />
                : <SmartToyOutlinedIcon sx={{ color: "#fff", fontSize: ICON.md }} />}
      </Box>
      <Box sx={{ maxWidth: "75%", px: 1.5, py: 1, borderRadius: isUser ? "4px 4px 0 4px" : "4px 4px 4px 0",
        bgcolor: isUser ? "#95EC69" : "#fff", fontSize: TYPE.body.fontSize, whiteSpace: "pre-wrap", lineHeight: 1.7 }}>
        {msg.content}
      </Box>
    </Box>
  );
}

export default function InterviewView({ doctorId, sessionId: resumeSessionId, onComplete, onCancel }) {
  const [messages, setMessages] = useState([{
    role: "assistant",
    content: "病历采集模式已开启。\n请输入患者信息（姓名、性别、年龄、症状等），我会帮您结构化记录。",
    ts: nowTs(),
  }]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [session, setSession] = useState({
    sessionId: resumeSessionId || null,
    progress: { filled: 0, total: 7 },
    status: "interviewing",
    patientId: null,
  });
  const [error, setError] = useState(null);
  const [suggestions, setSuggestions] = useState([]);
  const [selectedSuggestions, setSelectedSuggestions] = useState([]);
  const [carryForward, setCarryForward] = useState([]);
  const bottomRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);
  useEffect(() => { inputRef.current?.focus(); }, []);

  // Resume existing session from chat — load collected data and show progress
  useEffect(() => {
    if (!resumeSessionId) return;
    (async () => {
      try {
        const data = await doctorInterviewGetSession(resumeSessionId, doctorId);
        setSession({
          sessionId: data.session_id,
          progress: data.progress,
          status: data.status,
          patientId: data.patient_id,
        });
        // Show full conversation history from the session
        if (data.conversation && data.conversation.length > 0) {
          setMessages(data.conversation.map(turn => ({
            role: turn.role,
            content: turn.content,
            ts: turn.timestamp ? new Date(turn.timestamp).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" }) : nowTs(),
          })));
        } else if (data.reply) {
          setMessages([{ role: "assistant", content: data.reply, ts: nowTs() }]);
        }
        setSuggestions(data.suggestions || []);
      } catch (err) {
        setError(`会话加载失败：${err.message}`);
      }
    })();
  }, [resumeSessionId, doctorId]); // eslint-disable-line react-hooks/exhaustive-deps

  function handleToggleSuggestion(text) {
    setSelectedSuggestions(prev =>
      prev.includes(text) ? prev.filter(s => s !== text) : [...prev, text]
    );
  }

  async function handleCarryForwardConfirm(field) {
    if (!session.sessionId) return;
    try {
      const data = await confirmCarryForward(session.sessionId, doctorId, field, "confirm");
      setCarryForward(prev => prev.filter(item => item.field !== field));
      setSession(prev => ({
        ...prev,
        progress: data.progress,
        status: data.status,
      }));
    } catch (err) {
      setError(err.message);
    }
  }

  function handleCarryForwardDismiss(field) {
    setCarryForward(prev => prev.filter(item => item.field !== field));
  }

  async function handleCarryForwardConfirmAll() {
    if (!session.sessionId) return;
    const remaining = [...carryForward];
    for (const item of remaining) {
      try {
        const data = await confirmCarryForward(session.sessionId, doctorId, item.field, "confirm");
        setCarryForward(prev => prev.filter(i => i.field !== item.field));
        setSession(prev => ({
          ...prev,
          progress: data.progress,
          status: data.status,
        }));
      } catch (err) {
        setError(err.message);
        break;
      }
    }
  }

  async function handleSend() {
    const parts = [...selectedSuggestions];
    if (input.trim()) parts.push(input.trim());
    const text = parts.join("，");
    if (!text || loading) return;

    setMessages(prev => [...prev, { role: "user", content: text, ts: nowTs() }]);
    setInput("");
    setSuggestions([]);
    setSelectedSuggestions([]);
    setLoading(true);
    setError(null);

    try {
      const formData = new FormData();
      formData.append("text", text);
      formData.append("doctor_id", doctorId);

      if (session.sessionId) {
        formData.append("session_id", session.sessionId);
      }

      const data = await doctorInterviewTurn(formData);

      setSession({
        sessionId: data.session_id,
        progress: data.progress,
        status: data.status,
        patientId: data.patient_id,
      });

      // Carry-forward items are only returned on the first turn
      if (data.carry_forward && data.carry_forward.length > 0) {
        setCarryForward(data.carry_forward);
      }

      setMessages(prev => [...prev, { role: "assistant", content: data.reply, ts: nowTs() }]);
      setSuggestions(data.suggestions || []);
      setSelectedSuggestions([]);
    } catch (err) {
      setError(err.message);
      setMessages(prev => [...prev, { role: "assistant", content: `出错：${err.message}`, ts: nowTs() }]);
    } finally {
      setLoading(false);
    }
  }

  async function handleConfirm() {
    if (!session.sessionId) return;
    setLoading(true);
    try {
      const data = await doctorInterviewConfirm(session.sessionId, doctorId);
      setMessages(prev => [...prev, {
        role: "assistant",
        content: data.preview
          ? `病历草稿已生成：\n\n${data.preview}\n\n请在聊天中确认保存。`
          : "病历草稿已生成，请在聊天中确认保存。",
        ts: nowTs(),
      }]);
      setSession(prev => ({ ...prev, status: "draft_created" }));
      onComplete?.(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function handleCancel() {
    if (session.sessionId) {
      try { await doctorInterviewCancel(session.sessionId, doctorId); } catch {}
    }
    onCancel?.();
  }

  function handleKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      handleSend();
    }
  }

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <SubpageHeader title="新建病历" onBack={handleCancel}
        right={<Typography variant="caption" sx={{ color: "#07C160", fontWeight: 500 }}>
          {session.progress.pct || 0}%
        </Typography>} />

      {/* Progress bar + confirm */}
      <Box sx={{ px: 1.5, py: 0.5, bgcolor: "#fff", borderBottom: "1px solid #e0e0e0" }}>
        <LinearProgress variant="determinate"
          value={session.progress.pct || 0}
          sx={{ height: 6, borderRadius: 3, bgcolor: "#e0e0e0",
            "& .MuiLinearProgress-bar": { bgcolor: "#07C160", borderRadius: 3 } }} />
        <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", mt: 0.3 }}>
          <Typography variant="caption" sx={{ color: session.status === "ready_for_confirm" ? "#2e7d32" : "#999" }}>
            {session.status === "ready_for_confirm" ? "信息已完整，可以生成病历了" :
             session.sessionId ? `${session.progress.pct || 0}%` : ""}
          </Typography>
          {session.sessionId && session.status !== "draft_created" && (
            <Button size="small"
              variant={session.status === "ready_for_confirm" ? "contained" : "text"}
              disableElevation
              sx={session.status === "ready_for_confirm"
                ? { bgcolor: "#07C160", "&:hover": { bgcolor: "#06ad56" }, fontSize: TYPE.caption.fontSize, py: 0, minHeight: 24 }
                : { color: "#999", fontSize: TYPE.caption.fontSize, py: 0, minHeight: 24 }
              }
              onClick={handleConfirm} disabled={loading}>
              确认生成
            </Button>
          )}
        </Box>
      </Box>

      {/* Carry-forward card — prior record fields for one-tap confirmation */}
      {carryForward.length > 0 && session.status !== "draft_created" && (
        <CarryForwardCard
          items={carryForward}
          onConfirm={handleCarryForwardConfirm}
          onDismiss={handleCarryForwardDismiss}
          onConfirmAll={handleCarryForwardConfirmAll}
          disabled={loading}
        />
      )}

      {/* Messages */}
      <Box sx={{ flex: 1, overflowY: "auto", py: 2, display: "flex", flexDirection: "column", gap: 1.4, bgcolor: "#ededed" }}>
        {messages.map((msg, idx) => <MsgBubble key={idx} msg={msg} />)}
        {loading && (
          <Box sx={{ display: "flex", alignItems: "center", gap: 1, px: 2 }}>
            <CircularProgress size={14} />
            <Typography variant="caption" color="text.secondary">处理中...</Typography>
          </Box>
        )}
        <div ref={bottomRef} />
      </Box>


      {session.status === "draft_created" && (
        <Box sx={{ px: 1.5, py: 1, borderTop: "1px solid #e0e0e0", bgcolor: "#f0f9f0",
          display: "flex", alignItems: "center", justifyContent: "center" }}>
          <Typography variant="caption" sx={{ color: "#2e7d32" }}>
            草稿已生成
          </Typography>
        </Box>
      )}

      {/* Missing field hints — derived from progress.fields, capped by viewport */}
      {session.status !== "draft_created" && !loading && (() => {
        const fields = session.progress?.fields || {};
        const empty = Object.entries(fields)
          .filter(([, f]) => f.status === "empty")
          .map(([, f]) => f.label);
        if (empty.length === 0) return null;
        return (
          <Box sx={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 0.5,
            px: 1.5, py: 0.6, borderTop: "1px solid #e0e0e0", bgcolor: "#f7f7f7" }}>
            <Typography variant="caption" sx={{ color: "#999", mr: 0.5, flexShrink: 0 }}>待补充：</Typography>
            {empty.map((text, i) => (
              <Box key={i} sx={{
                display: { xs: i >= 3 ? "none" : "inline-flex", md: i >= 5 ? "none" : "inline-flex" },
                px: 1, py: 0.3, borderRadius: "12px",
                fontSize: "12px", bgcolor: "#fff3e0", color: "#e65100", border: "1px solid #ffe0b2" }}>
                {text}
              </Box>
            ))}
            {empty.length > 3 && (
              <Typography variant="caption" sx={{ color: "#999", display: { xs: "inline", md: "none" } }}>
                +{empty.length - 3}
              </Typography>
            )}
            {empty.length > 5 && (
              <Typography variant="caption" sx={{ color: "#999", display: { xs: "none", md: "inline" } }}>
                +{empty.length - 5}
              </Typography>
            )}
          </Box>
        );
      })()}

      {/* LLM suggestions — clickable chips (carry-forward from prior records, etc.) */}
      {session.status !== "draft_created" && !loading && suggestions.length > 0 && (
        <SuggestionChips
          items={suggestions}
          selected={selectedSuggestions}
          onToggle={handleToggleSuggestion}
          onDismiss={() => setSuggestions([])}
          disabled={loading}
        />
      )}

      {/* Input bar */}
      {session.status !== "draft_created" && (
        <Box sx={{ borderTop: "1px solid #d9d9d9", bgcolor: "#f5f5f5", px: 1, py: 0.8,
          display: "flex", alignItems: "flex-end", gap: 0.5 }}>
          <Box sx={{ flex: 1, bgcolor: "#fff", borderRadius: "4px", px: 1, py: 0.5,
            display: "flex", flexWrap: "wrap", alignItems: "center", gap: 0.5, minHeight: 36 }}>
            {selectedSuggestions.map((s, i) => (
              <Box key={i} sx={{
                display: "inline-flex", alignItems: "center", gap: 0.3,
                px: 1, py: 0.2, borderRadius: "12px", fontSize: TYPE.secondary.fontSize,
                bgcolor: "#e8f5e9", color: "#07C160", fontWeight: 500,
                flexShrink: 0,
              }}>
                {s}
                <Box component="span"
                  onClick={() => setSelectedSuggestions(prev => prev.filter(x => x !== s))}
                  sx={{ cursor: "pointer", fontSize: TYPE.body.fontSize, lineHeight: 1, ml: 0.2, "&:active": { opacity: 0.5 } }}>
                  ×
                </Box>
              </Box>
            ))}
            <Box component="input" ref={inputRef} value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={loading}
              placeholder={selectedSuggestions.length > 0 ? "" : "输入患者信息..."}
              sx={{ flex: 1, minWidth: 60, border: "none", outline: "none", fontSize: TYPE.body.fontSize, fontFamily: "inherit",
                bgcolor: "transparent", p: 0.3 }}
            />
          </Box>
          <IconButton onClick={() => handleSend()} disabled={loading || (!input.trim() && selectedSuggestions.length === 0)}
            sx={{ bgcolor: "#07C160", color: "#fff", p: 1, borderRadius: "50%",
              "&:hover": { bgcolor: "#06ad56" }, "&.Mui-disabled": { bgcolor: "#ccc", color: "#fff" } }}>
            <SendOutlinedIcon fontSize="small" />
          </IconButton>
        </Box>
      )}

      {error && <Alert severity="error" onClose={() => setError(null)} sx={{ mx: 1, mb: 0.5 }}>{error}</Alert>}
    </Box>
  );
}
