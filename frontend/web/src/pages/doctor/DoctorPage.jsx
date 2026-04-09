/**
 * @route /doctor/*
 *
 * 鲸鱼随行主页：composer-first workbench with one visible working context.
 *
 * Default route is the AI chat composer.
 * Admin/management surfaces are reachable but secondary.
 */
import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import {
  Badge, Box, Chip, CircularProgress, Fade, IconButton, LinearProgress, Slide, Stack, TextField, Typography,
} from "@mui/material";
import BottomNavigationMui from "@mui/material/BottomNavigation";
import BottomNavigationActionMui from "@mui/material/BottomNavigationAction";
import LogoutIcon from "@mui/icons-material/Logout";
import SendOutlinedIcon from "@mui/icons-material/SendOutlined";
import MicNoneOutlinedIcon from "@mui/icons-material/MicNoneOutlined";
import KeyboardOutlinedIcon from "@mui/icons-material/KeyboardOutlined";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import useMediaQuery from "@mui/material/useMediaQuery";
import { useTheme } from "@mui/material/styles";
import { useApi } from "../../api/ApiContext";
import { useAppNavigate } from "../../hooks/useAppNavigate";
import { useDoctorStore } from "../../store/doctorStore";
import {
  NAV,
  DESKTOP_NAV,
  getOnboardingState,
  markOnboardingStep,
  ONBOARDING_STEP,
} from "./constants";
import { isWizardDone } from "./onboardingWizardState";
import MyAIPage from "./MyAIPage";
import PatientsPage from "./PatientsPage";
import SettingsPage from "./SettingsPage";
import ReviewPage from "./ReviewPage";
import ReviewQueuePage from "./ReviewQueuePage";
import TaskPage from "./TaskPage";
import ErrorBoundary from "../../components/ErrorBoundary";
import ConfirmDialog from "../../components/ConfirmDialog";
import SheetDialog from "../../components/SheetDialog";
import AppButton from "../../components/AppButton";
import DialogFooter from "../../components/DialogFooter";
import SubpageHeader from "../../components/SubpageHeader";
import BarButton from "../../components/BarButton";
import SuggestionChips from "../../components/SuggestionChips";
import VoiceInput, { isVoiceSupported } from "../../components/VoiceInput";
import { TYPE, ICON, COLOR, RADIUS } from "../../theme";
import { dp } from "../../utils/doctorBasePath";
import { usePendingTasks, useDraftSummary, useReviewQueue, useDrafts } from "../../lib/doctorQueries";

function DesktopSidebar({ activeSection, doctorName, doctorId, navBadge, onNav, onLogout }) {
  return (
    <Box sx={{ width: 220, flexShrink: 0, borderRight: `0.5px solid ${COLOR.border}`, backgroundColor: COLOR.surface, display: "flex", flexDirection: "column", py: 2, px: 0 }}>
      <Box sx={{ mb: 2, px: 2 }}>
        <Typography variant="subtitle1" sx={{ fontWeight: 800, color: COLOR.primary }}>鲸鱼随行</Typography>
        <Typography variant="caption" color="text.secondary">{doctorName || doctorId}</Typography>
      </Box>
      <Box component="nav" aria-label="主导航" sx={{ flex: 1 }}>
        {DESKTOP_NAV.map((item) => (
          <Box key={item.key} component="button" type="button" onClick={() => onNav(item.key)}
            aria-current={activeSection === item.key ? "page" : undefined}
            sx={{ display: "flex", alignItems: "center", gap: 1, px: 2, py: 1, cursor: "pointer", width: "100%", border: "none", textAlign: "left",
              bgcolor: activeSection === item.key ? COLOR.primary : "transparent",
              color: activeSection === item.key ? COLOR.white : COLOR.text4,
              "&:hover": { bgcolor: activeSection === item.key ? COLOR.primary : COLOR.borderLight },
              "&:focus-visible": { outline: `2px solid ${COLOR.primary}`, outlineOffset: -2 },
              "&:active": { opacity: 0.8 } }}>
            <Box sx={{ "& svg": { fontSize: ICON.lg, color: activeSection === item.key ? COLOR.white : COLOR.text4 } }}>
              {item.badgeKey && navBadge[item.badgeKey] > 0 ? <Badge badgeContent={navBadge[item.badgeKey]} color="error">{item.icon}</Badge> : item.icon}
            </Box>
            <Typography sx={{ fontSize: TYPE.heading.fontSize, fontWeight: activeSection === item.key ? 600 : 400, color: "inherit" }}>{item.label}</Typography>
          </Box>
        ))}
      </Box>
      <Box component="button" type="button" onClick={onLogout} sx={{ display: "flex", alignItems: "center", gap: 1, px: 2, py: 1, cursor: "pointer", width: "100%", border: "none", textAlign: "left", bgcolor: "transparent", color: COLOR.text4, "&:hover": { bgcolor: COLOR.borderLight }, "&:focus-visible": { outline: `2px solid ${COLOR.primary}`, outlineOffset: -2 }, "&:active": { opacity: 0.8 } }}>
        <LogoutIcon fontSize="small" sx={{ color: COLOR.text4 }} />
        <Typography sx={{ fontSize: TYPE.body.fontSize, color: COLOR.text4 }}>退出登录</Typography>
      </Box>
    </Box>
  );
}

