/**
 * 聊天面板：医生与 AI 助手对话，支持图片上传和快捷命令。
 */
import { useEffect, useMemo, useRef, useState } from "react";
import {
  Alert, Box, Button, CircularProgress, Dialog, DialogActions,
  DialogContent, DialogTitle, IconButton, Stack, TextField, Tooltip, Typography,
} from "@mui/material";
import useMediaQuery from "@mui/material/useMediaQuery";
import { useTheme } from "@mui/material/styles";
import SendOutlinedIcon from "@mui/icons-material/SendOutlined";
import AttachFileOutlinedIcon from "@mui/icons-material/AttachFileOutlined";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import SmartToyOutlinedIcon from "@mui/icons-material/SmartToyOutlined";
import LocalHospitalOutlinedIcon from "@mui/icons-material/LocalHospitalOutlined";
import { sendChat, confirmPendingRecordById, abandonPendingRecordById } from "../../api";
import RecordFields from "../../components/RecordFields";
import { t } from "../../i18n";
import { QUICK_COMMANDS } from "./constants";
import ViewPayloadCard from "./ViewPayloadCard";
import { processFile } from "./FileUploader";

function MsgAvatar({ isUser, size = 40 }) {
  return (
    <Box sx={{ width: size, height: size, borderRadius: "4px", flexShrink: 0, mb: 0.5,
      bgcolor: isUser ? "#5b9bd5" : "#07C160",
      display: "flex", alignItems: "center", justifyContent: "center" }}>
      {isUser
        ? <LocalHospitalOutlinedIcon sx={{ color: "#fff", fontSize: size * 0.56 }} />
        : <SmartToyOutlinedIcon sx={{ color: "#fff", fontSize: size * 0.56 }} />}
    </Box>
  );
}

function PendingConfirmCard({ patientName, expiresAt, onConfirm, onAbandon }) {
  const [busy, setBusy] = useState(false);
  const expiry = expiresAt ? new Date(expiresAt).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" }) : null;
  async function handleConfirm() {
    setBusy(true);
    try { await onConfirm(); } finally { setBusy(false); }
  }
  async function handleAbandon() {
    setBusy(true);
    try { await onAbandon(); } finally { setBusy(false); }
  }
  return (
    <Box sx={{ mt: 1, p: 1.5, borderRadius: "4px", border: "1px solid #e0e0e0", bgcolor: "#f9fff9" }}>
      <Typography variant="caption" sx={{ color: "#555", display: "block", mb: 1 }}>
        草稿已生成{patientName ? `（患者：${patientName}）` : ""}
        {expiry ? `，${expiry} 前有效` : ""}
      </Typography>
      <Stack direction="row" spacing={1}>
        <Button size="small" variant="contained" disabled={busy}
          sx={{ bgcolor: "#07C160", "&:hover": { bgcolor: "#06ad56" }, fontSize: 12 }}
          onClick={handleConfirm}>
          确认保存
        </Button>
        <Button size="small" variant="outlined" disabled={busy} color="inherit"
          sx={{ fontSize: 12, color: "#888", borderColor: "#ccc" }}
          onClick={handleAbandon}>
          取消
        </Button>
      </Stack>
    </Box>
  );
}

function MsgBubble({ msg, onConfirm, onAbandon }) {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down("sm"));
  const isUser = msg.role === "user";
  const bubbleRadius = isUser ? "4px 4px 0 4px" : "4px 4px 4px 0";
  const bgColor = isUser ? "#95EC69" : "#fff";
  const textColor = isUser ? "#111111" : (isMobile ? "#111" : "#191919");

  return (
    <Box sx={{ display: "flex", flexDirection: isUser ? "row-reverse" : "row", alignItems: "flex-end", gap: isMobile ? 1 : 1.2, px: isMobile ? 1.5 : 2 }}>
      <MsgAvatar isUser={isUser} size={40} />
      <Box sx={{ maxWidth: isMobile ? "72%" : "min(70%, 600px)", display: "flex", flexDirection: "column", alignItems: isUser ? "flex-end" : "flex-start" }}>
        <Box sx={{ position: "relative", px: isMobile ? "12px" : "14px", py: isMobile ? "9px" : "10px", borderRadius: bubbleRadius, bgcolor: bgColor, boxShadow: "none", ...(isUser ? { "&::after": { content: '""', position: "absolute", top: 10, right: -6, width: 0, height: 0, borderTop: "6px solid transparent", borderBottom: "6px solid transparent", borderLeft: "6px solid #95EC69" } } : { "&::after": { content: '""', position: "absolute", top: 10, left: -6, width: 0, height: 0, borderTop: "6px solid transparent", borderBottom: "6px solid transparent", borderRight: "6px solid #ffffff" } }) }}>
          <Typography variant="body2" sx={{ whiteSpace: "pre-wrap", lineHeight: isMobile ? 1.8 : 1.7, color: textColor }}>
            {msg.content}
          </Typography>
          {!isUser && msg.record ? <RecordFields record={msg.record} /> : null}
          {!isUser && msg.view_payload ? <ViewPayloadCard payload={msg.view_payload} /> : null}
          {!isUser && msg.pending_id && onConfirm && onAbandon ? (
            <PendingConfirmCard
              patientName={msg.pending_patient_name}
              expiresAt={msg.pending_expires_at}
              onConfirm={onConfirm}
              onAbandon={onAbandon}
            />
          ) : null}
        </Box>
        <Typography sx={{ mt: isMobile ? 0.3 : 0.4, px: 0.5, color: isMobile ? "#888" : "#aaa", fontSize: 11 }}>
          {msg.ts}
        </Typography>
      </Box>
    </Box>
  );
}

