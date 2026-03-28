/**
 * @route /doctor/chat
 *
 * 聊天面板：医生与 AI 助手对话，支持图片上传和快捷命令。
 */
import { useEffect, useMemo, useRef, useState } from "react";
import {
  Alert, Box, Button, CircularProgress, IconButton, Stack, Tooltip, Typography,
} from "@mui/material";
import useMediaQuery from "@mui/material/useMediaQuery";
import { useTheme } from "@mui/material/styles";
import SendOutlinedIcon from "@mui/icons-material/SendOutlined";
import AttachFileOutlinedIcon from "@mui/icons-material/AttachFileOutlined";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import SmartToyOutlinedIcon from "@mui/icons-material/SmartToyOutlined";
import LocalHospitalOutlinedIcon from "@mui/icons-material/LocalHospitalOutlined";
import Markdown from "react-markdown";
import PersonOutlineIcon from "@mui/icons-material/PersonOutline";
import DescriptionOutlinedIcon from "@mui/icons-material/DescriptionOutlined";
import AssignmentOutlinedIcon from "@mui/icons-material/AssignmentOutlined";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import { useApi } from "../../api/ApiContext";
import RecordFields from "../../components/RecordFields";
import { t } from "../../i18n";
import { QUICK_COMMANDS, Action } from "./constants";
import ActionPanel from "../../components/ActionPanel";
import PatientPickerDialog from "../../components/PatientPickerDialog";
import ImportChoiceDialog from "../../components/ImportChoiceDialog";
import VoiceInput, { isVoiceSupported } from "../../components/VoiceInput";
import AddCircleOutlineIcon from "@mui/icons-material/AddCircleOutline";
import MicNoneOutlinedIcon from "@mui/icons-material/MicNoneOutlined";
import BarButton from "../../components/BarButton";
import SubpageHeader from "../../components/SubpageHeader";
import ConfirmDialog from "../../components/ConfirmDialog";
import { useAppNavigate } from "../../hooks/useAppNavigate";
import { TYPE, ICON } from "../../theme";

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
          <Typography variant="body2" sx={{ fontWeight: 600, fontSize: TYPE.secondary.fontSize }}>
            {typeLabels[t.task_type] || "任务"} · {t.title || "未命名"}
          </Typography>
          {t.due_at && <Typography variant="caption" color="text.secondary">{t.due_at.replace("T", " ").slice(0, 16)}</Typography>}
        </Box>
      ))}
    </Box>
  );
}

/* ── Data Cards (rendered below AI reply bubble) ── */

const cardRowSx = {
  display: "flex", alignItems: "center", gap: 1, py: 0.8,
  borderBottom: "1px solid #f5f5f5", cursor: "pointer",
  "&:last-child": { borderBottom: "none" },
  "&:active": { bgcolor: "#fafafa" },
};
const cardIconSx = (bg) => ({
  width: 28, height: 28, borderRadius: "6px", bgcolor: bg,
  display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0,
});

function PatientCards({ patients, onNavigate, max = 5 }) {
  if (!patients?.length) return null;
  const shown = patients.slice(0, max);
  return (
    <Box sx={{ mt: 1, borderTop: "1px solid #e5e5e5", pt: 0.5 }}>
      {shown.map((p) => (
        <Box key={p.id} sx={cardRowSx} onClick={() => onNavigate(`/doctor/patients/${p.id}`)}>
          <Box sx={cardIconSx("#e3f2fd")}><PersonOutlineIcon sx={{ fontSize: 16, color: "#1565c0" }} /></Box>
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Typography sx={{ fontSize: TYPE.secondary.fontSize, fontWeight: 600, color: "#333" }} noWrap>{p.name}</Typography>
            <Typography sx={{ fontSize: TYPE.micro.fontSize, color: "#999" }} noWrap>
              {[p.gender === "male" ? "男" : p.gender === "female" ? "女" : p.gender, p.age ? `${p.age}岁` : null].filter(Boolean).join(" · ")}
            </Typography>
          </Box>
          <ChevronRightIcon sx={{ fontSize: 16, color: "#ccc" }} />
        </Box>
      ))}
      {patients.length > max && (
        <Typography sx={{ fontSize: TYPE.micro.fontSize, color: "#07C160", textAlign: "center", pt: 0.5, cursor: "pointer" }}
          onClick={() => onNavigate("/doctor/patients")}>
          查看全部 ({patients.length})
        </Typography>
      )}
    </Box>
  );
}