function MobileBottomNav({ activeSection, navBadge, onNav }) {
  const navValue = activeSection;
  return (
    <Box sx={{ flexShrink: 0, borderTop: `0.5px solid ${COLOR.border}`, bgcolor: COLOR.surface, pb: "8px" }}>
      <BottomNavigationMui value={navValue} onChange={(_, val) => onNav(val)}
        sx={{ height: 64, bgcolor: COLOR.surface, "& .MuiBottomNavigationAction-root": { minWidth: 56, paddingTop: "8px", color: COLOR.text4 }, "& .Mui-selected": { color: COLOR.primary }, "& .Mui-selected .MuiBottomNavigationAction-label": { color: COLOR.primary, fontWeight: 600 } }}>
        {NAV.map((item) => {
          const badgeCount = item.badgeKey ? (navBadge[item.badgeKey] || 0) : 0;
          return (
            <BottomNavigationActionMui key={item.key} label={item.label} value={item.key} showLabel
              icon={badgeCount > 0 ? <Badge badgeContent={badgeCount} color="error">{item.icon}</Badge> : item.icon}
              sx={{ minWidth: 0, "& .MuiBottomNavigationAction-label": { fontSize: TYPE.micro.fontSize } }} />
          );
        })}
      </BottomNavigationMui>
    </Box>
  );
}

function OnboardingDialog({ open, name, saving, onChange, onSubmit, onClose }) {
  return (
    <SheetDialog
      open={open}
      onClose={onClose}
      title="欢迎，请完成初始设置"
      desktopMaxWidth={360}
      footer={<DialogFooter onCancel={onClose} onConfirm={onSubmit} confirmLabel="完成设置" confirmDisabled={!name.trim() || saving} confirmLoading={saving} confirmLoadingLabel="保存中..." />}
    >
        <Stack spacing={2} sx={{ mt: 1 }}>
          <TextField label="您的姓名" value={name} onChange={(e) => onChange(e.target.value)} fullWidth autoFocus required />
        </Stack>
    </SheetDialog>
  );
}

const PREVIEW_FIELD_LABELS = {
  chief_complaint: "主诉",
  present_illness: "现病史",
  past_history: "既往史",
  allergy_history: "过敏史",
  family_history: "家族史",
  personal_history: "个人史",
  marital_reproductive: "婚育史",
};

const PREVIEW_ALL_FIELDS = Object.keys(PREVIEW_FIELD_LABELS);

function parsePreviewSession(previewId, doctorId) {
  const params = new URLSearchParams(window.location.search);
  const queryToken = params.get("patient_token") || "";
  const queryName = params.get("patient_name") || "";
  const onboarding = getOnboardingState(doctorId);
  const samePatient = String(onboarding.lastPreviewPatientId || "") === String(previewId || "");
  return {
    token: queryToken || (samePatient ? onboarding.lastPreviewToken || "" : ""),
    patientName: queryName || (samePatient ? onboarding.lastPreviewPatientName || "" : ""),
  };
}

