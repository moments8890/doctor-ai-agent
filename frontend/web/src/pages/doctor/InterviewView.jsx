/**
 * 病历采集视图：医生输入患者信息，AI提取字段并跟踪进度。
 * 显示在患者列表右侧（替代患者详情面板）。
 */
import { useEffect, useRef, useState } from "react";
import { Alert, Box, Button, CircularProgress, IconButton, Stack, Typography } from "@mui/material";
import SendOutlinedIcon from "@mui/icons-material/SendOutlined";
import SmartToyOutlinedIcon from "@mui/icons-material/SmartToyOutlined";
import LocalHospitalOutlinedIcon from "@mui/icons-material/LocalHospitalOutlined";
import { doctorInterviewTurn, doctorInterviewConfirm, doctorInterviewCancel } from "../../api";
import SubpageHeader from "./SubpageHeader";

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
        {isUser ? <LocalHospitalOutlinedIcon sx={{ color: "#fff", fontSize: 18 }} />
                : <SmartToyOutlinedIcon sx={{ color: "#fff", fontSize: 18 }} />}
      </Box>
      <Box sx={{ maxWidth: "75%", px: 1.5, py: 1, borderRadius: isUser ? "4px 4px 0 4px" : "4px 4px 4px 0",
        bgcolor: isUser ? "#95EC69" : "#fff", fontSize: 14, whiteSpace: "pre-wrap", lineHeight: 1.7 }}>
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
  const bottomRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);
  useEffect(() => { inputRef.current?.focus(); }, []);

  async function handleSend() {
    const text = input.trim();
    if (!text || loading) return;

    setMessages(prev => [...prev, { role: "user", content: text, ts: nowTs() }]);
    setInput("");
    setLoading(true);
    setError(null);

    try {
      const formData = new FormData();
      formData.append("text", text);
      formData.append("doctor_id", doctorId);

      if (!session.sessionId) {
        // First turn — extract patient name from text
        const name = text.split(/[，,\s]/)[0].replace(/[新患者创建建立]/g, "").trim();
        formData.append("patient_name", name || text.substring(0, 10));
      } else {
        formData.append("session_id", session.sessionId);
      }

      const data = await doctorInterviewTurn(formData);

      setSession({
        sessionId: data.session_id,
        progress: data.progress,
        status: data.status,
        patientId: data.patient_id,
      });

      setMessages(prev => [...prev, { role: "assistant", content: data.reply, ts: nowTs() }]);
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
          {session.progress.filled}/{session.progress.total}
        </Typography>} />

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

      {/* Progress + confirm bar */}
      {session.status === "ready_for_confirm" && (
        <Box sx={{ px: 1.5, py: 1, borderTop: "1px solid #e0e0e0", bgcolor: "#f0f9f0",
          display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <Typography variant="caption" sx={{ color: "#2e7d32", fontWeight: 500 }}>
            必填已完成，可以生成初步病历了
          </Typography>
          <Button size="small" variant="contained" disableElevation
            sx={{ bgcolor: "#07C160", "&:hover": { bgcolor: "#06ad56" }, fontSize: 12 }}
            onClick={handleConfirm} disabled={loading}>
            确认生成
          </Button>
        </Box>
      )}

      {session.status === "draft_created" && (
        <Box sx={{ px: 1.5, py: 1, borderTop: "1px solid #e0e0e0", bgcolor: "#f0f9f0",
          display: "flex", alignItems: "center", justifyContent: "center" }}>
          <Typography variant="caption" sx={{ color: "#2e7d32" }}>
            草稿已生成
          </Typography>
        </Box>
      )}

      {/* Input bar */}
      {session.status !== "draft_created" && (
        <Box sx={{ borderTop: "1px solid #d9d9d9", bgcolor: "#f5f5f5", px: 1, py: 0.8,
          display: "flex", alignItems: "center", gap: 0.5 }}>
          <Box sx={{ flex: 1, bgcolor: "#fff", borderRadius: "4px", px: 1.2, py: 0.8 }}>
            <Box component="input" ref={inputRef} value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={loading}
              placeholder="输入患者信息..."
              sx={{ width: "100%", border: "none", outline: "none", fontSize: 14, fontFamily: "inherit",
                bgcolor: "transparent", p: 0 }}
            />
          </Box>
          <IconButton onClick={handleSend} disabled={loading || !input.trim()}
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