function SystemMessage({ msg }) {
  return (
    <Box sx={{ display: "flex", justifyContent: "center", px: 2, py: 0.5 }}>
      <Box sx={{ px: 2, py: 0.5, borderRadius: "4px", bgcolor: "#f0f0f0" }}>
        <Typography variant="caption" sx={{ color: "#999999", fontSize: 12, fontWeight: 500 }}>
          {msg.content}
        </Typography>
      </Box>
    </Box>
  );
}

function LoadingBubble({ isMobile }) {
  if (!isMobile) {
    return <Box sx={{ px: 2 }}><Typography variant="caption" color="text.secondary">AI 正在回复…</Typography></Box>;
  }
  return (
    <Box sx={{ display: "flex", alignItems: "flex-end", gap: 1, px: 1.5 }}>
      <Box sx={{ width: 40, height: 40, borderRadius: "4px", bgcolor: "#07C160", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
        <SmartToyOutlinedIcon sx={{ color: "#fff", fontSize: 20 }} />
      </Box>
      <Box sx={{ px: "12px", py: "10px", borderRadius: "4px 4px 4px 0", bgcolor: "#fff", boxShadow: "none", display: "flex", alignItems: "center", gap: 0.5 }}>
        {[0, 1, 2].map((i) => (
          <Box key={i} sx={{ width: 6, height: 6, borderRadius: "50%", bgcolor: "#aaa", animation: "dotPulse 1.4s ease-in-out infinite", animationDelay: `${i * 0.2}s`, "@keyframes dotPulse": { "0%, 80%, 100%": { opacity: 0.3, transform: "scale(0.8)" }, "40%": { opacity: 1, transform: "scale(1)" } } }} />
        ))}
      </Box>
    </Box>
  );
}

function QuickCommandChips({ onInsert, onAutoSend }) {
  return (
    <Box sx={{
      display: "flex", gap: 0.8, px: 1.5, py: 0.8,
      overflowX: "auto", whiteSpace: "nowrap",
      "&::-webkit-scrollbar": { display: "none" },
    }}>
      {QUICK_COMMANDS.map((cmd) => (
        <Box
          key={cmd.label}
          onClick={() => {
            if (cmd.insert.endsWith("：") || cmd.insert.endsWith("，")) {
              onInsert(cmd.insert);
            } else {
              onAutoSend(cmd.insert);
            }
          }}
          sx={{
            px: 1.5, py: 0.5, borderRadius: "4px", cursor: "pointer",
            fontSize: 13, flexShrink: 0, userSelect: "none",
            bgcolor: "#f0f0f0", color: "#333",
            "&:hover": { bgcolor: "#e0e0e0" },
            "&:active": { bgcolor: "#d5d5d5" },
          }}
        >
          {cmd.icon} {cmd.label}
        </Box>
      ))}
    </Box>
  );
}

function FailedMessageBanner({ onRetry, onDismiss }) {
  return (
    <Box sx={{ display: "flex", alignItems: "center", gap: 1, px: 2, py: 0.5, bgcolor: "#fff0f0", borderTop: "1px solid #fecaca" }}>
      <Typography variant="caption" color="error" sx={{ flex: 1 }}>上条消息发送失败</Typography>
      <Button size="small" variant="text" color="error" sx={{ fontSize: 12, py: 0, minWidth: "auto" }} onClick={onRetry}>重试</Button>
      <Button size="small" variant="text" sx={{ fontSize: 12, py: 0, minWidth: "auto", color: "text.secondary" }} onClick={onDismiss}>忽略</Button>
    </Box>
  );
}

function nowTs() {
  const d = new Date();
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

function MobileInputBar({ input, loading, isProcessing, failedText, mediaError, fileInputRef, onInput, onSend, onFileClick, onRetry, onDismissError, onDismissFailed }) {
  return (
    <Box sx={{ borderTop: "1px solid #d9d9d9", backgroundColor: "#f5f5f5" }}>
      {failedText && <FailedMessageBanner onRetry={onRetry} onDismiss={onDismissFailed} />}
      {mediaError && <Alert severity="error" onClose={onDismissError} sx={{ mx: 1, mt: 0.5, py: 0 }}>{mediaError}</Alert>}
      {isProcessing && (
        <Typography variant="caption" color="text.secondary" sx={{ display: "flex", alignItems: "center", gap: 0.5, px: 2, pt: 0.5 }}>
          <CircularProgress size={10} /> 处理中…
        </Typography>
      )}
      <Stack direction="row" alignItems="center" sx={{ px: 1, py: 0.8, gap: 0.5 }}>
        <IconButton size="small" onClick={onFileClick} disabled={isProcessing} sx={{ color: "#666", p: 1.1 }}>
          <AttachFileOutlinedIcon />
        </IconButton>
        <TextField multiline minRows={1} maxRows={4} fullWidth size="small"
          placeholder={t("chat.placeholder")} value={input}
          onChange={(e) => onInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); onSend(); } }}
          disabled={isProcessing}
          sx={{ "& .MuiOutlinedInput-root": { borderRadius: "4px", backgroundColor: "#fff", fontSize: "0.9rem", "& fieldset": { borderColor: "#e0e0e0" } } }} />
        <IconButton onClick={onSend} disabled={loading || !input.trim()}
          sx={{ bgcolor: "#07C160", color: "#fff", p: 1.2, borderRadius: "50%", "&:hover": { bgcolor: "#06ad56" }, flexShrink: 0, minWidth: 44, minHeight: 44 }}>
          <SendOutlinedIcon fontSize="small" />
        </IconButton>
      </Stack>
    </Box>
  );
}

