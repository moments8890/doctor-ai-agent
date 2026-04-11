/**
 * InterviewPage — full-screen pre-consultation interview.
 *
 * Extracted from PatientPage.jsx (lines 822-1056).
 * Session management: start → turns → confirm/cancel.
 *
 * Props: token, onBack, onLogout
 */

import { useEffect, useState, useRef } from "react";
import {
  Box,
  Button,
  CircularProgress,
  IconButton,
  LinearProgress,
  Stack,
  Typography,
} from "@mui/material";
import SendIcon from "@mui/icons-material/Send";
import MicNoneOutlinedIcon from "@mui/icons-material/MicNoneOutlined";
import KeyboardOutlinedIcon from "@mui/icons-material/KeyboardOutlined";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";
import RadioButtonUncheckedIcon from "@mui/icons-material/RadioButtonUnchecked";
import MsgAvatar from "../../components/MsgAvatar";

import { usePatientApi } from "../../api/PatientApiContext";
import VoiceInput, { isVoiceSupported } from "../../components/VoiceInput";
import SubpageHeader from "../../components/SubpageHeader";
import SuggestionChips from "../../components/SuggestionChips";
import SheetDialog from "../../components/SheetDialog";
import ConfirmDialog from "../../components/ConfirmDialog";
import AppButton from "../../components/AppButton";
import BarButton from "../../components/BarButton";
import { TYPE, COLOR, RADIUS } from "../../theme";
import { FIELD_LABELS, PAGE_LAYOUT } from "./constants";

