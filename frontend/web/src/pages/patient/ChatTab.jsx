/**
 * ChatTab — AI health assistant general chat.
 *
 * Extracted from PatientPage.jsx. Includes:
 * - QuickActions row ("新问诊", "我的病历")
 * - Message polling with visibility-based intervals (10s visible, 60s hidden)
 * - localStorage persistence of chat messages
 * - Unread count tracking
 * - Triage category rendering (diagnosis_confirmation green bg, urgent red badge)
 * - DoctorBubble for doctor messages
 */

import { useEffect, useState, useRef } from "react";
import { useAppNavigate } from "../../hooks/useAppNavigate";
import {
  Box,
  CircularProgress,
  IconButton,
  TextField,
  Typography,
} from "@mui/material";
import SendIcon from "@mui/icons-material/Send";
import AddIcon from "@mui/icons-material/Add";
import SmartToyOutlinedIcon from "@mui/icons-material/SmartToyOutlined";
import PersonOutlineIcon from "@mui/icons-material/PersonOutline";
import DescriptionOutlinedIcon from "@mui/icons-material/DescriptionOutlined";
import AssignmentOutlinedIcon from "@mui/icons-material/AssignmentOutlined";
import NotificationsNoneOutlinedIcon from "@mui/icons-material/NotificationsNoneOutlined";
import { usePatientApi } from "../../api/PatientApiContext";
import DoctorBubble from "../../components/DoctorBubble";
import ListCard from "../../components/ListCard";
import RecordAvatar from "../../components/RecordAvatar";
import { TYPE, ICON, COLOR } from "../../theme";
import { LAST_SEEN_CHAT_KEY } from "./constants";

const PATIENT_CHAT_STORAGE_KEY = "patient_chat_messages";

// ---------------------------------------------------------------------------
// QuickActions — action row at top of chat
// ---------------------------------------------------------------------------