function DesktopInputBar({ input, loading, isProcessing, failedText, mediaError, fileInputRef, onInput, onSend, onFileClick, onRetry, onDismissError, onDismissFailed }) {
  return (
    <Box sx={{ px: 2, py: 1.2, borderTop: "0.5px solid #d9d9d9", backgroundColor: "#f5f5f5" }}>
      {failedText && <FailedMessageBanner onRetry={onRetry} onDismiss={onDismissFailed} />}
      {mediaError && <Alert severity="error" onClose={onDismissError} sx={{ mb: 1, py: 0 }}>{mediaError}</Alert>}
      <Stack direction="row" spacing={1} alignItems="flex-end">
        <Box sx={{ flex: 1 }}>
          <TextField multiline minRows={2} maxRows={6} fullWidth size="small"
            placeholder={t("chat.placeholder")} value={input}
            onChange={(e) => onInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); onSend(); } }}
            disabled={isProcessing}
            sx={{ "& .MuiOutlinedInput-root": { borderRadius: 1.5 } }} />
          {input.length > 0 && (
            <Typography variant="caption" color="text.secondary" sx={{ display: "block", textAlign: "right", mt: 0.3 }}>
              {input.length} 字
            </Typography>
          )}
          {isProcessing && (
            <Typography variant="caption" color="text.secondary" sx={{ display: "flex", alignItems: "center", gap: 0.5, mt: 0.3 }}>
              <CircularProgress size={10} /> 处理中…
            </Typography>
          )}
        </Box>
        <Stack direction="row" spacing={0.5} alignItems="center" sx={{ flexShrink: 0 }}>
          <Tooltip title="上传图片">
            <span>
              <IconButton size="small" onClick={onFileClick} disabled={isProcessing} sx={{ color: "text.secondary" }}>
                <AttachFileOutlinedIcon fontSize="small" />
              </IconButton>
            </span>
          </Tooltip>
          <Button variant="contained" onClick={onSend} disabled={loading || !input.trim()}
            sx={{ borderRadius: 1.5, minWidth: 48, height: 48 }}>
            <SendOutlinedIcon fontSize="small" />
          </Button>
        </Stack>
      </Stack>
    </Box>
  );
}

