/**
 * @route /doctor/patients/new
 *
 * 病历采集视图：医生输入患者信息，AI提取字段并跟踪进度。
 * 显示在患者列表右侧（替代患者详情面板）。
 */
import { useEffect, useRef, useState } from "react";
import { Alert, Box, Button, CircularProgress, IconButton, Stack, Typography } from "@mui/material";
import SendOutlinedIcon from "@mui/icons-material/SendOutlined";
import AddCircleOutlineIcon from "@mui/icons-material/AddCircleOutline";
import MicIcon from "@mui/icons-material/Mic";
import KeyboardIcon from "@mui/icons-material/Keyboard";
import { useApi } from "../../api/ApiContext";
import { useAppNavigate } from "../../hooks/useAppNavigate";
import SubpageHeader from "../../components/SubpageHeader";
import ConfirmDialog from "../../components/ConfirmDialog";
import SuggestionChips from "../../components/SuggestionChips";
import VoiceInput, { isVoiceSupported } from "../../components/VoiceInput";
import ActionPanel from "../../components/ActionPanel";
import ImportChoiceDialog from "../../components/ImportChoiceDialog";
import FieldReviewCard from "../../components/doctor/FieldReviewCard";
import InterviewCompleteDialog from "../../components/doctor/InterviewCompleteDialog";
import { TYPE, COLOR, RADIUS } from "../../theme";
import { dp } from "../../utils/doctorBasePath";
import MsgAvatar from "../../components/MsgAvatar";
import { nowTs } from "../../utils/time";

function MsgBubble({ msg }) {
  const isUser = msg.role === "user";
  return (
    <Box sx={{ display: "flex", flexDirection: isUser ? "row-reverse" : "row", alignItems: "flex-end", gap: 1, px: 1.5 }}>
      <MsgAvatar isUser={isUser} size={32} />
      <Box sx={{ maxWidth: "75%", px: 1.5, py: 1, borderRadius: isUser ? `${RADIUS.sm} ${RADIUS.sm} 0 ${RADIUS.sm}` : `${RADIUS.sm} ${RADIUS.sm} ${RADIUS.sm} 0`,
        bgcolor: isUser ? COLOR.wechatGreen : COLOR.white, fontSize: TYPE.body.fontSize, whiteSpace: "pre-wrap", lineHeight: 1.7 }}>
        {msg.content}
      </Box>
    </Box>
  );
}