function PreviewIntroCard({ patientName }) {
  return (
    <Box
      sx={{
        mx: 2,
        mt: 1.5,
        p: 1.5,
        bgcolor: COLOR.white,
        borderTop: `0.5px solid ${COLOR.border}`,
        borderBottom: `0.5px solid ${COLOR.border}`,
      }}
    >
      <Box sx={{ display: "flex", alignItems: "flex-start", gap: 1 }}>
        <InfoOutlinedIcon sx={{ fontSize: 18, color: COLOR.primary, mt: 0.5 }} />
        <Box sx={{ flex: 1 }}>
          <Typography sx={{ fontSize: TYPE.heading.fontSize, fontWeight: 600, color: COLOR.text1 }}>
            患者端预览
          </Typography>
          <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text3, mt: 0.5, lineHeight: 1.6 }}>
            {patientName || "患者"} 将看到一个 2 分钟左右的 AI 预问诊流程：
            描述症状，接受追问，确认后提交给医生审核。
          </Typography>
        </Box>
      </Box>
    </Box>
  );
}

function PreviewMessageBubble({ role, content }) {
  const isUser = role === "user";
  return (
    <Box sx={{ display: "flex", justifyContent: isUser ? "flex-end" : "flex-start", mb: 1.5 }}>
      <Box
        sx={{
          maxWidth: "82%",
          px: 2,
          py: 1.5,
          borderRadius: 2,
          bgcolor: isUser ? COLOR.wechatGreen : COLOR.white,
          color: COLOR.text2,
          fontSize: TYPE.body.fontSize,
          lineHeight: 1.6,
          whiteSpace: "pre-wrap",
          wordBreak: "break-word",
        }}
      >
        {content}
      </Box>
    </Box>
  );
}

function PreviewSummarySheet({ open, onClose, collected, progress, onConfirm, confirming, onResumeInput }) {
  return (
    <SheetDialog
      open={open}
      onClose={onResumeInput || onClose}
      title="确认预问诊信息"
      desktopMaxWidth={400}
      footer={(
        <DialogFooter
          onCancel={onResumeInput || onClose}
          cancelLabel="继续补充"
          onConfirm={onConfirm}
          confirmLabel="提交"
          confirmDisabled={confirming}
          confirmLoading={confirming}
          confirmLoadingLabel="提交中…"
        />
      )}
    >
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 1.5 }}>
        <Chip
          size="small"
          label={`${progress.filled}/${progress.total}`}
          sx={{ bgcolor: COLOR.primaryLight, color: COLOR.primary, fontWeight: 600 }}
        />
        <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4 }}>
          提交后会自动创建审核任务
        </Typography>
      </Box>
      {PREVIEW_ALL_FIELDS.map((field) => (
        <Box
          key={field}
          sx={{
            py: 1,
            borderBottom: `0.5px solid ${COLOR.borderLight}`,
            "&:last-child": { borderBottom: "none" },
          }}
        >
          <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4, mb: 0.5 }}>
            {PREVIEW_FIELD_LABELS[field]}
          </Typography>
          <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text2, lineHeight: 1.6 }}>
            {collected[field] || "未填写"}
          </Typography>
        </Box>
      ))}
    </SheetDialog>
  );
}

function PreviewSuccessCard({ patientName, reviewTaskId, onViewReview, onViewTasks, openingReview }) {
  return (
    <Box
      sx={{
        mx: 2,
        mt: 1.5,
        p: 1.5,
        bgcolor: COLOR.white,
        borderTop: `0.5px solid ${COLOR.border}`,
        borderBottom: `0.5px solid ${COLOR.border}`,
      }}
    >
      <Typography sx={{ fontSize: TYPE.heading.fontSize, fontWeight: 600, color: COLOR.text1 }}>
        已提交给医生
      </Typography>
      <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text3, mt: 0.5, lineHeight: 1.6 }}>
        {patientName || "患者"} 的预问诊信息已经提交，系统已创建审核任务 #{reviewTaskId || "—"}。
      </Typography>
      <Box sx={{ display: "grid", gap: 1, gridTemplateColumns: "repeat(2, minmax(0, 1fr))", mt: 1.5 }}>
        <AppButton variant="secondary" size="md" fullWidth onClick={onViewTasks}>
          查看任务
        </AppButton>
        <AppButton
          variant="primary"
          size="md"
          fullWidth
          disabled={openingReview}
          loading={openingReview}
          loadingLabel="打开中…"
          onClick={onViewReview}
        >
          去审核
        </AppButton>
      </Box>
    </Box>
  );
}