async function performSend({ text, loading, doctorId, history, setMessages, setInput, setLoading, setFailedText, onPatientCreated }) {
  if (!text || loading) return;
  setFailedText(null);
  setMessages((prev) => [...prev, { role: "user", content: text, ts: nowTs() }]);
  setInput("");
  setLoading(true);
  try {
    const data = await sendChat({ text, doctor_id: doctorId, history });
    const reply = data.reply || t("chat.received");
    setMessages((prev) => {
      const next = [...prev];
      // Show patient-switch notification as a distinct system message before the reply
      if (data.switch_notification) {
        next.push({ role: "system", content: data.switch_notification, ts: nowTs() });
      }
      next.push({
        role: "assistant", content: reply, record: data.record || null, ts: nowTs(),
        pending_id: data.pending_id || null,
        pending_patient_name: data.pending_patient_name || null,
        pending_expires_at: data.pending_expires_at || null,
        view_payload: data.view_payload || null,
      });
      return next;
    });
    if (onPatientCreated && (reply.includes("已创建") || (reply.includes("已为") && reply.includes("创建")))) {
      onPatientCreated();
    }
  } catch (error) {
    const isNet = error.message === "Failed to fetch" || error.message === "NetworkError" || error.name === "TypeError";
    const msg = isNet ? "网络连接失败，请检查网络后重试。" : t("chat.requestFailed", { message: error.message });
    setMessages((prev) => [...prev, { role: "assistant", content: msg, ts: nowTs() }]);
    setFailedText(text);
  } finally {
    setLoading(false);
  }
}

function useChatState({ doctorId, onMessageCountChange, onPatientCreated }) {
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [failedText, setFailedText] = useState(null);
  const [messages, setMessages] = useState([]);
  const bottomRef = useRef(null);
  const storageKey = `doctor_ai_chat_history:${(doctorId || "anon")}`;
  const history = useMemo(() => messages.slice(-20).map((m) => ({ role: m.role, content: m.content })), [messages]);

  useEffect(() => {
    const raw = localStorage.getItem(storageKey);
    try {
      const parsed = raw ? JSON.parse(raw) : null;
      setMessages(Array.isArray(parsed) && parsed.length ? parsed : [{ role: "assistant", content: t("chat.welcome"), ts: nowTs() }]);
    } catch { setMessages([{ role: "assistant", content: t("chat.welcome"), ts: nowTs() }]); }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [doctorId]);

  useEffect(() => {
    if (messages.length) localStorage.setItem(storageKey, JSON.stringify(messages));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [messages]);

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);
  useEffect(() => { onMessageCountChange?.(messages.length); }, [messages.length, onMessageCountChange]);

  function onClear() {
    const fresh = [{ role: "assistant", content: t("chat.welcome"), ts: nowTs() }];
    setMessages(fresh);
    localStorage.setItem(storageKey, JSON.stringify(fresh));
  }

  function sendText(text) {
    return performSend({ text, loading, doctorId, history, setMessages, setInput, setLoading, setFailedText, onPatientCreated });
  }

  return { input, setInput, loading, failedText, setFailedText, messages, setMessages, bottomRef, onClear, sendText };
}

function ChatTopbar({ isMobile, doctorId, onClearClick }) {
  return (
    <Box sx={{ px: isMobile ? 2 : 3, height: 48, borderBottom: "1px solid #e5e5e5", backgroundColor: isMobile ? "#f7f7f7" : "#fff", display: "flex", alignItems: "center" }}>
      <Box sx={{ flex: 1, textAlign: isMobile ? "center" : "left" }}>
        <Typography variant="subtitle2" sx={{ fontWeight: 500, color: "#191919", fontSize: 17 }}>{t("chat.workspaceTitle")}</Typography>
        {isMobile && doctorId && (
          <Typography variant="caption" sx={{ color: "#999", fontSize: 10, display: "block", lineHeight: 1 }}>ID: {doctorId}</Typography>
        )}
      </Box>
      <Tooltip title="清空对话">
        <IconButton size="small" onClick={onClearClick} sx={{ color: "text.secondary" }}>
          <DeleteOutlineIcon fontSize="small" />
        </IconButton>
      </Tooltip>
    </Box>
  );
}

function ClearDialog({ open, onClear, onClose }) {
  return (
    <Dialog open={open} onClose={onClose}>
      <DialogTitle>清空对话记录</DialogTitle>
      <DialogContent>
        <Typography>确定清空所有对话记录？此操作无法撤销。</Typography>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>取消</Button>
        <Button color="error" onClick={() => { onClear(); onClose(); }}>清空</Button>
      </DialogActions>
    </Dialog>
  );
}

function useChatEffects({ externalInput, onExternalInputConsumed, autoSendText, onAutoSendConsumed, setInput, sendText }) {
  const autoSentRef = useRef("");
  useEffect(() => {
    if (externalInput) { setInput(externalInput); onExternalInputConsumed?.(); }
  }, [externalInput]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (autoSendText && autoSendText !== autoSentRef.current) {
      autoSentRef.current = autoSendText;
      onAutoSendConsumed?.();
      sendText(autoSendText);
    }
  }, [autoSendText]); // eslint-disable-line react-hooks/exhaustive-deps
}

