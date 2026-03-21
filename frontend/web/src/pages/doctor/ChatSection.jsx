/**
 * 聊天面板：医生与 AI 助手对话，支持图片上传和快捷命令。
 */
import { useEffect, useMemo, useRef, useState } from "react";
import {
  Alert, Box, Button, CircularProgress, Dialog, DialogActions,
  DialogContent, DialogTitle, IconButton, Stack, Tooltip, Typography,
} from "@mui/material";
import useMediaQuery from "@mui/material/useMediaQuery";
import { useTheme } from "@mui/material/styles";
import SendOutlinedIcon from "@mui/icons-material/SendOutlined";
import AttachFileOutlinedIcon from "@mui/icons-material/AttachFileOutlined";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import SmartToyOutlinedIcon from "@mui/icons-material/SmartToyOutlined";
import LocalHospitalOutlinedIcon from "@mui/icons-material/LocalHospitalOutlined";
import Markdown from "react-markdown";
import { sendChat, ocrImage, extractFileForChat, clearContext, doctorInterviewTurn, doctorInterviewConfirm, doctorInterviewCancel } from "../../api";
import RecordFields from "../../components/RecordFields";
import { t } from "../../i18n";
import { QUICK_COMMANDS, Action } from "./constants";
import ActionPanel from "./ActionPanel";
import PatientPickerDialog from "./PatientPickerDialog";
import ImportChoiceDialog from "./ImportChoiceDialog";
import VoiceInput, { isVoiceSupported } from "./VoiceInput";
import AddCircleOutlineIcon from "@mui/icons-material/AddCircleOutline";
import MicNoneOutlinedIcon from "@mui/icons-material/MicNoneOutlined";

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


function TasksCard({ tasks }) {
  if (!tasks || !tasks.length) return null;
  const typeLabels = { appointment: "复诊", follow_up: "随访", general: "任务" };
  return (
    <Box sx={{ mt: 1, borderTop: "1px solid #e5e5e5", pt: 1 }}>
      {tasks.map((t) => (
        <Box key={t.id} sx={{ py: 0.5, borderBottom: "1px solid #f0f0f0", "&:last-child": { borderBottom: "none" } }}>
          <Typography variant="body2" sx={{ fontWeight: 600, fontSize: 13 }}>
            {typeLabels[t.task_type] || "任务"} · {t.title || "未命名"}
          </Typography>
          {t.due_at && <Typography variant="caption" color="text.secondary">{t.due_at.replace("T", " ").slice(0, 16)}</Typography>}
        </Box>
      ))}
    </Box>
  );
}

/* Minimal markdown styles scoped to AI message bubbles */
const mdStyles = {
  "& p": { m: 0, lineHeight: 1.7 },
  "& p + p": { mt: 0.8 },
  "& strong": { fontWeight: 600 },
  "& hr": { border: "none", borderTop: "1px solid #e5e5e5", my: 1 },
  "& ul, & ol": { m: 0, pl: 2.5 },
  "& li": { lineHeight: 1.7 },
  "& h1,& h2,& h3,& h4": { fontSize: 14, fontWeight: 600, mt: 1, mb: 0.5 },
  "& code": { fontSize: 12, bgcolor: "#f5f5f5", px: 0.5, borderRadius: 0.5 },
};