function PatientPreviewPage({ doctorId, previewId }) {
  const navigate = useAppNavigate();
  const { interviewStart, interviewTurn, interviewConfirm, interviewCancel, triggerDiagnosis } = useApi();
  const sessionConfig = parsePreviewSession(previewId, doctorId);
  const patientName = sessionConfig.patientName || "患者";
  const token = sessionConfig.token;
  const voiceSupported = isVoiceSupported();
  const chatEndRef = useRef(null);

  const [sessionId, setSessionId] = useState("");
  const [messages, setMessages] = useState([]);
  const [collected, setCollected] = useState({});
  const [progress, setProgress] = useState({ filled: 0, total: 7 });
  const [status, setStatus] = useState("interviewing");
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [showSummary, setShowSummary] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [suggestions, setSuggestions] = useState([]);
  const [selectedSuggestions, setSelectedSuggestions] = useState([]);
  const [voiceMode, setVoiceMode] = useState(false);
  const [showExitDialog, setShowExitDialog] = useState(false);
  const [error, setError] = useState("");
  const [submitted, setSubmitted] = useState(null);
  const [openingReview, setOpeningReview] = useState(false);
  const [reviewReady, setReviewReady] = useState(false);
  const [reviewHintShown, setReviewHintShown] = useState(false);
  const canSupplement = reviewReady && !submitted;
  const canInput = !submitted && (status === "interviewing" || canSupplement);

  useEffect(() => {
    if (!token) {
      setError("缺少患者预览凭证，请重新生成预问诊入口。");
      return undefined;
    }
    let cancelled = false;
    (async () => {
      try {
        const data = await interviewStart(token);
        if (cancelled) return;
        setSessionId(data.session_id);
        setCollected(data.collected || {});
        setProgress(data.progress || { filled: 0, total: 7 });
        setStatus(data.status || "interviewing");
        setMessages([{ role: "assistant", content: data.reply }]);
        if (data.ready_to_review || data.status === "reviewing") {
          setReviewReady(true);
          if (!reviewHintShown) {
            setReviewHintShown(true);
            setTimeout(() => setShowSummary(true), 300);
          }
        }
      } catch (err) {
        if (cancelled) return;
        setError(err?.message || "无法启动患者预问诊。");
      }
    })();
    return () => { cancelled = true; };
  }, [token, interviewStart]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, sending]);

  function handleToggleSuggestion(text) {
    setSelectedSuggestions((prev) => (
      prev.includes(text) ? prev.filter((item) => item !== text) : [...prev, text]
    ));
  }

  async function handleSend() {
    const parts = [...selectedSuggestions];
    if (input.trim()) parts.push(input.trim());
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
      setProgress(data.progress || { filled: 0, total: 7 });
      setStatus(data.status || "interviewing");
      setSuggestions(data.suggestions || []);
      if (data.ready_to_review || data.status === "reviewing") {
        setReviewReady(true);
        if (!reviewHintShown) {
          setReviewHintShown(true);
          setTimeout(() => setShowSummary(true), 500);
        }
      }
    } catch (err) {
      setMessages((prev) => [...prev, { role: "assistant", content: err?.message || "系统繁忙，请稍后重试。" }]);
    } finally {
      setSending(false);
    }
  }

  async function handleConfirm() {
    if (!sessionId) return;
    setConfirming(true);
    try {
      const data = await interviewConfirm(token, sessionId);
      setStatus("confirmed");
      setShowSummary(false);
      setSubmitted(data);
      setMessages((prev) => [...prev, { role: "assistant", content: data.message }]);
      markOnboardingStep(doctorId, ONBOARDING_STEP.patientPreview, {
        lastPreviewPatientId: Number(previewId),
        lastPreviewPatientName: patientName,
        lastPreviewToken: token,
        lastReviewRecordId: data.record_id,
        lastReviewTaskId: data.review_id,
      });
      markOnboardingStep(doctorId, ONBOARDING_STEP.reviewTask, {
        lastReviewRecordId: data.record_id,
        lastReviewTaskId: data.review_id,
      });
    } catch (err) {
      setError(err?.message || "提交失败，请稍后重试。");
    } finally {
      setConfirming(false);
    }
  }

  async function handleExit(abandon) {
    setShowExitDialog(false);
    if (abandon && sessionId) {
      try { await interviewCancel(token, sessionId); } catch {}
    }
    navigate(-1);
  }

  async function handleViewReview() {
    if (!submitted?.record_id) return;
    setOpeningReview(true);
    try {
      await triggerDiagnosis(submitted.record_id, doctorId);
    } catch {
      // Keep navigation deterministic even if the background trigger fails.
    }
    navigate(`${dp("review")}/${submitted.record_id}?source=patient_preview&review_task_id=${submitted.review_id || ""}`);
  }

  function handleViewTasks() {
    if (!submitted?.review_id) return;
    navigate(`${dp("tasks")}?tab=followups&highlight_task_ids=${submitted.review_id}&origin=patient_submit`);
  }

  function handleResumeInput() {
    setShowSummary(false);
    setStatus("interviewing");
  }

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%", bgcolor: COLOR.surfaceAlt }}>
      {/*
        Top-bar action follows UI-DESIGN.md: single text-only BarButton, max 2 Chinese chars.
        Progress is shown as a disabled bar action until the interview is ready to submit.
      */}
      <SubpageHeader
        title="患者端预览"
        onBack={() => (status === "confirmed" ? navigate(-1) : setShowExitDialog(true))}
        right={
          submitted ? null : (
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

      <Box sx={{ px: 2, py: 1, bgcolor: COLOR.white, borderBottom: `0.5px solid ${COLOR.borderLight}` }}>
        <LinearProgress
          variant="determinate"
          value={progress.total ? (progress.filled / progress.total) * 100 : 0}
          sx={{
            height: 6,
            borderRadius: 3,
            bgcolor: COLOR.border,
            "& .MuiLinearProgress-bar": { bgcolor: COLOR.primary, borderRadius: 3 },
          }}
        />
        <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4, mt: 0.5 }}>
          {submitted ? "预问诊已提交" : `患者侧流程进度 ${progress.filled}/${progress.total}`}
        </Typography>
      </Box>

      <Box sx={{ flex: 1, overflowY: "auto", pb: 2 }}>
        <PreviewIntroCard patientName={patientName} />

        {error ? (
          <Box sx={{ mx: 2, mt: 1.5, p: 1.5, bgcolor: COLOR.white, borderTop: `0.5px solid ${COLOR.border}`, borderBottom: `0.5px solid ${COLOR.border}` }}>
            <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.danger }}>
              {error}
            </Typography>
          </Box>
        ) : (
          <Box sx={{ px: 2, py: 2 }}>
            {messages.map((msg, index) => (
              <PreviewMessageBubble key={`${msg.role}-${index}`} role={msg.role} content={msg.content} />
            ))}
            {sending && (
              <Box sx={{ display: "flex", justifyContent: "flex-start", mb: 1.5 }}>
                <Box sx={{ px: 2, py: 1.5, borderRadius: 2, bgcolor: COLOR.white }}>
                  <CircularProgress size={16} />
                </Box>
              </Box>
            )}
            {submitted && (
              <PreviewSuccessCard
                patientName={patientName}
                reviewTaskId={submitted.review_id}
                onViewReview={handleViewReview}
                onViewTasks={handleViewTasks}
                openingReview={openingReview}
              />
            )}
            <div ref={chatEndRef} />
          </Box>
        )}
      </Box>

      {canInput && suggestions.length > 0 && (
        <SuggestionChips
          items={suggestions}
          selected={selectedSuggestions}
          onToggle={handleToggleSuggestion}
          onDismiss={() => setSuggestions([])}
          disabled={sending}
        />
      )}

      {canInput && (
        <Box
          sx={{
            display: "flex",
            alignItems: "flex-end",
            gap: 1,
            px: 2,
            py: 1,
            bgcolor: COLOR.surface,
            borderTop: suggestions.length > 0 ? "none" : `0.5px solid ${COLOR.border}`,
            flexShrink: 0,
          }}
        >
          {voiceSupported && (
            <IconButton
              onClick={() => setVoiceMode((value) => !value)}
              sx={{ color: COLOR.text3, flexShrink: 0, alignSelf: "center" }}
            >
              {voiceMode ? <KeyboardOutlinedIcon /> : <MicNoneOutlinedIcon />}
            </IconButton>
          )}
          {voiceMode ? (
            <Box sx={{ flex: 1 }}>
              <VoiceInput
                onResult={(text) => {
                  setInput((prev) => (prev ? `${prev} ${text}` : text));
                }}
                onCancel={() => setVoiceMode(false)}
              />
            </Box>
          ) : (
            <Box
              sx={{
                flex: 1,
                bgcolor: COLOR.white,
                borderRadius: RADIUS.md,
                border: `1px solid ${COLOR.border}`,
                px: 1,
                py: 0.5,
                display: "flex",
                flexWrap: "wrap",
                alignItems: "center",
                gap: 0.5,
                minHeight: 36,
              }}
            >
              {selectedSuggestions.map((item) => (
                <Box
                  key={item}
                  sx={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: 0.5,
                    px: 1,
                    py: 0.5,
                    borderRadius: RADIUS.lg,
                    fontSize: TYPE.secondary.fontSize,
                    bgcolor: COLOR.primaryLight,
                    color: COLOR.primary,
                    fontWeight: 500,
                  }}
                >
                  {item}
                  <Box
                    component="span"
                    onClick={() => setSelectedSuggestions((prev) => prev.filter((value) => value !== item))}
                    sx={{ cursor: "pointer", fontSize: TYPE.body.fontSize, lineHeight: 1, "&:active": { opacity: 0.5 } }}
                  >
                    ×
                  </Box>
                </Box>
              ))}
              <Box
                component="input"
                value={input}
                onChange={(event) => setInput(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    handleSend();
                  }
                }}
                placeholder={selectedSuggestions.length > 0 ? "" : "请输入患者描述…"}
                sx={{
                  flex: 1,
                  minWidth: 60,
                  border: "none",
                  outline: "none",
                  fontSize: TYPE.body.fontSize,
                  fontFamily: "inherit",
                  bgcolor: "transparent",
                  p: 0.5,
                }}
              />
            </Box>
          )}
          <IconButton
            onClick={handleSend}
            disabled={sending || (!input.trim() && selectedSuggestions.length === 0)}
            sx={{ color: COLOR.primary, flexShrink: 0, alignSelf: "center" }}
          >
            <SendOutlinedIcon />
          </IconButton>
        </Box>
      )}

      <PreviewSummarySheet
        open={showSummary}
        onClose={handleResumeInput}
        collected={collected}
        progress={progress}
        onConfirm={handleConfirm}
        confirming={confirming}
        onResumeInput={handleResumeInput}
      />

      <ConfirmDialog
        open={showExitDialog}
        onClose={() => setShowExitDialog(false)}
        onCancel={() => handleExit(false)}
        onConfirm={() => handleExit(true)}
        title="退出预览"
        message="要保留当前预问诊进度，还是放弃本次预览？"
        cancelLabel="保存退出"
        confirmLabel="放弃重来"
        confirmTone="danger"
      />
    </Box>
  );
}

