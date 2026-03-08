import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useDoctorStore } from "../store/doctorStore";
import { setWebToken } from "../api";
import {
  Box,
  Button,
  Chip,
  Divider,
  IconButton,
  Paper,
  Stack,
  TextField,
  Tooltip,
  Typography,
} from "@mui/material";
import SmartToyOutlinedIcon from "@mui/icons-material/SmartToyOutlined";
import PeopleOutlineIcon from "@mui/icons-material/PeopleOutline";
import SendOutlinedIcon from "@mui/icons-material/SendOutlined";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import LogoutIcon from "@mui/icons-material/Logout";
import { sendChat } from "../api";
import RecordFields from "../components/RecordFields";
import { t } from "../i18n";

function MsgBubble({ msg }) {
  const isUser = msg.role === "user";
  return (
    <Box
      sx={{
        display: "flex",
        justifyContent: isUser ? "flex-end" : "flex-start",
        px: 1,
      }}
    >
      <Paper
        elevation={0}
        sx={{
          maxWidth: "min(85%, 720px)",
          p: 1.5,
          borderRadius: 2,
          bgcolor: isUser ? "#eaf4ff" : "#f0faf4",
          border: "1px solid",
          borderColor: isUser ? "#c8def6" : "#c9e8d4",
        }}
      >
        <Typography variant="body2" sx={{ whiteSpace: "pre-wrap", lineHeight: 1.6 }}>
          {msg.content}
        </Typography>
        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.5, textAlign: "right" }}>
          {msg.ts || ""}
        </Typography>
        {!isUser && msg.record ? <RecordFields record={msg.record} /> : null}
      </Paper>
    </Box>
  );
}