export default function InterviewPage({ token, onBack, onLogout, initialSuggestions }) {
  const { interviewStart, interviewTurn, interviewConfirm, interviewCancel } = usePatientApi();

  const [sessionId, setSessionId] = useState("");
  const [messages, setMessages] = useState([]);
  const [collected, setCollected] = useState({});
  const [progress, setProgress] = useState({ filled: 0, total: 7 });
  const [status, setStatus] = useState("interviewing");
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [showSummary, setShowSummary] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [showExitDialog, setShowExitDialog] = useState(false);
  const [showErrorDialog, setShowErrorDialog] = useState(false);
  const [suggestions, setSuggestions] = useState(() => {
    if (initialSuggestions?.length) return initialSuggestions;
    const params = new URLSearchParams(window.location.search);
    const starter = params.get("starter_suggestions");
    return starter ? starter.split(",").map(s => s.trim()).filter(Boolean) : [];
  });
  const [selectedSuggestions, setSelectedSuggestions] = useState([]);
  const [voiceMode, setVoiceMode] = useState(false);
  const [reviewReady, setReviewReady] = useState(false);
  const [reviewHintShown, setReviewHintShown] = useState(false);
  const voiceSupported = isVoiceSupported();
  const chatEndRef = useRef(null);
  const canSupplement = reviewReady && status !== "confirmed";
  const canInput = status === "interviewing" || canSupplement;

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
        if (err.status === 401) console.warn("auth expired");
        setMessages([{ role: "assistant", content: "无法启动问诊，请稍后重试。" }]);
      }
    })();
  }, [token]);

  useEffect(() => { chatEndRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  function handleToggleSuggestion(text) {
    setSelectedSuggestions(prev =>
      prev.includes(text) ? prev.filter(s => s !== text) : [...prev, text]
    );
  }

  async function handleSend(e) {
    if (e && e.preventDefault) e.preventDefault();
    const parts = [...selectedSuggestions];
    if (input.trim()) parts.push(input.trim());
    const text = parts.join("，");
    if (!text || sending || !canInput) return;
    setInput("");
    setSuggestions([]);
    setSelectedSuggestions([]);
    setMessages(prev => [...prev, { role: "user", content: text }]);
    setSending(true);
    try {
      const data = await interviewTurn(token, sessionId, text);
      setMessages(prev => [...prev, { role: "assistant", content: data.reply }]);
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
      if (err.status === 401) { console.warn("auth expired"); return; }
      setMessages(prev => [...prev, { role: "assistant", content: "系统暂时繁忙，请重新发送您的回答。" }]);
    } finally { setSending(false); }
  }

  async function handleConfirm() {
    setConfirming(true);
    try {
      const data = await interviewConfirm(token, sessionId);
      setStatus("confirmed");
      setShowSummary(false);
      setMessages(prev => [...prev, { role: "assistant", content: data.message }]);
    } catch (err) {
      if (err.status === 401) { console.warn("auth expired"); return; }
      setShowErrorDialog(true);
    } finally { setConfirming(false); }
  }

  async function handleExit(abandon) {
    setShowExitDialog(false);
    if (abandon) { try { await interviewCancel(token, sessionId); } catch {} }
    onBack();
  }

  function handleResumeInput() {
    setShowSummary(false);
    setStatus("interviewing");
  }

  const allFields = ["chief_complaint", "present_illness", "past_history", "allergy_history", "family_history", "personal_history", "marital_reproductive"];

  return (
    <Box sx={PAGE_LAYOUT}>
      {/*
        UI-DESIGN.md requires top-bar actions to be a single text-only BarButton.
        Keep progress/readiness in that slot instead of ad hoc chips.
      */}
      <SubpageHeader title="新建病历" onBack={() => status === "confirmed" ? onBack() : setShowExitDialog(true)}
        right={
          status === "confirmed" ? null : (
            <BarButton
              onClick={reviewReady ? () => setShowSummary(true) : undefined}
              disabled={!reviewReady}
              color={reviewReady ? COLOR.primary : COLOR.text4}
            >
              {reviewReady ? "提交" : `${progress.total ? Math.round((progress.filled / progress.total) * 100) : 0}%`}
            </BarButton>
          )
        }
      />

      {/* Progress bar */}
      <Box sx={{ px: 2, py: 0.5, bgcolor: COLOR.white, borderBottom: `1px solid ${COLOR.borderLight}` }}>
        <LinearProgress variant="determinate"
          value={progress.total ? (progress.filled / progress.total) * 100 : 0}
          sx={{ height: 6, borderRadius: RADIUS.sm, bgcolor: COLOR.border,
            "& .MuiLinearProgress-bar": { bgcolor: COLOR.primary, borderRadius: RADIUS.sm } }} />
        <Typography variant="caption" sx={{ color: COLOR.text4, mt: 0.5, display: "block" }}>
          {progress.total ? Math.round((progress.filled / progress.total) * 100) : 0}%
        </Typography>
      </Box>

      {/* Chat */}
      <Box sx={{ flex: 1, overflowY: "auto", px: 2, py: 2 }}>
        {messages.map((msg, i) => (
          <Box key={i} sx={{ display: "flex", alignItems: "flex-start", gap: 1, mb: 1.5, flexDirection: msg.role === "user" ? "row-reverse" : "row" }}>
            <MsgAvatar isUser={msg.role === "user"} size={32} />
            <Box sx={{
              maxWidth: "75%", px: 2, py: 1.5, borderRadius: RADIUS.sm,
              bgcolor: msg.role === "user" ? COLOR.wechatGreen : COLOR.white,
              color: COLOR.text2, fontSize: TYPE.body.fontSize, lineHeight: 1.6,
              whiteSpace: "pre-wrap", wordBreak: "break-word",
            }}>{msg.content}</Box>
          </Box>
        ))}
        {sending && (
          <Box sx={{ display: "flex", justifyContent: "flex-start", mb: 1.5 }}>
            <Box sx={{ px: 2, py: 1.5, borderRadius: 2, bgcolor: COLOR.white }}><CircularProgress size={16} /></Box>
          </Box>
        )}
        <div ref={chatEndRef} />
      </Box>

      {/* Suggestion chips — floating above input */}
      {canInput && !sending && suggestions.length > 0 && (
        <SuggestionChips
          items={suggestions}
          selected={selectedSuggestions}
          onToggle={handleToggleSuggestion}
          onDismiss={() => setSuggestions([])}
          disabled={sending}
        />
      )}

      {/* Input with selected chips */}
      {canInput && (
        <Box component="form" onSubmit={handleSend}
          sx={{ display: "flex", alignItems: "flex-end", gap: 1, px: 2, py: 1, bgcolor: COLOR.surface,
            borderTop: suggestions.length > 0 ? "none" : `1px solid ${COLOR.border}`, flexShrink: 0 }}>
          {voiceSupported && (
            <IconButton onClick={() => setVoiceMode(v => !v)}
              sx={{ color: COLOR.text3, flexShrink: 0, alignSelf: "center" }}
              aria-label={voiceMode ? "切换键盘" : "切换语音"}>
              {voiceMode ? <KeyboardOutlinedIcon /> : <MicNoneOutlinedIcon />}
            </IconButton>
          )}
          {voiceMode ? (
            <Box sx={{ flex: 1, display: "flex", flexDirection: "column", gap: 0.5, minHeight: 36 }}>
              {selectedSuggestions.length > 0 && (
                <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.5 }}>
                  {selectedSuggestions.map((s, i) => (
                    <Box key={i} sx={{
                      display: "inline-flex", alignItems: "center", gap: 0.5,
                      px: 1, py: 0.5, borderRadius: RADIUS.lg, fontSize: TYPE.secondary.fontSize,
                      bgcolor: COLOR.successLight, color: COLOR.primary, fontWeight: 500, flexShrink: 0,
                    }}>
                      {s}
                      <Box component="span"
                        onClick={(e) => { e.stopPropagation(); setSelectedSuggestions(prev => prev.filter(x => x !== s)); }}
                        sx={{ cursor: "pointer", fontSize: TYPE.body.fontSize, lineHeight: 1, ml: 0.5, "&:active": { opacity: 0.5 } }}>
                        ×
                      </Box>
                    </Box>
                  ))}
                </Box>
              )}
              <VoiceInput
                onResult={(text) => { setInput(prev => prev ? prev + text : text); }}
                onCancel={() => setVoiceMode(false)}
              />
            </Box>
          ) : (
            <Box sx={{ flex: 1, bgcolor: COLOR.white, borderRadius: RADIUS.md, border: `1px solid ${COLOR.border}`,
              px: 1, py: 0.5, display: "flex", flexWrap: "wrap", alignItems: "center", gap: 0.5, minHeight: 36 }}>
              {selectedSuggestions.map((s, i) => (
                <Box key={i} sx={{
                  display: "inline-flex", alignItems: "center", gap: 0.5,
                  px: 1, py: 0.5, borderRadius: RADIUS.lg, fontSize: TYPE.secondary.fontSize,
                  bgcolor: COLOR.successLight, color: COLOR.primary, fontWeight: 500,
                  flexShrink: 0,
                }}>
                  {s}
                  <Box component="span"
                    onClick={(e) => { e.stopPropagation(); setSelectedSuggestions(prev => prev.filter(x => x !== s)); }}
                    sx={{ cursor: "pointer", fontSize: TYPE.body.fontSize, lineHeight: 1, ml: 0.5, "&:active": { opacity: 0.5 } }}>
                    ×
                  </Box>
                </Box>
              ))}
              <Box component="input" value={input}
                onChange={e => setInput(e.target.value)}
                placeholder={selectedSuggestions.length > 0 ? "" : "请输入…"}
                sx={{ flex: 1, minWidth: 60, border: "none", outline: "none",
                  fontSize: TYPE.body.fontSize, fontFamily: "inherit", bgcolor: "transparent", p: 0.5 }}
              />
            </Box>
          )}
          <IconButton type="submit" disabled={(!input.trim() && selectedSuggestions.length === 0) || sending}
            sx={{ color: COLOR.primary, flexShrink: 0, alignSelf: "center" }}>
            <SendIcon />
          </IconButton>
        </Box>
      )}
      {status === "confirmed" && (
        <Box sx={{ px: 2, py: 2, bgcolor: COLOR.surface, textAlign: "center", flexShrink: 0 }}>
          <Button variant="contained" onClick={onBack} sx={{ bgcolor: COLOR.primary, "&:hover": { bgcolor: COLOR.primaryHover } }}>返回病历</Button>
        </Box>
      )}

      {/* Summary dialog */}
      <SheetDialog
        open={showSummary}
        onClose={handleResumeInput}
        title="已收集信息"
        desktopMaxWidth={400}
        footer={
          <Box sx={{ display: "grid", gap: 0.5, gridTemplateColumns: status === "reviewing" ? "repeat(2, minmax(0, 1fr))" : "1fr" }}>
            <AppButton variant="secondary" size="md" fullWidth onClick={handleResumeInput}>
              继续补充
            </AppButton>
            {status === "reviewing" && (
              <AppButton
                variant="primary"
                size="md"
                fullWidth
                disabled={confirming}
                loading={confirming}
                loadingLabel="提交中…"
                onClick={handleConfirm}
              >
                确认提交
              </AppButton>
            )}
          </Box>
        }
      >
          <Stack spacing={1.5}>
            {allFields.map(f => {
              const val = collected[f];
              return (
                <Box key={f}>
                  <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
                    {val
                      ? <CheckCircleOutlineIcon sx={{ fontSize: 14, color: COLOR.primary }} />
                      : <RadioButtonUncheckedIcon sx={{ fontSize: 14, color: COLOR.border }} />
                    }
                    <Typography variant="caption" color="text.secondary">{FIELD_LABELS[f]}</Typography>
                  </Box>
                  {val && <Typography variant="body2" sx={{ ml: 3 }}>{val}</Typography>}
                </Box>
              );
            })}
          </Stack>
      </SheetDialog>

      {/* Exit dialog */}
      <ConfirmDialog
        open={showExitDialog}
        onClose={() => setShowExitDialog(false)}
        onCancel={() => handleExit(false)}
        onConfirm={() => handleExit(true)}
        title="退出问诊"
        message="您要保存进度还是重新开始？"
        cancelLabel="保存退出"
        confirmLabel="放弃重来"
        confirmTone="danger"
      />

      <ConfirmDialog
        open={showErrorDialog}
        onClose={() => setShowErrorDialog(false)}
        onConfirm={() => setShowErrorDialog(false)}
        title="提交失败"
        message="请稍后重试。"
        confirmLabel="确定"
      />
    </Box>
  );
}