function SectionContent({ activeSection, doctorId, isMobile, navigate, urlSubpage, urlSubId, patientRefreshKey, setPatientRefreshKey, handleLogout, triggerInterview, setTriggerInterview, chatInterviewSessionId, setChatInterviewSessionId, chatInterviewPrePopulated, setChatInterviewPrePopulated }) {
  return (
    <Box sx={{ flex: 1, overflow: "hidden", position: "relative" }}>
      <Fade in={activeSection === "my-ai"} timeout={150} unmountOnExit>
        <Box sx={{ position: "absolute", inset: 0 }}>
          <ErrorBoundary label="我的AI">
            <MyAIPage doctorId={doctorId} />
          </ErrorBoundary>
        </Box>
      </Fade>
      <Fade in={activeSection === "patients"} timeout={150} unmountOnExit>
        <Box sx={{ position: "absolute", inset: 0 }}>
          <ErrorBoundary label="患者">
            <PatientsPage doctorId={doctorId}
              refreshKey={patientRefreshKey}
              triggerInterview={triggerInterview}
              onTriggerInterviewConsumed={() => setTriggerInterview(false)}
              chatInterviewSessionId={chatInterviewSessionId}
              onChatInterviewSessionConsumed={() => { setChatInterviewSessionId(null); setChatInterviewPrePopulated(null); }}
              chatInterviewPrePopulated={chatInterviewPrePopulated} />
          </ErrorBoundary>
        </Box>
      </Fade>
      <Fade in={activeSection === "review"} timeout={150} unmountOnExit><Box sx={{ position: "absolute", inset: 0 }}><ErrorBoundary label="门诊"><ReviewQueuePage doctorId={doctorId} urlSubpage={urlSubpage} /></ErrorBoundary></Box></Fade>
      <Fade in={activeSection === "tasks"} timeout={150} unmountOnExit><Box sx={{ position: "absolute", inset: 0 }}><ErrorBoundary label="任务"><TaskPage doctorId={doctorId} urlSubpage={urlSubpage} /></ErrorBoundary></Box></Fade>
      <Fade in={activeSection === "settings"} timeout={150} unmountOnExit><Box sx={{ position: "absolute", inset: 0 }}><ErrorBoundary label="设置"><SettingsPage doctorId={doctorId} onLogout={handleLogout} urlSubpage={urlSubpage} urlSubId={urlSubId} /></ErrorBoundary></Box></Fade>
      <Fade in={activeSection === "preview"} timeout={150} unmountOnExit><Box sx={{ position: "absolute", inset: 0 }}><ErrorBoundary label="患者端预览"><PatientPreviewPage doctorId={doctorId} previewId={urlSubpage} /></ErrorBoundary></Box></Fade>
    </Box>
  );
}