export default function ChatPage() {
  const navigate = useNavigate();
  const { doctorId, doctorName, clearAuth } = useDoctorStore();
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [messages, setMessages] = useState([]);
  const bottomRef = useRef(null);

  function nowTs() {
    const d = new Date();
    return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
  }

  function historyKey(id) {
    return `doctor_ai_chat_history:${(id || "anon").trim() || "anon"}`;
  }

  useEffect(() => {
    const raw = localStorage.getItem(historyKey(doctorId));
    if (!raw) { setMessages([{ role: "assistant", content: t("chat.welcome"), ts: nowTs() }]); return; }
    try {
      const parsed = JSON.parse(raw);
      setMessages(Array.isArray(parsed) && parsed.length ? parsed : [{ role: "assistant", content: t("chat.welcome"), ts: nowTs() }]);
    } catch {
      setMessages([{ role: "assistant", content: t("chat.welcome"), ts: nowTs() }]);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [doctorId]);

  useEffect(() => {
    if (!messages.length) return;
    localStorage.setItem(historyKey(doctorId), JSON.stringify(messages));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [messages, doctorId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const history = useMemo(
    () => messages.map((m) => ({ role: m.role, content: m.content })),
    [messages]
  );

  function onLogout() {
    setWebToken("");
    clearAuth();
    navigate("/login", { replace: true });
  }

  function onClear() {
    const fresh = [{ role: "assistant", content: t("chat.welcome"), ts: nowTs() }];
    setMessages(fresh);
    localStorage.setItem(historyKey(doctorId), JSON.stringify(fresh));
  }

  async function onSend() {
    const text = input.trim();
    if (!text || loading) return;
    setMessages((prev) => [...prev, { role: "user", content: text, ts: nowTs() }]);
    setInput("");
    setLoading(true);
    try {
      const data = await sendChat({ text, doctor_id: doctorId, history });
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: data.reply || t("chat.received"), record: data.record || null, ts: nowTs() },
      ]);
    } catch (error) {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: t("chat.requestFailed", { message: error.message }), ts: nowTs() },
      ]);
    } finally {
      setLoading(false);
    }
  }

  const assistantCount = useMemo(() => messages.filter((m) => m.role === "assistant").length, [messages]);

  return (
    <Box sx={{ display: "flex", height: "100vh", background: "#f8fafb" }}>
      {/* Sidebar */}
      <Box sx={{
        width: 220, flexShrink: 0, borderRight: "1px solid #e2e8f0",
        backgroundColor: "#fff", display: "flex", flexDirection: "column", py: 2, px: 1.5,
      }}>
        <Box sx={{ mb: 3, px: 0.5 }}>
          <Stack direction="row" spacing={0.8} alignItems="center">
            <SmartToyOutlinedIcon fontSize="small" color="primary" />
            <Typography variant="subtitle1" sx={{ fontWeight: 800, color: "primary.main" }}>AI 助手</Typography>
          </Stack>
          <Typography variant="caption" color="text.secondary">{doctorName || doctorId}</Typography>
        </Box>

        <Stack spacing={0.5} sx={{ flex: 1 }}>
          <Button
            startIcon={<PeopleOutlineIcon fontSize="small" />}
            onClick={() => navigate("/manage")}
            variant="text"
            sx={{ justifyContent: "flex-start", borderRadius: 1.5, color: "text.secondary", py: 1 }}
          >
            医生工作台
          </Button>
          <Divider sx={{ my: 1 }} />

          {/* Stats */}
          <Box sx={{ px: 0.5 }}>
            <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1 }}>会话信息</Typography>
            <Stack spacing={0.6}>
              {[
                { label: "消息数", value: messages.length },
                { label: "AI 回复", value: assistantCount },
              ].map((row) => (
                <Stack key={row.label} direction="row" justifyContent="space-between" alignItems="center">
                  <Typography variant="caption" color="text.secondary">{row.label}</Typography>
                  <Chip label={row.value} size="small" sx={{ height: 18, fontSize: 11 }} />
                </Stack>
              ))}
            </Stack>
          </Box>
        </Stack>

        <Button
          startIcon={<LogoutIcon fontSize="small" />}
          onClick={onLogout}
          size="small"
          sx={{ justifyContent: "flex-start", color: "text.secondary", mt: 1 }}
        >
          退出登录
        </Button>
      </Box>

      {/* Main chat area */}
      <Box sx={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
        {/* Topbar */}
        <Box sx={{ px: 3, py: 1.5, borderBottom: "1px solid #e2e8f0", backgroundColor: "#fff", display: "flex", alignItems: "center" }}>
          <Typography variant="subtitle2" sx={{ fontWeight: 700, color: "text.secondary", flex: 1 }}>
            {t("chat.workspaceTitle")}
          </Typography>
          <Tooltip title="清空对话">
            <IconButton size="small" onClick={onClear} sx={{ color: "text.secondary" }}>
              <DeleteOutlineIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        </Box>

        {/* Messages */}
        <Box sx={{ flex: 1, overflowY: "auto", py: 2, display: "flex", flexDirection: "column", gap: 1.4 }}>
          {messages.map((msg, idx) => (
            <MsgBubble key={`${msg.role}-${idx}`} msg={msg} />
          ))}
          {loading && (
            <Box sx={{ px: 2 }}>
              <Typography variant="caption" color="text.secondary">AI 正在回复…</Typography>
            </Box>
          )}
          <div ref={bottomRef} />
        </Box>

        {/* Input bar */}
        <Box sx={{ px: 2, py: 1.5, borderTop: "1px solid #e2e8f0", backgroundColor: "#fff" }}>
          <Stack direction="row" spacing={1} alignItems="flex-end">
            <TextField
              multiline
              minRows={2}
              maxRows={6}
              fullWidth
              placeholder={t("chat.placeholder")}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); onSend(); }
              }}
              size="small"
              sx={{ "& .MuiOutlinedInput-root": { borderRadius: 1.5 } }}
            />
            <Button
              variant="contained"
              onClick={onSend}
              disabled={loading || !input.trim()}
              sx={{ borderRadius: 1.5, minWidth: 48, height: 48, flexShrink: 0 }}
            >
              <SendOutlinedIcon fontSize="small" />
            </Button>
          </Stack>
        </Box>
      </Box>
    </Box>
  );
}