function QuickActions({ onNewInterview, onViewRecords }) {
  const actions = [
    { label: "新问诊", subtitle: "AI帮您整理病情", icon: <AddIcon sx={{ fontSize: ICON.xl, color: "#07C160" }} />, onClick: onNewInterview },
    { label: "我的病历", subtitle: "查看历史记录", icon: <DescriptionOutlinedIcon sx={{ fontSize: ICON.xl, color: "#1B6EF3" }} />, onClick: onViewRecords },
  ];
  return (
    <Box sx={{ display: "flex", gap: 1, px: 2, py: 1.5 }}>
      {actions.map(a => (
        <Box key={a.label} onClick={a.onClick}
          sx={{
            flex: 1, bgcolor: "#fff", borderRadius: "8px", p: 1.5,
            display: "flex", alignItems: "center", gap: 1.2,
            cursor: "pointer", userSelect: "none",
            boxShadow: "0 1px 3px rgba(0,0,0,0.06)",
            "&:active": { bgcolor: "#f9f9f9" },
          }}>
          <Box sx={{ width: 36, height: 36, borderRadius: "8px",
            bgcolor: a.label === "新问诊" ? "#e8f5e9" : "#E8F0FE",
            display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
            {a.icon}
          </Box>
          <Box>
            <Typography sx={{ fontSize: TYPE.heading.fontSize, fontWeight: 600, color: "#1A1A1A" }}>{a.label}</Typography>
            <Typography sx={{ fontSize: TYPE.micro.fontSize, color: "#999" }}>{a.subtitle}</Typography>
          </Box>
        </Box>
      ))}
    </Box>
  );
}

// ---------------------------------------------------------------------------
// ChatTab — main export
// ---------------------------------------------------------------------------

export default function ChatTab({ token, doctorName, onLogout, onNewInterview, onViewRecords, onUnreadCountChange }) {
  const navigate = useAppNavigate();
  const { getPatientChatMessages, sendPatientChat } = usePatientApi();
  const welcomeMsg = { source: "ai", content: `您好！我是${doctorName || "医生"}的AI助手。有什么健康问题可以问我。` };

  const [messages, setMessages] = useState([welcomeMsg]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [lastMsgId, setLastMsgId] = useState(null);
  const chatEndRef = useRef(null);
  const pollingRef = useRef(null);
  const visibleRef = useRef(true);

  // Initial load + polling for new messages
  useEffect(() => {
    let cancelled = false;

    async function poll() {
      try {
        const data = await getPatientChatMessages(token, lastMsgId);
        if (cancelled) return;
        if (Array.isArray(data) && data.length > 0) {
          setMessages(prev => {
            // Merge: append only new messages by id
            const existingIds = new Set(prev.filter(m => m.id).map(m => m.id));
            const newMsgs = data.filter(m => !existingIds.has(m.id));
            return newMsgs.length > 0 ? [...prev, ...newMsgs] : prev;
          });
          const maxId = Math.max(...data.map(m => m.id));
          setLastMsgId(maxId);
        }
      } catch (err) {
        if (err.status === 401) console.warn("auth expired");
      }
    }

    poll();

    function startPolling() {
      if (pollingRef.current) clearInterval(pollingRef.current);
      const interval = visibleRef.current ? 10000 : 60000;
      pollingRef.current = setInterval(poll, interval);
    }

    function handleVisibility() {
      visibleRef.current = !document.hidden;
      startPolling();
    }

    startPolling();
    document.addEventListener("visibilitychange", handleVisibility);

    return () => {
      cancelled = true;
      if (pollingRef.current) clearInterval(pollingRef.current);
      document.removeEventListener("visibilitychange", handleVisibility);
    };
  }, [token]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { chatEndRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  // Compute unread count for badge
  useEffect(() => {
    if (onUnreadCountChange && messages.length > 0) {
      const lastSeen = parseInt(localStorage.getItem(LAST_SEEN_CHAT_KEY) || "0", 10);
      const unread = messages.filter(m => {
        const msgTime = new Date(m.created_at).getTime();
        return msgTime > lastSeen;
      }).length;
      onUnreadCountChange(unread);
    }
  }, [messages, onUnreadCountChange]);

  async function handleSend(e) {
    e.preventDefault();
    const text = input.trim();
    if (!text || sending) return;
    setInput("");
    setMessages(prev => [...prev, { source: "patient", content: text, _local: true }]);
    setSending(true);
    try {
      const data = await sendPatientChat(token, text);
      setMessages(prev => [...prev, { source: "ai", content: data.reply || "收到您的消息。", triage_category: data.triage_category }]);
    } catch (err) {
      if (err.status === 401) { console.warn("auth expired"); return; }
      setMessages(prev => [...prev, { source: "ai", content: "系统繁忙，请稍后重试。" }]);
    } finally { setSending(false); }
  }

  function renderMessage(msg, i) {
    const src = msg.source || (msg.role === "user" ? "patient" : "ai");

    // Doctor reply bubble
    if (src === "doctor") {
      return (
        <Box key={msg.id || i} sx={{ mb: 1.5 }}>
          <DoctorBubble
            doctorName={doctorName || "医生"}
            content={msg.content}
            timestamp={msg.created_at ? new Date(msg.created_at).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" }) : null}
          />
        </Box>
      );
    }

    // Patient message (right aligned)
    if (src === "patient") {
      return (
        <Box key={msg.id || i} sx={{ display: "flex", flexDirection: "row-reverse", alignItems: "flex-end", gap: 1, mb: 1.5 }}>
          <Box sx={{ width: 32, height: 32, borderRadius: "4px", bgcolor: "#5b9bd5",
            display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
            <PersonOutlineIcon sx={{ color: "#fff", fontSize: ICON.md }} />
          </Box>
          <Box sx={{
            maxWidth: "75%", px: 1.5, py: 1, borderRadius: "4px 4px 0 4px",
            bgcolor: "#95ec69", color: "#333", fontSize: TYPE.body.fontSize, lineHeight: 1.7,
            whiteSpace: "pre-wrap", wordBreak: "break-word",
          }}>{msg.content}</Box>
        </Box>
      );
    }

    // System notification card
    if (src === "system") {
      const parts = (msg.triage_category || "").split(":");
      const linkType = parts[1] || null;
      const linkId = parts[2] || null;

      let avatar;
      let onTap;
      if (linkType === "record") {
        avatar = <RecordAvatar type="visit" size={32} />;
        onTap = () => navigate(`/patient/records/${linkId}`);
      } else if (linkType === "task") {
        avatar = (
          <Box sx={{ width: 32, height: 32, borderRadius: "4px", bgcolor: COLOR.primaryLight,
            display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
            <AssignmentOutlinedIcon sx={{ fontSize: 16, color: COLOR.primary }} />
          </Box>
        );
        onTap = () => navigate("/patient/tasks");
      } else {
        avatar = (
          <Box sx={{ width: 32, height: 32, borderRadius: "4px", bgcolor: COLOR.surface,
            display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
            <NotificationsNoneOutlinedIcon sx={{ fontSize: 16, color: COLOR.text4 }} />
          </Box>
        );
        onTap = null;
      }

      return (
        <Box key={msg.id || i} sx={{ px: 1.5, py: 0.5 }}>
          <ListCard
            avatar={avatar}
            title={msg.content}
            subtitle={onTap ? "点击查看" : undefined}
            chevron={!!onTap}
            onClick={onTap}
            sx={{ borderLeft: `3px solid ${COLOR.primary}`, borderRadius: "4px" }}
          />
        </Box>
      );
    }

    // AI message (left aligned) — with triage enrichment
    return (
      <Box key={msg.id || i} sx={{ display: "flex", alignItems: "flex-end", gap: 1, mb: 1.5 }}>
        <Box sx={{ width: 32, height: 32, borderRadius: "4px", bgcolor: "#07C160",
          display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
          <SmartToyOutlinedIcon sx={{ color: "#fff", fontSize: ICON.md }} />
        </Box>
        <Box sx={{ maxWidth: "75%" }}>
          {msg.triage_category === "diagnosis_confirmation" && (
            <Box sx={{ mb: 0.5, px: 1.5, py: 0.8, borderRadius: "4px 4px 4px 0", bgcolor: "#e8f5e9", border: "0.5px solid #c8e6c9" }}>
              <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.success, fontWeight: 500 }}>
                {msg.content}
              </Typography>
            </Box>
          )}
          {msg.triage_category !== "diagnosis_confirmation" && (
            <Box sx={{
              px: 1.5, py: 1, borderRadius: "4px 4px 4px 0", bgcolor: "#fff",
              color: "#333", fontSize: TYPE.body.fontSize, lineHeight: 1.7,
              whiteSpace: "pre-wrap", wordBreak: "break-word",
            }}>{msg.content}</Box>
          )}
          {msg.triage_category === "urgent" && (
            <Box sx={{ mt: 0.5, px: 1.5, py: 0.5, borderRadius: "6px", bgcolor: COLOR.dangerLight, border: `0.5px solid ${COLOR.danger}` }}>
              <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.danger, fontWeight: 500 }}>
                紧急情况，请立即就近就医
              </Typography>
            </Box>
          )}
        </Box>
      </Box>
    );
  }

  return (
    <Box sx={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0 }}>
      {/* Quick actions */}
      <QuickActions onNewInterview={onNewInterview} onViewRecords={onViewRecords} />

      {/* Chat area */}
      <Box sx={{ flex: 1, overflowY: "auto", px: 2, py: 1 }}>
        {messages.map(renderMessage)}
        {sending && (
          <Box sx={{ display: "flex", justifyContent: "flex-start", mb: 1.5 }}>
            <Box sx={{ px: 2, py: 1.5, borderRadius: 2, bgcolor: "#fff" }}><CircularProgress size={16} /></Box>
          </Box>
        )}
        <div ref={chatEndRef} />
      </Box>

      {/* Input */}
      <Box component="form" onSubmit={handleSend}
        sx={{ display: "flex", gap: 1, px: 2, py: 1.5, bgcolor: "#f5f5f5", borderTop: "1px solid #ddd", flexShrink: 0 }}>
        <TextField value={input} onChange={e => setInput(e.target.value)} placeholder="请输入…"
          fullWidth size="small" sx={{ bgcolor: "#fff", borderRadius: 1 }} autoFocus />
        <IconButton type="submit" disabled={!input.trim() || sending} sx={{ color: "#07C160" }} aria-label="发送"><SendIcon /></IconButton>
      </Box>
    </Box>
  );
}