export default function InterviewPage({ doctorId, sessionId: resumeSessionId, patientContext, prePopulated, onComplete, onCancel }) {
  const navigate = useAppNavigate();
  const { doctorInterviewTurn, doctorInterviewConfirm, doctorInterviewCancel, doctorInterviewGetSession, confirmCarryForward, triggerDiagnosis, updateInterviewField, ocrImage } = useApi();
  const patientName = patientContext?.name;
  const importFieldCount = prePopulated ? Object.values(prePopulated).filter(v => v && v.trim()).length : 0;
  const welcomeMsg = importFieldCount > 0
    ? `已从导入内容中识别 ${importFieldCount} 个字段，请确认或编辑。\n缺少的字段可以在下方对话中补充。`
    : patientName
      ? `正在为 ${patientName} 建立门诊记录。\n请输入症状、检查结果等信息，我会帮您结构化记录。`
      : "病历采集模式已开启。\n请输入患者信息（姓名、性别、年龄、症状等），我会帮您结构化记录。";
  const [messages, setMessages] = useState([{
    role: "assistant",
    content: welcomeMsg,
    ts: nowTs(),
  }]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [voiceMode, setVoiceMode] = useState(false);
  const [actionPanelOpen, setActionPanelOpen] = useState(false);
  const [importChoice, setImportChoice] = useState(null);
  const cameraInputRef = useRef(null);
  const fileInputRef = useRef(null);
  const voiceSupported = isVoiceSupported();
  const [session, setSession] = useState({
    sessionId: resumeSessionId || null,
    progress: { filled: 0, total: 7 },
    status: "interviewing",
    patientId: patientContext?.id || null,
    collected: {},
  });
  // Update welcome message if patientContext arrives after mount
  useEffect(() => {
    if (patientContext?.name && messages.length === 1 && messages[0].role === "assistant") {
      setMessages([{
        role: "assistant",
        content: `正在为 ${patientContext.name} 建立门诊记录。\n请输入症状、检查结果等信息，我会帮您结构化记录。`,
        ts: nowTs(),
      }]);
      setSession(prev => ({ ...prev, patientId: patientContext.id }));
    }
  }, [patientContext?.name]); // eslint-disable-line react-hooks/exhaustive-deps

  const [error, setError] = useState(null);
  const [suggestions, setSuggestions] = useState([]);
  const [selectedSuggestions, setSelectedSuggestions] = useState([]);
  const [carryForward, setCarryForward] = useState([]);
  const [importItems, setImportItems] = useState(() => {
    if (!prePopulated || Object.keys(prePopulated).length === 0) return [];
    const FIELD_LABELS = {
      department: "科室", chief_complaint: "主诉", present_illness: "现病史",
      past_history: "既往史", allergy_history: "过敏史", personal_history: "个人史",
      marital_reproductive: "婚育史", family_history: "家族史", physical_exam: "体格检查",
      specialist_exam: "专科检查", auxiliary_exam: "辅助检查", diagnosis: "初步诊断",
      treatment_plan: "治疗方案", orders_followup: "医嘱随访",
    };
    return Object.entries(prePopulated)
      .filter(([, v]) => v && v.trim())
      .map(([field, value]) => ({ field, label: FIELD_LABELS[field] || field, value }));
  });
  const [showCompleteDialog, setShowCompleteDialog] = useState(false);
  const [showCancelConfirm, setShowCancelConfirm] = useState(false);
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
          collected: data.collected || {},
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
        collected: data.collected || prev.collected,
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
          collected: data.collected || prev.collected,
        }));
      } catch (err) {
        setError(err.message);
        break;
      }
    }
  }

  function handleImportConfirm(field) {
    setImportItems(prev => prev.filter(item => item.field !== field));
  }

  async function handleImportEdit(field, newValue) {
    if (!session.sessionId) return;
    try {
      const data = await updateInterviewField(session.sessionId, doctorId, field, newValue);
      setSession(prev => ({
        ...prev,
        progress: data.progress,
        status: data.status,
        collected: data.collected || prev.collected,
      }));
      setImportItems(prev => prev.filter(item => item.field !== field));
    } catch (err) {
      setError(err.message);
    }
  }

  function handleImportConfirmAll() {
    setImportItems([]);
  }

  function handlePanelAction(action) {
    setActionPanelOpen(false);
    if (action === "camera") cameraInputRef.current?.click();
    else if (action === "gallery") cameraInputRef.current?.click();
    else if (action === "file") fileInputRef.current?.click();
  }

  async function handleCameraFile(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      if (ocrImage) {
        const result = await ocrImage(file);
        if (result?.text) setImportChoice({ text: result.text });
      }
    } catch { /* silent */ }
    e.target.value = "";
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
      if (session.patientId) {
        formData.append("patient_id", String(session.patientId));
      }

      const data = await doctorInterviewTurn(formData);

      setSession({
        sessionId: data.session_id,
        progress: data.progress,
        status: data.status,
        patientId: data.patient_id,
        collected: data.collected || {},
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

  async function handleConfirm(nameOverride) {
    if (!session.sessionId) return null;
    setLoading(true);
    try {
      const data = await doctorInterviewConfirm(session.sessionId, doctorId, nameOverride);
      setMessages(prev => [...prev, {
        role: "assistant",
        content: data.preview
          ? `病历草稿已生成：\n\n${data.preview}\n\n请在聊天中确认保存。`
          : "病历草稿已生成，请在聊天中确认保存。",
        ts: nowTs(),
      }]);
      setSession(prev => ({ ...prev, status: "draft_created" }));
      setShowCompleteDialog(false);
      onComplete?.(data);
      return data;
    } catch (err) {
      setError(err.message);
      return null;
    } finally {
      setLoading(false);
    }
  }

  async function handleSaveOnly(nameOverride) {
    await handleConfirm(nameOverride);
  }

  async function handleSaveAndDiagnose(nameOverride) {
    const data = await handleConfirm(nameOverride);
    if (!data) return;
    const recordId = data.pending_id;
    if (!recordId) return;
    try {
      await triggerDiagnosis(recordId, doctorId);
    } catch (err) {
      // Diagnosis trigger is best-effort; navigate to review regardless
    }
    navigate(`${dp("review")}/${recordId}`);
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
      <SubpageHeader title="新建病历" onBack={() => {
          const hasWork = session.sessionId || messages.length > 1 || input.trim();
          hasWork ? setShowCancelConfirm(true) : handleCancel();
        }}
      />

      {/* Compact status line: counts + 完成 button */}
      {session.sessionId && session.status !== "draft_created" && (
        <Box sx={{ px: 1.5, py: 0.75, bgcolor: COLOR.white, borderBottom: `1px solid ${COLOR.border}`,
          display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
            <Typography variant="caption" sx={{ color: session.collected?._patient_name ? COLOR.text1 : COLOR.text4, fontWeight: session.collected?._patient_name ? 600 : 400 }}>
              {session.collected?._patient_name || "未命名"}
            </Typography>
            <Typography variant="caption" sx={{ color: COLOR.text4 }}>·</Typography>
            <Typography variant="caption" sx={{ color: session.progress.can_complete ? COLOR.successText : COLOR.text4, fontWeight: 500 }}>
              必填 {session.progress.required_count || 0}/{session.progress.required_total || 0}{session.progress.can_complete ? " ✓" : ""}
            </Typography>
            <Typography variant="caption" sx={{ color: COLOR.text4 }}>
              其他 {(session.progress.filled || 0) - (session.progress.required_count || 0)}/{(session.progress.total || 0) - (session.progress.required_total || 0)}
            </Typography>
          </Box>
          <Button size="small"
            variant={session.progress.can_complete ? "contained" : "text"}
            disableElevation
            sx={session.progress.can_complete
              ? { bgcolor: COLOR.primary, "&:hover": { bgcolor: COLOR.primaryHover }, fontSize: TYPE.caption.fontSize, py: 0, minHeight: 24 }
              : { color: COLOR.text4, fontSize: TYPE.caption.fontSize, py: 0, minHeight: 24 }
            }
            onClick={() => setShowCompleteDialog(true)} disabled={loading || !session.progress.can_complete}>
            完成
          </Button>
        </Box>
      )}

      {/* Import preview card — fields extracted from photo/PDF/text import */}
      {importItems.length > 0 && session.status !== "draft_created" && (
        <FieldReviewCard
          title="已从导入提取"
          subtitle={`${importItems.length} 项待确认`}
          items={importItems}
          confirmLabel="确认"
          dismissLabel="编辑"
          confirmAllLabel="全部确认"
          onConfirm={handleImportConfirm}
          onEdit={handleImportEdit}
          onConfirmAll={handleImportConfirmAll}
          editable
          disabled={loading}
        />
      )}

      {/* Carry-forward card — prior record fields for one-tap confirmation */}
      {carryForward.length > 0 && session.status !== "draft_created" && (
        <FieldReviewCard
          title={`上次记录${carryForward[0]?.source_date ? ` (${carryForward[0].source_date})` : ""}`}
          subtitle={`${carryForward.length} 项可沿用`}
          items={carryForward}
          confirmLabel="沿用"
          dismissLabel="忽略"
          confirmAllLabel="全部沿用"
          onConfirm={handleCarryForwardConfirm}
          onDismiss={handleCarryForwardDismiss}
          onConfirmAll={handleCarryForwardConfirmAll}
          disabled={loading}
        />
      )}

      {/* Messages */}
      <Box sx={{ flex: 1, overflowY: "auto", py: 2, display: "flex", flexDirection: "column", gap: 1.5, bgcolor: COLOR.surfaceAlt }}>
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
        <Box sx={{ px: 1.5, py: 1, borderTop: `1px solid ${COLOR.border}`, bgcolor: COLOR.primaryLight,
          display: "flex", alignItems: "center", justifyContent: "center" }}>
          <Typography variant="caption" sx={{ color: COLOR.successText }}>
            草稿已生成
          </Typography>
        </Box>
      )}

      {/* LLM suggestions — clickable quick-reply chips */}
      {session.status !== "draft_created" && !loading && suggestions.length > 0 && (
        <SuggestionChips
          items={suggestions}
          selected={selectedSuggestions}
          onToggle={handleToggleSuggestion}
          onDismiss={() => setSuggestions([])}
          disabled={loading}
        />
      )}

      {/* Bottom banner removed — single 完成 button in status line is sufficient */}

      {/* Input bar — WeChat style: voice toggle | text input | + actions | send */}
      {session.status !== "draft_created" && (
        <>
          {voiceMode && (
            <Box sx={{ px: 1, py: 1, borderTop: `1px solid ${COLOR.border}`, bgcolor: COLOR.surface, display: "flex", alignItems: "center", gap: 0.5 }}>
              <IconButton onClick={() => setVoiceMode(false)} sx={{ color: COLOR.text4, p: 1, flexShrink: 0 }}>
                <KeyboardIcon sx={{ fontSize: 22 }} />
              </IconButton>
              <Box sx={{ flex: 1 }}>
                <VoiceInput
                  onResult={(text) => { setInput((prev) => prev ? prev + text : text); setVoiceMode(false); }}
                  onCancel={() => setVoiceMode(false)}
                />
              </Box>
            </Box>
          )}
          {!voiceMode && (
            <Box sx={{ borderTop: `1px solid ${COLOR.border}`, bgcolor: COLOR.surface, px: 1, py: 1,
              display: "flex", alignItems: "flex-end", gap: 0.5 }}>
              {/* Voice toggle */}
              {voiceSupported && (
                <IconButton onClick={() => setVoiceMode(true)} sx={{ color: COLOR.text4, p: 1 }}>
                  <MicIcon sx={{ fontSize: 22 }} />
                </IconButton>
              )}
              {/* Text input with suggestion chips */}
              <Box sx={{ flex: 1, bgcolor: COLOR.white, borderRadius: RADIUS.sm, px: 1, py: 0.5,
                display: "flex", flexWrap: "wrap", alignItems: "center", gap: 0.5, minHeight: 36 }}>
                {selectedSuggestions.map((s, i) => (
                  <Box key={i} sx={{
                    display: "inline-flex", alignItems: "center", gap: 0.5,
                    px: 1, py: 0.5, borderRadius: RADIUS.lg, fontSize: TYPE.secondary.fontSize,
                    bgcolor: COLOR.successLight, color: COLOR.primary, fontWeight: 500, flexShrink: 0,
                  }}>
                    {s}
                    <Box component="span"
                      onClick={() => setSelectedSuggestions(prev => prev.filter(x => x !== s))}
                      sx={{ cursor: "pointer", fontSize: TYPE.body.fontSize, lineHeight: 1, ml: 0.5, "&:active": { opacity: 0.5 } }}>
                      ×
                    </Box>
                  </Box>
                ))}
                <Box component="input" ref={inputRef} value={input}
                  onChange={e => setInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  disabled={loading}
                  placeholder={selectedSuggestions.length > 0 ? "" : "输入患者信息..."}
                  sx={{ flex: 1, minWidth: 60, border: "none", outline: "none", fontSize: TYPE.body.fontSize,
                    fontFamily: "inherit", bgcolor: "transparent", p: 0.5 }}
                />
              </Box>
              {/* Action panel toggle (camera, gallery, file) */}
              <IconButton onClick={() => setActionPanelOpen(true)} sx={{ color: COLOR.text4, p: 1 }}>
                <AddCircleOutlineIcon sx={{ fontSize: 24 }} />
              </IconButton>
              {/* Send button */}
              <IconButton onClick={() => handleSend()} disabled={loading || (!input.trim() && selectedSuggestions.length === 0)}
                sx={{ bgcolor: COLOR.primary, color: COLOR.white, p: 1, borderRadius: "50%",
                  "&:hover": { bgcolor: COLOR.primaryHover }, "&.Mui-disabled": { bgcolor: COLOR.text4, color: COLOR.white } }}>
                <SendOutlinedIcon fontSize="small" />
              </IconButton>
            </Box>
          )}
        </>
      )}

      {/* Hidden camera/gallery input (images only) */}
      <input ref={cameraInputRef} type="file" accept="image/*" capture="environment"
        style={{ display: "none" }} onChange={handleCameraFile} />
      {/* Hidden file input (documents + images) */}
      <input ref={fileInputRef} type="file" accept="image/*,.pdf,.doc,.docx"
        style={{ display: "none" }} onChange={handleCameraFile} />

      {/* Action panel (camera, gallery, file) */}
      <ActionPanel open={actionPanelOpen} onClose={() => setActionPanelOpen(false)} onAction={handlePanelAction} />

      {/* Import choice dialog (OCR result → send to interview) */}
      <ImportChoiceDialog
        open={Boolean(importChoice)} text={importChoice?.text || ""}
        onInterview={(text) => { setImportChoice(null); setInput(text); }}
        onChat={(text) => { setImportChoice(null); setInput(text); }}
        onClose={() => setImportChoice(null)}
      />

      {error && <Alert severity="error" onClose={() => setError(null)} sx={{ mx: 1, mb: 0.5 }}>{error}</Alert>}

      <ConfirmDialog
        open={showCancelConfirm}
        onClose={() => setShowCancelConfirm(false)}
        onCancel={() => setShowCancelConfirm(false)}
        onConfirm={() => { setShowCancelConfirm(false); handleCancel(); }}
        title="确认离开？"
        message="未保存的内容将会丢失"
        confirmLabel="离开"
        cancelLabel="取消"
        confirmTone="danger"
      />

      {/* Interview complete dialog — preview fields + save/diagnose */}
      <InterviewCompleteDialog
        open={showCompleteDialog}
        fields={session.collected}
        fieldCount={(() => {
          const fields = session.progress?.fields || {};
          const total = Object.keys(fields).length || 14;
          const filled = Object.values(fields).filter(f => f.status !== "empty").length;
          return { filled, total };
        })()}
        onSave={handleSaveOnly}
        onSaveAndDiagnose={handleSaveAndDiagnose}
        onClose={() => setShowCompleteDialog(false)}
      />
    </Box>
  );
}