function MsgBubble({ msg, onQuickSend }) {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down("sm"));
  const isUser = msg.role === "user";
  const bubbleRadius = isUser ? "4px 4px 0 4px" : "4px 4px 4px 0";
  const bgColor = isUser ? "#95EC69" : "#fff";
  const textColor = "#111111";
  const hasPending = !isUser && /确认保存/.test(msg.content);

  return (
    <Box sx={{ display: "flex", flexDirection: isUser ? "row-reverse" : "row", alignItems: "flex-end", gap: isMobile ? 1 : 1.2, px: isMobile ? 1.5 : 2 }}>
      <MsgAvatar isUser={isUser} size={40} />
      <Box sx={{ maxWidth: isMobile ? "72%" : "min(70%, 600px)", display: "flex", flexDirection: "column", alignItems: isUser ? "flex-end" : "flex-start" }}>
        <Box sx={{ position: "relative", px: isMobile ? "12px" : "14px", py: isMobile ? "9px" : "10px", borderRadius: bubbleRadius, bgcolor: bgColor, boxShadow: "none",
          "&::after": {
            content: '""', position: "absolute", bottom: 0, width: 0, height: 0, border: "6px solid transparent",
            ...(isUser
              ? { right: "-10px", borderLeftColor: bgColor, borderBottomColor: bgColor }
              : { left: "-10px", borderRightColor: bgColor, borderBottomColor: bgColor }),
          } }}>
          {isUser ? (
            <Typography variant="body2" sx={{ whiteSpace: "pre-wrap", lineHeight: isMobile ? 1.8 : 1.7, color: textColor }}>
              {msg.actionLabel && (
                <Box component="span" sx={{ display: "inline-flex", alignItems: "center", backgroundColor: "rgba(0,0,0,0.06)",
                  px: 0.8, py: 0.1, borderRadius: "2px", fontSize: 12, color: "#555", mr: 0.8, verticalAlign: "middle" }}>
                  {msg.actionLabel}
                </Box>
              )}
              {msg.actionLabel && msg.content === msg.actionLabel ? null : msg.content}
            </Typography>
          ) : (
            <Box sx={{ fontSize: 14, color: textColor, ...mdStyles }}>
              <Markdown>{msg.content}</Markdown>
            </Box>
          )}
          {!isUser && msg.record ? <RecordFields record={msg.record} /> : null}
          {!isUser && msg.view_payload?.type === "tasks_list" ? <TasksCard tasks={msg.view_payload.data} /> : null}
          {hasPending && onQuickSend && (
            <Stack direction="row" spacing={1} sx={{ mt: 1.5, pt: 1, borderTop: "1px solid #e5e5e5" }}>
              <Button size="small" variant="contained" disableElevation
                sx={{ bgcolor: "#07C160", "&:hover": { bgcolor: "#06a050" }, textTransform: "none", fontSize: 13, borderRadius: 1 }}
                onClick={() => onQuickSend("确认")}>
                确认保存
              </Button>
              <Button size="small" variant="outlined" disableElevation
                sx={{ color: "#999", borderColor: "#d9d9d9", textTransform: "none", fontSize: 13, borderRadius: 1 }}
                onClick={() => onQuickSend("取消")}>
                取消
              </Button>
            </Stack>
          )}
        </Box>
        <Typography sx={{ mt: isMobile ? 0.3 : 0.4, px: 0.5, color: isMobile ? "#888" : "#aaa", fontSize: 11 }}>
          {msg.ts}
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

function QuickCommandBar({ activeChip, onSelect }) {
  return (
    <Box sx={{ px: 1.5, pt: 1, pb: 0.8, borderTop: "0.5px solid #e0e0e0", backgroundColor: "#f7f7f7", display: "flex", gap: 1, flexWrap: "wrap" }}>
      {QUICK_COMMANDS.map((cmd) => {
        const isActive = activeChip?.key === cmd.key;
        const isDisabled = cmd.disabled;
        return (
          <Box key={cmd.key} component="button"
            onClick={() => !isDisabled && onSelect(cmd)}
            disabled={isDisabled}
            title={isDisabled ? "即将上线" : undefined}
            sx={{
              display: "inline-flex", alignItems: "center", px: 1.5, py: 0.6,
              border: "none", borderRadius: "4px", cursor: isDisabled ? "default" : "pointer",
              fontSize: 13, fontFamily: "inherit", whiteSpace: "nowrap",
              backgroundColor: isActive ? "#07C160" : "#fff",
              color: isActive ? "#fff" : "#333",
              opacity: isDisabled ? 0.4 : 1,
              boxShadow: isActive ? "none" : "0 1px 2px rgba(0,0,0,0.08)",
              transition: "background-color 0.15s, color 0.15s",
              "&:active": isDisabled ? {} : { opacity: 0.7 },
            }}>
            {cmd.label}
          </Box>
        );
      })}
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

function ChipInput({ activeChip, onRemoveChip, input, onInput, onSend, loading, isProcessing,
  failedText, onRetry, onDismissFailed, mediaError, onDismissError, fileInputRef,
  isMobile, voiceMode, voiceSupported, onVoiceToggle, onVoiceResult, onVoiceCancel, onActionPanelOpen }) {
  const inputRef = useRef(null);

  function handleKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      onSend();
    }
    if (e.key === "Backspace" && activeChip && !input) {
      e.preventDefault();
      onRemoveChip();
    }
  }

  useEffect(() => {
    if (activeChip) inputRef.current?.focus();
  }, [activeChip]);

  return (
    <Box sx={{ borderTop: "1px solid #d9d9d9", backgroundColor: "#f5f5f5" }}>
      {failedText && <FailedMessageBanner onRetry={onRetry} onDismiss={onDismissFailed} />}
      {mediaError && <Alert severity="error" onClose={onDismissError} sx={{ mx: 1, mt: 0.5, py: 0 }}>{mediaError}</Alert>}
      {isProcessing && (
        <Typography variant="caption" color="text.secondary" sx={{ display: "flex", alignItems: "center", gap: 0.5, px: 2, pt: 0.5 }}>
          <CircularProgress size={10} /> 处理中…
        </Typography>
      )}
      {voiceMode ? (
        <Box sx={{ px: 1, py: 0.8 }}>
          <VoiceInput onResult={onVoiceResult} onCancel={onVoiceCancel} />
        </Box>
      ) : (
        <Stack direction="row" alignItems="center" sx={{ px: 1, py: 0.8, gap: 0.5 }}>
          {isMobile && (
            <IconButton size="small" onClick={onActionPanelOpen} disabled={isProcessing} sx={{ color: "#07C160", p: 1.1 }}>
              <AddCircleOutlineIcon />
            </IconButton>
          )}
          <Box sx={{ flex: 1, display: "flex", alignItems: "center", gap: 0.8, flexWrap: "nowrap",
            backgroundColor: "#fff", borderRadius: "4px", px: 1.2, py: 0.8, minHeight: 36 }}>
            {activeChip && (
              <Box sx={{ display: "inline-flex", alignItems: "center", gap: 0.3, backgroundColor: "#f0f0f0",
                color: "#333", px: 1, py: 0.25, borderRadius: "3px", fontSize: 12, whiteSpace: "nowrap",
                border: "1px solid #ddd", flexShrink: 0 }}>
                {activeChip.label}
                <Box component="span" onClick={onRemoveChip}
                  sx={{ color: "#999", ml: 0.3, cursor: "pointer", fontSize: 10, lineHeight: 1, "&:hover": { color: "#666" } }}>
                  ✕
                </Box>
              </Box>
            )}
            <Box component="input" ref={inputRef} value={input}
              onChange={(e) => onInput(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={isProcessing}
              placeholder={activeChip ? "输入内容..." : "输入消息..."}
              sx={{ flex: 1, border: "none", outline: "none", fontSize: 14, fontFamily: "inherit",
                backgroundColor: "transparent", minWidth: 0, p: 0 }}
            />
          </Box>
          {!isMobile && (
            <Tooltip title="上传图片">
              <span>
                <IconButton size="small" onClick={() => fileInputRef.current?.click()} disabled={isProcessing} sx={{ color: "text.secondary" }}>
                  <AttachFileOutlinedIcon fontSize="small" />
                </IconButton>
              </span>
            </Tooltip>
          )}
          {isMobile && voiceSupported && !input.trim() && !activeChip ? (
            <IconButton onClick={onVoiceToggle}
              sx={{ color: "#666", p: 1.2, flexShrink: 0, minWidth: 44, minHeight: 44 }}>
              <MicNoneOutlinedIcon fontSize="small" />
            </IconButton>
          ) : (
            <IconButton onClick={onSend} disabled={loading || (!input.trim() && !activeChip)}
              sx={{ bgcolor: "#07C160", color: "#fff", p: 1.2, borderRadius: "50%", "&:hover": { bgcolor: "#06ad56" }, flexShrink: 0, minWidth: 44, minHeight: 44, "&.Mui-disabled": { bgcolor: "#ccc", color: "#fff" } }}>
              <SendOutlinedIcon fontSize="small" />
            </IconButton>
          )}
        </Stack>
      )}
    </Box>
  );
}

async function performSend({ text, loading, doctorId, history, setMessages, setInput, setLoading, setFailedText, onPatientCreated, actionHint, actionLabel }) {
  if (!text || loading) return;
  setFailedText(null);
  setMessages((prev) => [...prev, { role: "user", content: text, ts: nowTs(), actionLabel: actionLabel || null }]);
  setInput("");
  setLoading(true);
  try {
    const payload = { text, doctor_id: doctorId, history };
    if (actionHint) payload.action_hint = actionHint;
    const data = await sendChat(payload);
    const reply = data.reply || t("chat.received");
    setMessages((prev) => [...prev, {
      role: "assistant", content: reply, record: data.record || null, ts: nowTs(),
      view_payload: data.view_payload || null,
    }]);
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

function useChatState({ doctorId, onMessageCountChange, onPatientCreated, onContextCleared }) {
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

  async function onClear() {
    const fresh = [{ role: "assistant", content: t("chat.welcome"), ts: nowTs() }];
    setMessages(fresh);
    localStorage.setItem(storageKey, JSON.stringify(fresh));
    // Clear server-side context: pending draft, current patient, conversation history, etc.
    if (doctorId) {
      try { await clearContext(doctorId); } catch {}
      onContextCleared?.();
    }
  }

  function sendText(text, actionHint = null, actionLabel = null) {
    return performSend({ text, loading, doctorId, history, setMessages, setInput, setLoading, setFailedText, onPatientCreated, actionHint, actionLabel });
  }

  return { input, setInput, loading, setLoading, failedText, setFailedText, messages, setMessages, bottomRef, onClear, sendText };
}

function ChatTopbar({ isMobile, doctorId, onClearClick }) {
  return (
    <Box sx={{ px: isMobile ? 2 : 3, height: 48, borderBottom: "0.5px solid #d9d9d9", backgroundColor: isMobile ? "#f7f7f7" : "#fff", display: "flex", alignItems: "center" }}>
      <Box sx={{ flex: 1, textAlign: isMobile ? "center" : "left" }}>
        <Typography variant="subtitle2" sx={{ fontWeight: 500, color: "#111111", fontSize: 17 }}>{t("chat.workspaceTitle")}</Typography>
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
        <Typography>确定清空所有对话记录、草稿和当前工作上下文？此操作无法撤销。</Typography>
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

async function processFile({ file, setMediaError, setMediaProcessing, setInput }) {
  if (!file) return;
  setMediaError(null);
  setMediaProcessing(true);
  try {
    if (file.type.startsWith("image/")) {
      const { text } = await ocrImage(file);
      if (text) setInput((prev) => (prev ? prev + "\n" + text : text));
    } else {
      setMediaError("不支持的文件类型，请上传图片");
    }
  } catch {
    setMediaError("文件处理失败，请重试");
  } finally {
    setMediaProcessing(false);
  }
}


function useDailySummary({ doctorId, sendText, ready }) {
  const done = useRef(false);
  const sendRef = useRef(sendText);
  sendRef.current = sendText;
  useEffect(() => {
    if (!doctorId || !ready || done.current) return;
    const today = new Date().toISOString().slice(0, 10);
    const key = `daily_summary_sent:${doctorId}`;
    if (localStorage.getItem(key) === today) return;
    done.current = true;
    localStorage.setItem(key, today);
    const t = setTimeout(() => sendRef.current("今日摘要", "daily_summary", "今日摘要"), 1200);
    return () => clearTimeout(t);
  }, [doctorId, ready]); // eslint-disable-line react-hooks/exhaustive-deps
}

export default function ChatSection({ doctorId, onMessageCountChange, externalInput, onExternalInputConsumed, onPatientCreated, autoSendText, onAutoSendConsumed, onContextCleared }) {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down("sm"));
  const [clearConfirmOpen, setClearConfirmOpen] = useState(false);
  const [mediaError, setMediaError] = useState(null);
  const [activeChip, setActiveChip] = useState(null);
  const [activeInterview, setActiveInterview] = useState(() => {
    const saved = localStorage.getItem(`active_interview:${doctorId}`);
    try { return saved ? JSON.parse(saved) : null; } catch { return null; }
  });

  useEffect(() => {
    if (activeInterview) {
      localStorage.setItem(`active_interview:${doctorId}`, JSON.stringify(activeInterview));
    } else {
      localStorage.removeItem(`active_interview:${doctorId}`);
    }
  }, [activeInterview, doctorId]);

  const fileInputRef = useRef(null);
  const [mediaProcessing, setMediaProcessing] = useState(false);
  const [actionPanelOpen, setActionPanelOpen] = useState(false);
  const [patientPickerOpen, setPatientPickerOpen] = useState(false);
  const [importChoice, setImportChoice] = useState(null);
  const [voiceMode, setVoiceMode] = useState(false);
  const voiceSupported = isVoiceSupported();
  const cameraInputRef = useRef(null);
  const galleryInputRef = useRef(null);
  const fileDocInputRef = useRef(null);

  const { input, setInput, loading, setLoading, failedText, setFailedText, messages, setMessages, bottomRef, onClear, sendText } =
    useChatState({ doctorId, onMessageCountChange, onPatientCreated, onContextCleared });
  useChatEffects({ externalInput, onExternalInputConsumed, autoSendText, onAutoSendConsumed, setInput, sendText });
  useDailySummary({ doctorId, sendText, ready: messages.length > 0 });


  function handlePanelAction(action) {
    setActionPanelOpen(false);
    switch (action) {
      case "camera": cameraInputRef.current?.click(); break;
      case "gallery": galleryInputRef.current?.click(); break;
      case "file": fileDocInputRef.current?.click(); break;
      case "patient": setPatientPickerOpen(true); break;
    }
  }
  async function handleDocFile(file) {
    if (!file) return;
    try {
      const { text } = await extractFileForChat(file);
      if (text) setImportChoice({ text });
    } catch { /* ignore */ }
  }

  function handleCommandSelect(cmd) {
    if (cmd.key === Action.CREATE_RECORD) {
      // Enter interview mode
      if (activeInterview) {
        // Abandon current interview silently
        if (activeInterview.sessionId) {
          doctorInterviewCancel(activeInterview.sessionId, doctorId).catch(() => {});
        }
      }
      setActiveInterview({ sessionId: null, progress: { filled: 0, total: 7 }, status: "interviewing" });
      setActiveChip(null);
      setMessages(prev => [...prev, {
        role: "assistant",
        content: "病历采集模式已开启。请输入患者信息（姓名、性别、年龄、症状等），我会帮您结构化记录。",
        ts: nowTs(),
      }]);
      return;
    }
    if (cmd.autoSend) {
      setInput("");
      setActiveChip(null);
      sendText(cmd.label, cmd.key, cmd.label);
      return;
    }
    if (activeChip?.key === cmd.key) {
      setActiveChip(null);
      return;
    }
    setActiveChip({ key: cmd.key, label: cmd.label });
  }

  function handleChipSend() {
    const text = input.trim();
    const cmd = QUICK_COMMANDS.find(c => c.key === activeChip?.key);
    if (activeChip && !cmd?.autoSend && !text && !cmd?.allowEmpty) return;
    sendText(text || activeChip?.label || "", activeChip?.key || null, activeChip?.label || null);
    setInput("");
    setActiveChip(null);
  }

  async function handleInterviewSend() {
    const text = input.trim();
    if (!text || loading) return;

    setMessages(prev => [...prev, { role: "user", content: text, ts: nowTs() }]);
    setInput("");
    setLoading(true);

    try {
      const formData = new FormData();
      formData.append("text", text);
      formData.append("doctor_id", doctorId);

      if (!activeInterview.sessionId) {
        // First turn — extract patient name from text
        const name = text.split(/[，,\s]/)[0].replace(/[新患者创建]/g, "").trim();
        formData.append("patient_name", name || text.substring(0, 10));
      } else {
        formData.append("session_id", activeInterview.sessionId);
      }

      const data = await doctorInterviewTurn(formData);

      setActiveInterview({
        sessionId: data.session_id,
        progress: data.progress,
        status: data.status,
        patientId: data.patient_id,
      });

      setMessages(prev => [...prev, {
        role: "assistant",
        content: data.reply,
        ts: nowTs(),
        interviewProgress: data.progress,
      }]);
    } catch (error) {
      setMessages(prev => [...prev, {
        role: "assistant",
        content: `采集出错：${error.message}`,
        ts: nowTs(),
      }]);
    } finally {
      setLoading(false);
    }
  }

  async function handleInterviewConfirm() {
    if (!activeInterview?.sessionId) return;
    setLoading(true);
    try {
      const data = await doctorInterviewConfirm(activeInterview.sessionId, doctorId);
      setMessages(prev => [...prev, {
        role: "assistant",
        content: data.preview
          ? `病历草稿已生成：\n\n${data.preview}\n\n请确认保存或取消。`
          : "病历草稿已生成，请确认保存。",
        ts: nowTs(),
      }]);
      setActiveInterview(null);
    } catch (error) {
      setMessages(prev => [...prev, {
        role: "assistant",
        content: `生成失败：${error.message}`,
        ts: nowTs(),
      }]);
    } finally {
      setLoading(false);
    }
  }

  async function handleInterviewCancel() {
    if (activeInterview?.sessionId) {
      try { await doctorInterviewCancel(activeInterview.sessionId, doctorId); } catch { /* ignore */ }
    }
    setActiveInterview(null);
    setMessages(prev => [...prev, {
      role: "assistant",
      content: "病历采集已取消。",
      ts: nowTs(),
    }]);
  }

  const isProcessing = mediaProcessing;

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <ChatTopbar isMobile={isMobile} doctorId={doctorId} onClearClick={() => setClearConfirmOpen(true)} />
      <Box sx={{ flex: 1, overflowY: "auto", py: 2, display: "flex", flexDirection: "column", gap: isMobile ? 1.8 : 1.4, bgcolor: "#ededed" }}>
        {messages.map((msg, idx) => (
          <MsgBubble key={`${msg.role}-${idx}`} msg={msg} onQuickSend={sendText} />
        ))}
        {loading && <LoadingBubble isMobile={isMobile} />}
        <div ref={bottomRef} />
      </Box>
      {activeInterview && (
        <Box sx={{ px: 1.5, py: 0.8, borderTop: "1px solid #e0e0e0", bgcolor: "#f0f9f0",
          display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <Typography variant="caption" sx={{ color: "#2e7d32", fontWeight: 500 }}>
            病历采集中 {activeInterview.progress?.filled || 0}/{activeInterview.progress?.total || 7}
          </Typography>
          <Box sx={{ display: "flex", gap: 1 }}>
            {activeInterview.status === "ready_for_confirm" && (
              <Button size="small" variant="contained" disableElevation
                sx={{ bgcolor: "#07C160", "&:hover": { bgcolor: "#06ad56" }, fontSize: 12, py: 0.3 }}
                onClick={handleInterviewConfirm}>
                确认生成
              </Button>
            )}
            <Button size="small" variant="text" color="error" sx={{ fontSize: 12, py: 0.3 }}
              onClick={handleInterviewCancel}>
              取消
            </Button>
          </Box>
        </Box>
      )}
      {!activeInterview && (
        <QuickCommandBar activeChip={activeChip} onSelect={handleCommandSelect} />
      )}
      <input ref={fileInputRef} type="file" accept="image/*" style={{ display: "none" }}
        onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; processFile({ file: f, setMediaError, setMediaProcessing, setInput }); }} />
      <input ref={cameraInputRef} type="file" accept="image/*" capture="environment" style={{ display: "none" }}
        onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; processFile({ file: f, setMediaError, setMediaProcessing, setInput }); }} />
      <input ref={galleryInputRef} type="file" accept="image/*" style={{ display: "none" }}
        onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; processFile({ file: f, setMediaError, setMediaProcessing, setInput }); }} />
      <input ref={fileDocInputRef} type="file" accept=".pdf,.docx,.doc,.txt,image/jpeg,image/png" style={{ display: "none" }}
        onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; handleDocFile(f); }} />
      <ChipInput
        activeChip={activeChip}
        onRemoveChip={() => setActiveChip(null)}
        input={input}
        onInput={setInput}
        onSend={activeInterview ? handleInterviewSend : handleChipSend}
        loading={loading}
        isProcessing={isProcessing}
        failedText={failedText}
        onRetry={() => { setInput(failedText); setFailedText(null); }}
        onDismissFailed={() => setFailedText(null)}
        mediaError={mediaError}
        onDismissError={() => setMediaError(null)}
        fileInputRef={fileInputRef}
        isMobile={isMobile}
        voiceMode={voiceMode}
        voiceSupported={voiceSupported}
        onVoiceToggle={() => setVoiceMode(true)}
        onVoiceResult={(text) => { setVoiceMode(false); if (text) { setInput((prev) => (prev ? prev + " " + text : text)); } }}
        onVoiceCancel={() => setVoiceMode(false)}
        onActionPanelOpen={() => setActionPanelOpen(true)}
      />
      <ClearDialog open={clearConfirmOpen} onClear={onClear} onClose={() => setClearConfirmOpen(false)} />
      <ActionPanel open={actionPanelOpen} onClose={() => setActionPanelOpen(false)} onAction={handlePanelAction} />
      <PatientPickerDialog open={patientPickerOpen} onClose={() => setPatientPickerOpen(false)} doctorId={doctorId}
        onSelect={(patient) => { setPatientPickerOpen(false); sendText(`查询患者：${patient.name}`); }} />
      <ImportChoiceDialog open={Boolean(importChoice)} text={importChoice?.text || ""}
        onInsert={() => { setInput((prev) => (prev ? prev + "\n" + importChoice.text : importChoice.text)); setImportChoice(null); }}
        onImport={() => { sendText(importChoice.text); setImportChoice(null); }}
        onClose={() => setImportChoice(null)} />
    </Box>
  );
}