function usePendingHandlers({ setMessages, onPatientCreated }) {
  function clearMsg(pendingId) {
    setMessages((prev) => prev.map((m) => m.pending_id === pendingId ? { ...m, pending_id: null } : m));
  }
  async function handleConfirm(pendingId) {
    try {
      const result = await confirmPendingRecordById(pendingId);
      clearMsg(pendingId);
      setMessages((prev) => [...prev, { role: "assistant", content: `✅ 病历已保存（${result.patient_name || ""}）`, ts: nowTs() }]);
      onPatientCreated?.();
    } catch (err) {
      setMessages((prev) => [...prev, { role: "assistant", content: `保存失败：${err.message}`, ts: nowTs() }]);
    }
  }
  async function handleAbandon(pendingId) {
    try { await abandonPendingRecordById(pendingId); } catch {}
    clearMsg(pendingId);
    setMessages((prev) => [...prev, { role: "assistant", content: "草稿已取消。", ts: nowTs() }]);
  }
  return { handleConfirm, handleAbandon };
}

export default function ChatSection({ doctorId, onMessageCountChange, externalInput, onExternalInputConsumed, onPatientCreated, autoSendText, onAutoSendConsumed }) {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down("sm"));
  const [clearConfirmOpen, setClearConfirmOpen] = useState(false);
  const [mediaError, setMediaError] = useState(null);
  const fileInputRef = useRef(null);
  const [mediaProcessing, setMediaProcessing] = useState(false);

  const { input, setInput, loading, failedText, setFailedText, messages, setMessages, bottomRef, onClear, sendText } =
    useChatState({ doctorId, onMessageCountChange, onPatientCreated });
  useChatEffects({ externalInput, onExternalInputConsumed, autoSendText, onAutoSendConsumed, setInput, sendText });
  const { handleConfirm: handlePendingConfirm, handleAbandon: handlePendingAbandon } = usePendingHandlers({ setMessages, onPatientCreated });

  const isProcessing = mediaProcessing;
  const sharedBarProps = {
    input, loading, isProcessing, failedText, mediaError, fileInputRef,
    onInput: setInput, onSend: () => sendText(input.trim()), onFileClick: () => fileInputRef.current?.click(),
    onRetry: () => { setInput(failedText); setFailedText(null); },
    onDismissError: () => setMediaError(null), onDismissFailed: () => setFailedText(null),
  };

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <ChatTopbar isMobile={isMobile} doctorId={doctorId} onClearClick={() => setClearConfirmOpen(true)} />
      <Box sx={{ flex: 1, overflowY: "auto", py: 2, display: "flex", flexDirection: "column", gap: isMobile ? 1.8 : 1.4, bgcolor: "#ededed" }}>
        {messages.map((msg, idx) => (
          msg.role === "system"
            ? <SystemMessage key={`system-${idx}`} msg={msg} />
            : <MsgBubble key={`${msg.role}-${idx}`} msg={msg}
                onConfirm={msg.pending_id ? () => handlePendingConfirm(msg.pending_id) : undefined}
                onAbandon={msg.pending_id ? () => handlePendingAbandon(msg.pending_id) : undefined} />
        ))}
        {loading && <LoadingBubble isMobile={isMobile} />}
        <div ref={bottomRef} />
      </Box>
      <QuickCommandChips onInsert={(text) => setInput(text)} onAutoSend={(text) => sendText(text)} />
      <input ref={fileInputRef} type="file" accept="image/*" style={{ display: "none" }}
        onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; processFile({ file: f, setMediaError, setMediaProcessing, setInput }); }} />
      {isMobile ? <MobileInputBar {...sharedBarProps} /> : <DesktopInputBar {...sharedBarProps} />}
      <ClearDialog open={clearConfirmOpen} onClear={onClear} onClose={() => setClearConfirmOpen(false)} />
    </Box>
  );
}