function useDoctorPageState({ doctorId, accessToken, setAuth }) {
  const { getDoctorProfile, updateDoctorProfile } = useApi();
  const [showOnboarding, setShowOnboarding] = useState(false);
  const [onboardName, setOnboardName] = useState("");
  const [onboardSaving, setOnboardSaving] = useState(false);

  // Badge counts via React Query (cache-backed, no redundant fetches on tab switch)
  const { data: tasksData } = usePendingTasks();
  const { data: reviewQueueData } = useReviewQueue();
  const { data: draftsData } = useDrafts();

  const pendingTaskCount = (() => {
    if (!tasksData) return 0;
    const items = Array.isArray(tasksData) ? tasksData : (tasksData.items || []);
    return items.length;
  })();

  // Review badge = pending review records + pending reply drafts (from cached queries, no extra DB call)
  const pendingReviewRecords = reviewQueueData?.pending?.length ?? 0;
  const pendingDrafts = (draftsData || []).filter(d => d.status !== "sent").length;
  const reviewCount = pendingReviewRecords + pendingDrafts;

  const followupCount = 0;

  useEffect(() => {
    if (!doctorId) return;
    const setupDoneKey = `onboarding_setup_done:${doctorId}`;
    if (localStorage.getItem(setupDoneKey)) return;
    getDoctorProfile(doctorId).then((p) => { if (!p.onboarded) { setOnboardName(p.name || ""); setShowOnboarding(true); } }).catch(() => {});
  }, [doctorId]); // eslint-disable-line react-hooks/exhaustive-deps

  async function handleOnboardSubmit() {
    if (!onboardName.trim() || onboardSaving) return;
    setOnboardSaving(true);
    try { await updateDoctorProfile(doctorId, { name: onboardName.trim() }); setAuth(doctorId, onboardName.trim(), accessToken); localStorage.setItem(`onboarding_setup_done:${doctorId}`, "1"); setShowOnboarding(false); }
    catch { localStorage.setItem(`onboarding_setup_done:${doctorId}`, "1"); setShowOnboarding(false); } finally { setOnboardSaving(false); }
  }
  return { pendingTaskCount, reviewCount, followupCount, showOnboarding, onboardName, setOnboardName, onboardSaving, handleOnboardSubmit };
}