function RecordCards({ records, onNavigate, max = 5 }) {
  if (!records?.length) return null;
  const shown = records.slice(0, max);
  return (
    <Box sx={{ mt: 1, borderTop: "1px solid #e5e5e5", pt: 0.5 }}>
      {shown.map((r, i) => (
        <Box key={r.id || i} sx={cardRowSx} onClick={() => r.patient_id ? onNavigate(`/doctor/patients/${r.patient_id}`) : null}>
          <Box sx={cardIconSx("#e8f5e9")}><DescriptionOutlinedIcon sx={{ fontSize: 16, color: "#07C160" }} /></Box>
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Typography sx={{ fontSize: TYPE.secondary.fontSize, fontWeight: 600, color: "#333" }} noWrap>
              {r.patient_name || "患者"} · {r.chief_complaint || r.record_type || "病历"}
            </Typography>
            <Typography sx={{ fontSize: TYPE.micro.fontSize, color: "#999" }} noWrap>
              {r.created_at ? r.created_at.slice(0, 10) : ""}
            </Typography>
          </Box>
          <ChevronRightIcon sx={{ fontSize: 16, color: "#ccc" }} />
        </Box>
      ))}
      {records.length > max && (
        <Typography sx={{ fontSize: TYPE.micro.fontSize, color: "#07C160", textAlign: "center", pt: 0.5 }}>
          共 {records.length} 条记录
        </Typography>
      )}
    </Box>
  );
}

function TaskCards({ tasks, onNavigate, max = 5 }) {
  if (!tasks?.length) return null;
  const shown = tasks.slice(0, max);
  const typeLabels = { follow_up: "随访", medication: "用药", checkup: "检查", general: "任务", review: "审核" };
  return (
    <Box sx={{ mt: 1, borderTop: "1px solid #e5e5e5", pt: 0.5 }}>
      {shown.map((tk) => (
        <Box key={tk.id} sx={cardRowSx} onClick={() => tk.patient_id ? onNavigate(`/doctor/patients/${tk.patient_id}`) : onNavigate("/doctor/tasks")}>
          <Box sx={cardIconSx("#fff3e0")}><AssignmentOutlinedIcon sx={{ fontSize: 16, color: "#e8833a" }} /></Box>
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Typography sx={{ fontSize: TYPE.secondary.fontSize, fontWeight: 600, color: "#333" }} noWrap>
              {typeLabels[tk.task_type] || "任务"} · {tk.title || "未命名"}
            </Typography>
            <Typography sx={{ fontSize: TYPE.micro.fontSize, color: "#999" }} noWrap>
              {tk.due_at ? tk.due_at.replace("T", " ").slice(0, 16) : tk.status || ""}
            </Typography>
          </Box>
          <ChevronRightIcon sx={{ fontSize: 16, color: "#ccc" }} />
        </Box>
      ))}
      {tasks.length > max && (
        <Typography sx={{ fontSize: TYPE.micro.fontSize, color: "#07C160", textAlign: "center", pt: 0.5 }}
          onClick={() => onNavigate("/doctor/tasks")}>
          查看全部 ({tasks.length})
        </Typography>
      )}
    </Box>
  );
}

function DataCards({ viewPayload, onNavigate }) {
  if (!viewPayload) return null;
  const vp = viewPayload;
  if (vp.patients?.length) return <PatientCards patients={vp.patients} onNavigate={onNavigate} />;
  if (vp.records?.length) return <RecordCards records={vp.records} onNavigate={onNavigate} />;
  if (vp.tasks?.length) return <TaskCards tasks={vp.tasks} onNavigate={onNavigate} />;
  if (vp.task_id) return <TaskCards tasks={[{ id: vp.task_id, title: vp.title, task_type: vp.task_type || "general" }]} onNavigate={onNavigate} />;
  return null;
}

/* Minimal markdown styles scoped to AI message bubbles */
const mdStyles = {
  "& p": { m: 0, lineHeight: 1.7 },
  "& p + p": { mt: 0.8 },
  "& strong": { fontWeight: 600 },
  "& hr": { border: "none", borderTop: "1px solid #e5e5e5", my: 1 },
  "& ul, & ol": { m: 0, pl: 2.5 },
  "& li": { lineHeight: 1.7 },
  "& h1,& h2,& h3,& h4": { fontSize: TYPE.heading.fontSize, fontWeight: 600, mt: 1, mb: 0.5 },
  "& code": { fontSize: TYPE.caption.fontSize, bgcolor: "#f5f5f5", px: 0.5, borderRadius: 0.5 },
};

function MsgBubble({ msg, onQuickSend, onNavigate }) {
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
                  px: 0.8, py: 0.1, borderRadius: "2px", fontSize: TYPE.caption.fontSize, color: "#555", mr: 0.8, verticalAlign: "middle" }}>
                  {msg.actionLabel}
                </Box>
              )}
              {msg.actionLabel && msg.content === msg.actionLabel ? null : msg.content}
            </Typography>
          ) : (
            <Box sx={{ fontSize: TYPE.body.fontSize, color: textColor, ...mdStyles }}>
              <Markdown>{msg.content}</Markdown>
            </Box>
          )}
          {!isUser && msg.record ? <RecordFields record={msg.record} /> : null}
          {!isUser && msg.view_payload?.type === "tasks_list" ? <TasksCard tasks={msg.view_payload.data} /> : null}
          {!isUser && msg.view_payload && onNavigate ? <DataCards viewPayload={msg.view_payload} onNavigate={onNavigate} /> : null}
          {hasPending && onQuickSend && (
            <Stack direction="row" spacing={1} sx={{ mt: 1.5, pt: 1, borderTop: "1px solid #e5e5e5" }}>
              <Button size="small" variant="contained" disableElevation
                sx={{ bgcolor: "#07C160", "&:hover": { bgcolor: "#06a050" }, textTransform: "none", fontSize: TYPE.secondary.fontSize, borderRadius: 1 }}
                onClick={() => onQuickSend("确认")}>
                确认保存
              </Button>
              <Button size="small" variant="outlined" disableElevation
                sx={{ color: "#999", borderColor: "#d9d9d9", textTransform: "none", fontSize: TYPE.secondary.fontSize, borderRadius: 1 }}
                onClick={() => onQuickSend("取消")}>
                取消
              </Button>
            </Stack>
          )}
        </Box>
        <Typography sx={{ mt: isMobile ? 0.3 : 0.4, px: 0.5, color: isMobile ? "#888" : "#aaa", fontSize: TYPE.micro.fontSize }}>
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
        <SmartToyOutlinedIcon sx={{ color: "#fff", fontSize: ICON.lg }} />
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
              fontSize: TYPE.secondary.fontSize, fontFamily: "inherit", whiteSpace: "nowrap",
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
      <Button size="small" variant="text" color="error" sx={{ fontSize: TYPE.caption.fontSize, py: 0, minWidth: "auto" }} onClick={onRetry}>重试</Button>
      <Button size="small" variant="text" sx={{ fontSize: TYPE.caption.fontSize, py: 0, minWidth: "auto", color: "text.secondary" }} onClick={onDismiss}>忽略</Button>
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
                color: "#333", px: 1, py: 0.25, borderRadius: "3px", fontSize: TYPE.caption.fontSize, whiteSpace: "nowrap",
                border: "1px solid #ddd", flexShrink: 0 }}>
                {activeChip.label}
                <Box component="span" onClick={onRemoveChip}
                  sx={{ color: "#999", ml: 0.3, cursor: "pointer", fontSize: TYPE.micro.fontSize, lineHeight: 1, "&:hover": { color: "#666" } }}>
                  ✕
                </Box>
              </Box>
            )}
            <Box component="input" ref={inputRef} value={input}
              onChange={(e) => onInput(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={isProcessing}
              placeholder={activeChip ? "输入内容..." : "输入消息..."}
              sx={{ flex: 1, border: "none", outline: "none", fontSize: TYPE.body.fontSize, fontFamily: "inherit",
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

async function performSend({ text, loading, doctorId, history, sendChat, setMessages, setInput, setLoading, setFailedText, onPatientCreated, onStartPatientInterview, actionHint, actionLabel }) {
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
    // If routing LLM started an interview session, switch to interview UI
    if (data.view_payload?.session_id && onStartPatientInterview) {
      onStartPatientInterview(data.view_payload.session_id);
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

function useChatState({ doctorId, onMessageCountChange, onPatientCreated, onStartPatientInterview, onContextCleared }) {
  const { sendChat, clearContext } = useApi();
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
    return performSend({ text, loading, doctorId, history, sendChat, setMessages, setInput, setLoading, setFailedText, onPatientCreated, onStartPatientInterview, actionHint, actionLabel });
  }

  return { input, setInput, loading, setLoading, failedText, setFailedText, messages, setMessages, bottomRef, onClear, sendText };
}

function ChatTopbar({ onClearClick, onBack }) {
  return (
    <SubpageHeader
      title={t("chat.workspaceTitle")}
      onBack={onBack}
      right={<BarButton onClick={onClearClick} color="#999">清空</BarButton>}
    />
  );
}

function ClearDialog({ open, onClear, onClose }) {
  return (
    <ConfirmDialog
      open={open}
      onClose={onClose}
      onCancel={onClose}
      onConfirm={() => { onClear(); onClose(); }}
      title="清空对话记录"
      message="确定清空所有对话记录、草稿和当前工作上下文？此操作无法撤销。"
      cancelLabel="返回"
      confirmLabel="清空"
      confirmTone="danger"
    />
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

async function processFile({ file, importToInterview, setMediaError, setMediaProcessing, doctorId, onStartPatientInterview }) {
  if (!file) return;
  setMediaError(null);
  if (!file.type.startsWith("image/")) {
    setMediaError("不支持的文件类型，请上传图片");
    return;
  }
  setMediaProcessing(true);
  try {
    const data = await importToInterview(file, doctorId);
    if (data.session_id) {
      onStartPatientInterview?.(data.session_id, data.pre_populated);
    }
  } catch {
    setMediaError("病历导入失败，请重试");
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

export default function ChatPage({ doctorId, onMessageCountChange, externalInput, onExternalInputConsumed, onPatientCreated, autoSendText, onAutoSendConsumed, onContextCleared, onStartPatientInterview, onBack, hideHeader }) {
  const { importToInterview, extractFileForChat, textToInterview } = useApi();
  const navigate = useAppNavigate();
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down("sm"));
  const [clearConfirmOpen, setClearConfirmOpen] = useState(false);
  const [mediaError, setMediaError] = useState(null);
  const [activeChip, setActiveChip] = useState(null);
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
    useChatState({ doctorId, onMessageCountChange, onPatientCreated, onStartPatientInterview, onContextCleared });
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
    setMediaProcessing(true);
    try {
      // Plain text files: read directly and go through text import
      if (file.type === "text/plain" || file.name?.endsWith(".txt")) {
        const text = await file.text();
        if (text?.trim()) {
          const data = await textToInterview(text, doctorId);
          if (data.session_id) {
            onStartPatientInterview?.(data.session_id, data.pre_populated);
            return;
          }
        }
        setMediaError("文件内容为空");
        return;
      }
      // Images/PDFs: try import endpoint first
      const data = await importToInterview(file, doctorId);
      if (data.session_id) {
        onStartPatientInterview?.(data.session_id, data.pre_populated);
      }
    } catch {
      // Fallback: extract text and show choice dialog
      try {
        const { text } = await extractFileForChat(file);
        if (text) setImportChoice({ text });
      } catch { setMediaError("文件处理失败"); }
    } finally {
      setMediaProcessing(false);
    }
  }

  function handleCommandSelect(cmd) {
    if (cmd.key === Action.CREATE_RECORD) {
      // Navigate to patients tab to start interview
      onStartPatientInterview?.();
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

  const isProcessing = mediaProcessing;

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%" }}>
      {!hideHeader && <ChatTopbar onClearClick={() => setClearConfirmOpen(true)} onBack={onBack} />}
      <Box sx={{ flex: 1, overflowY: "auto", py: 2, display: "flex", flexDirection: "column", gap: isMobile ? 1.8 : 1.4, bgcolor: "#ededed" }}>
        {messages.map((msg, idx) => (
          <MsgBubble key={`${msg.role}-${idx}`} msg={msg} onQuickSend={sendText} onNavigate={navigate} />
        ))}
        {loading && <LoadingBubble isMobile={isMobile} />}
        <div ref={bottomRef} />
      </Box>
      <QuickCommandBar activeChip={activeChip} onSelect={handleCommandSelect} />
      <input ref={fileInputRef} type="file" accept="image/*" style={{ display: "none" }}
        onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; processFile({ file: f, importToInterview, setMediaError, setMediaProcessing, doctorId, onStartPatientInterview }); }} />
      <input ref={cameraInputRef} type="file" accept="image/*" capture="environment" style={{ display: "none" }}
        onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; processFile({ file: f, importToInterview, setMediaError, setMediaProcessing, doctorId, onStartPatientInterview }); }} />
      <input ref={galleryInputRef} type="file" accept="image/*" style={{ display: "none" }}
        onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; processFile({ file: f, importToInterview, setMediaError, setMediaProcessing, doctorId, onStartPatientInterview }); }} />
      <input ref={fileDocInputRef} type="file" accept=".pdf,.docx,.doc,.txt,image/jpeg,image/png" style={{ display: "none" }}
        onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; handleDocFile(f); }} />
      <ChipInput
        activeChip={activeChip}
        onRemoveChip={() => setActiveChip(null)}
        input={input}
        onInput={setInput}
        onSend={handleChipSend}
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
        onImport={async () => {
          const text = importChoice?.text;
          setImportChoice(null);
          if (!text) return;
          setMediaProcessing(true);
          try {
            const data = await textToInterview(text, doctorId);
            if (data.session_id) onStartPatientInterview?.(data.session_id, data.pre_populated);
          } catch { sendText(text); }
          finally { setMediaProcessing(false); }
        }}
        onChat={(text) => { setImportChoice(null); sendText(text); }}
        onClose={() => setImportChoice(null)} />
    </Box>
  );
}