export default function DoctorPage() {
  const { section, patientId, recordId, subpage: urlSubpage, subId: urlSubId } = useParams();
  const navigate = useAppNavigate();
  const { doctorId, doctorName, accessToken, clearAuth, setAuth } = useDoctorStore();
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down("sm"));
  const [patientRefreshKey, setPatientRefreshKey] = useState(0);
  const [triggerInterview, setTriggerInterview] = useState(false);
  const [chatInterviewSessionId, setChatInterviewSessionId] = useState(null);
  const [chatInterviewPrePopulated, setChatInterviewPrePopulated] = useState(null);

  const { pendingTaskCount, reviewCount, followupCount, showOnboarding, onboardName, setOnboardName, onboardSaving, handleOnboardSubmit } = useDoctorPageState({ doctorId, accessToken, setAuth });

  // Redirect to onboarding wizard on first login (skip for /mock and wizard subpages)
  useEffect(() => {
    if (!doctorId) return;
    if (window.location.pathname.startsWith("/mock")) return;
    const params = new URLSearchParams(window.location.search);
    if (params.get("wizard") === "1" || params.get("onboarding") === "1") return;
    if (!isWizardDone(doctorId)) {
      navigate(dp("onboarding"));
    }
  }, [doctorId]); // eslint-disable-line react-hooks/exhaustive-deps

  const navBadge = { tasks: pendingTaskCount, review: reviewCount };

  const isReviewPage = !!recordId;
  const activeSection = patientId ? "patients" : (section || "my-ai");

  // Main tabs show bottom nav; subpages hide it and show ‹ back in top bar.
  // WeChat pattern: bottom nav only on root tab views.
  const MAIN_TABS = new Set(["my-ai", "patients", "review", "tasks"]);
  const isSubpage = isReviewPage || !MAIN_TABS.has(activeSection) || !!patientId;

  function handleNav(key) { navigate(key === "my-ai" ? dp() : dp(key)); }
  function handleLogout() {
    clearAuth();
    if (window.__wxjs_environment === "miniprogram") wx.miniProgram?.postMessage?.({ data: { action: "logout" } }); // eslint-disable-line no-undef
    navigate("/login", { replace: true });
  }

  return (
    <Box sx={{ display: "flex", flexDirection: isMobile ? "column" : "row", height: "100%", position: "relative", bgcolor: COLOR.surface }}>
      {!isMobile && <DesktopSidebar activeSection={activeSection} doctorName={doctorName} doctorId={doctorId} navBadge={navBadge} onNav={handleNav} onLogout={handleLogout} />}
      <Box sx={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden", position: "relative" }}>
        <SectionContent activeSection={activeSection} doctorId={doctorId} isMobile={isMobile} navigate={navigate} urlSubpage={urlSubpage} urlSubId={urlSubId} patientRefreshKey={patientRefreshKey} setPatientRefreshKey={setPatientRefreshKey} handleLogout={handleLogout} triggerInterview={triggerInterview} setTriggerInterview={setTriggerInterview} chatInterviewSessionId={chatInterviewSessionId} setChatInterviewSessionId={setChatInterviewSessionId} chatInterviewPrePopulated={chatInterviewPrePopulated} setChatInterviewPrePopulated={setChatInterviewPrePopulated} />
        <Slide direction="left" in={isReviewPage} timeout={300} mountOnEnter unmountOnExit>
          <Box sx={{ position: "absolute", inset: 0, zIndex: 5, bgcolor: COLOR.surfaceAlt }}>
            <ErrorBoundary label="诊断审核">
              <ReviewPage recordId={recordId} />
            </ErrorBoundary>
          </Box>
        </Slide>
      </Box>
      {isMobile && !isSubpage && <MobileBottomNav activeSection={activeSection} navBadge={navBadge} onNav={handleNav} />}
      <OnboardingDialog open={showOnboarding} name={onboardName} saving={onboardSaving} onChange={setOnboardName} onSubmit={handleOnboardSubmit} onClose={() => setShowOnboarding(false)} />
    </Box>
  );
}
