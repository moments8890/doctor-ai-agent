// frontend/web/src/pages/doctor/OnboardingWizard.jsx
import { useState, useEffect, useCallback } from "react";
import { useSearchParams } from "react-router-dom";
import { Box, Typography, LinearProgress } from "@mui/material";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";
import { useAppNavigate } from "../../hooks/useAppNavigate";
import { useApi } from "../../api/ApiContext";
import { useDoctorStore } from "../../store/doctorStore";
import SubpageHeader from "../../components/SubpageHeader";
import AppButton from "../../components/AppButton";
import SheetDialog from "../../components/SheetDialog";
import PatientInterviewPage from "../patient/InterviewPage";
import { PatientApiProvider } from "../../api/PatientApiContext";
import ListCard from "../../components/ListCard";
import IconBadge from "../../components/IconBadge";
import ConfirmDialog from "../../components/ConfirmDialog";
import MsgAvatar from "../../components/MsgAvatar";
import NameAvatar from "../../components/NameAvatar";
import { TYPE, COLOR, RADIUS } from "../../theme";
import { dp } from "../../utils/doctorBasePath";
import { ICON_BADGES } from "./constants";
import {
  getWizardProgress,
  setWizardProgress,
  markWizardDone,
  clearWizardProgress,
} from "./onboardingWizardState";

const TOTAL_STEPS = 3;

const STEP_TITLES = {
  1: "添加一条规则",
  2: "看AI怎么用它",
  3: "确认并开始",
};

function ProgressBar({ step }) {
  return (
    <Box sx={{ px: 2, py: 1, bgcolor: COLOR.white, borderBottom: `0.5px solid ${COLOR.border}` }}>
      <Box sx={{ display: "flex", justifyContent: "space-between", mb: 0.5 }}>
        <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4 }}>
          步骤 {step}/{TOTAL_STEPS}
        </Typography>
        <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4 }}>
          {STEP_TITLES[step]}
        </Typography>
      </Box>
      <LinearProgress
        variant="determinate"
        value={(step / TOTAL_STEPS) * 100}
        sx={{
          height: 4,
          borderRadius: 2,
          bgcolor: COLOR.primaryLight,
          "& .MuiLinearProgress-bar": { bgcolor: COLOR.primary, borderRadius: 2 },
        }}
      />
    </Box>
  );
}

/**
 * SpotlightHint — green dashed border around "click here next" target.
 */
function SpotlightHint({ active, children }) {
  if (!active) return children;
  return (
    <Box sx={{ outline: `2px dashed ${COLOR.primary}`, outlineOffset: -2, borderRadius: RADIUS.sm }}>
      {children}
    </Box>
  );
}

function ContextCard({ children }) {
  return (
    <Box sx={{ mx: 2, mt: 2, p: 2, bgcolor: COLOR.primaryLight, border: `1px solid ${COLOR.primary}30`, borderRadius: RADIUS.lg }}>
      <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text2, lineHeight: 1.7 }}>
        {children}
      </Typography>
    </Box>
  );
}

function WizardFooter({ canAdvance, onAdvance, onSkip, onRestart, advanceLabel = "下一步", isLast = false }) {
  return (
    <Box sx={{
      p: 2,
      borderTop: `0.5px solid ${COLOR.border}`,
      bgcolor: COLOR.white,
      display: "flex",
      flexDirection: "column",
      gap: 1,
    }}>
      <AppButton
        variant="primary" size="md" fullWidth
        disabled={!canAdvance}
        onClick={onAdvance}
      >
        {isLast ? "完成引导" : advanceLabel}
      </AppButton>
      <Box sx={{ display: "flex", gap: 1 }}>
        <AppButton variant="secondary" size="sm" fullWidth onClick={onRestart}>
          重新开始
        </AppButton>
        <AppButton variant="secondary" size="sm" fullWidth onClick={onSkip}>
          跳过引导
        </AppButton>
      </Box>
    </Box>
  );
}

// ── Visual connector: rule → usage arrow ──────────────────────────────────────

function RuleArrowConnector({ label }) {
  return (
    <Box sx={{ display: "flex", flexDirection: "column", alignItems: "center", py: 1, gap: "3px" }}>
      <Box sx={{ width: 2, height: 18, bgcolor: COLOR.primary, borderRadius: 1, opacity: 0.5 }} />
      <Box sx={{ width: 0, height: 0, borderLeft: "6px solid transparent", borderRight: "6px solid transparent", borderTop: `8px solid ${COLOR.primary}`, opacity: 0.6 }} />
      <Typography sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.primary, fontWeight: 600, mt: "4px" }}>{label}</Typography>
    </Box>
  );
}

// ── Rule echo card ────────────────────────────────────────────────────────────

function RuleEchoCard({ title, body }) {
  return (
    <Box sx={{ mx: 2, mt: 2, p: 2, bgcolor: COLOR.primaryLight, border: `1px solid ${COLOR.primary}30`, borderRadius: RADIUS.lg }}>
      <Typography sx={{ fontSize: TYPE.micro.fontSize, fontWeight: 600, color: COLOR.primary, mb: 0.5, textTransform: "uppercase", letterSpacing: "0.3px" }}>你刚添加的规则</Typography>
      <Typography sx={{ fontSize: TYPE.heading.fontSize, fontWeight: 700, color: COLOR.text1, mb: 0.5 }}>{title}</Typography>
      <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text2, lineHeight: 1.6 }}>{body}</Typography>
    </Box>
  );
}

// ── Step 1: 添加一条规则 ───────────────────────────────────────────────────────

function Step1Content({ doctorId, progress, updateProgress, setCanAdvance, api }) {
  const navigate = useAppNavigate();
  const [searchParams] = useSearchParams();
  const [hintDismissed, setHintDismissed] = useState(false);

  // Check for return from AddKnowledgeSubpage
  const savedSource = searchParams.get("saved");
  const savedTitle = searchParams.get("savedTitle");
  const savedId = searchParams.get("savedId");

  useEffect(() => {
    if (savedSource) {
      updateProgress((prev) => {
        const newSources = [...new Set([...prev.savedSources, savedSource])];
        return {
          savedSources: newSources,
          savedTitles: { ...(prev.savedTitles || {}), [savedSource]: savedTitle || "已添加" },
          savedIds: { ...(prev.savedIds || {}), ...(savedId ? { [savedSource]: savedId } : {}) },
          savedRuleTitle: savedTitle || prev.savedRuleTitle,
          ...(savedId ? { savedRuleIds: [...new Set([...(prev.savedRuleIds || []), savedId])] } : {}),
        };
      });
      // Clean the URL params
      const params = new URLSearchParams(window.location.search);
      params.delete("saved");
      params.delete("savedTitle");
      params.delete("savedId");
      window.history.replaceState({}, "", `${window.location.pathname}?${params.toString()}`);
    }
  }, [savedSource]); // eslint-disable-line react-hooks/exhaustive-deps

  const savedSources = progress.savedSources || [];
  // Unlock after any 1 source saved
  const allDone = savedSources.length >= 1;

  // When first source is saved, call ensureOnboardingExamples and enable advance
  useEffect(() => {
    if (!allDone) { setCanAdvance(false); return; }
    if (progress.proofData) { setCanAdvance(true); return; }
    const lastRuleId = Object.values(progress.savedIds || {}).filter(Boolean).pop();
    (api.ensureOnboardingExamples || (() => Promise.resolve(null)))(doctorId, {
      knowledgeItemId: lastRuleId,
    }).then((data) => {
      if (data) updateProgress({ proofData: data });
      setCanAdvance(true);
    }).catch(() => { setCanAdvance(true); });
  }, [allDone]); // eslint-disable-line react-hooks/exhaustive-deps

  const sources = [
    { key: "file", label: "文件上传", subtitle: "PDF、Word、图片", icon: ICON_BADGES.kb_upload, hint: "点击上传一份文件，AI 会自动提取知识" },
    { key: "url", label: "网址导入", subtitle: "粘贴网页链接", icon: ICON_BADGES.kb_url, hint: "点击粘贴一个网页链接，AI 会自动抓取内容" },
    { key: "text", label: "手动输入", subtitle: "直接输入规则文本", icon: ICON_BADGES.kb_doctor, hint: "点击输入一条你的临床规则" },
  ];
  const firstTodo = sources.find((s) => !savedSources.includes(s.key));
  const showHint = !hintDismissed && firstTodo && savedSources.length < 3;

  return (
    <>
      <ContextCard>
        添加一条你的诊疗规则，让 AI 学会你的思维方式
      </ContextCard>
      <Box sx={{ mt: 2, bgcolor: COLOR.white, borderTop: `0.5px solid ${COLOR.border}`, borderBottom: `0.5px solid ${COLOR.border}` }}>
        {sources.map((s, i) => {
          const isTarget = showHint && firstTodo?.key === s.key;
          const row = (
            <ListCard
              avatar={<IconBadge config={s.icon} />}
              title={s.label}
              subtitle={s.subtitle}
              right={
                savedSources.includes(s.key)
                  ? <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.primary, fontWeight: 600 }}>已完成</Typography>
                  : <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4 }}>待添加</Typography>
              }
              chevron
              onClick={() => {
                setHintDismissed(true);
                navigate(`${dp("settings/knowledge/add")}?onboarding=1&source=${s.key}&wizard=1`);
              }}
              sx={{
                ...(i === sources.length - 1 ? { borderBottom: "none" } : {}),
                ...(isTarget ? { outline: `2px dashed ${COLOR.primary}`, outlineOffset: -2, borderRadius: RADIUS.sm } : {}),
              }}
            />
          );
          return (
            <Box key={s.key}>
              {isTarget ? (
                <SpotlightHint active hint={s.hint}>
                  {row}
                </SpotlightHint>
              ) : row}
            </Box>
          );
        })}
      </Box>
      <Box sx={{ px: 2, mt: 2 }}>
        <Typography sx={{ fontSize: TYPE.caption.fontSize, color: allDone ? COLOR.primary : COLOR.text4, textAlign: "center", fontWeight: allDone ? 600 : 400 }}>
          {allDone ? "已完成" : "添加任意一条即可继续"}
        </Typography>
      </Box>
    </>
  );
}

// ── Step 2: 看AI怎么用它 (combined diagnosis + reply proof) ───────────────────

const STEP2_DRAFT_TEXT = "张阿姨家属您好，LVB术后出现头痛加重伴认知改善后再次下降，需要警惕吻合口狭窄或血栓。请尽快带张阿姨来医院复查荧光成像，评估吻合口通畅性。在此之前请让她卧床休息，避免剧烈活动。";
const HIGHLIGHTED_SENTENCE = "LVB术后出现头痛加重伴认知改善后再次下降，需要警惕吻合口狭窄或血栓";

function StepProofContent({ progress, setCanAdvance }) {
  useEffect(() => { setCanAdvance(true); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const ruleTitle = progress.savedRuleTitle || "LVB术后吻合口评估";
  const ruleBody = "术侧头痛加重、认知改善后再次下降 → 警惕吻合口血栓";
  const citedRuleTitle = ruleTitle;

  // Split draft text around the highlighted sentence for inline highlight rendering
  const draftParts = STEP2_DRAFT_TEXT.split(HIGHLIGHTED_SENTENCE);

  return (
    <>
      {/* ── Section A: 诊断审核 ─────────────────────────────────────── */}
      <RuleEchoCard title={ruleTitle} body={ruleBody} />

      <Box sx={{ display: "flex", justifyContent: "center" }}>
        <RuleArrowConnector label="AI 在诊断中引用了它" />
      </Box>

      {/* Patient strip */}
      <Box sx={{ mx: 2, px: 2, py: 1, bgcolor: COLOR.white, borderRadius: RADIUS.md, border: `0.5px solid ${COLOR.border}`, display: "flex", alignItems: "center", gap: 1.5, mb: 1 }}>
        <NameAvatar name="张阿姨" size={36} />
        <Box>
          <Typography sx={{ fontSize: TYPE.action.fontSize, fontWeight: 500, color: COLOR.text1 }}>张阿姨 · 65岁</Typography>
          <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4 }}>右侧头痛加重 · 认知改善后下降</Typography>
        </Box>
      </Box>

      {/* AI differential rows */}
      <Box sx={{ mx: 2, bgcolor: COLOR.white, borderRadius: RADIUS.md, border: `0.5px solid ${COLOR.border}`, overflow: "hidden" }}>
        {/* Row 1 — spotlighted */}
        <SpotlightHint active>
          <Box sx={{ display: "flex", alignItems: "flex-start", gap: 1.5, px: 2, py: 1.5, borderBottom: `0.5px solid ${COLOR.borderLight}` }}>
            <Box sx={{
              width: 18, height: 18, borderRadius: "50%", flexShrink: 0, mt: 0.5,
              bgcolor: COLOR.primary, display: "flex", alignItems: "center", justifyContent: "center",
            }}>
              <Typography sx={{ color: COLOR.white, fontSize: 11, lineHeight: 1 }}>✓</Typography>
            </Box>
            <Box sx={{ flex: 1, minWidth: 0 }}>
              <Typography sx={{ fontSize: TYPE.action.fontSize, fontWeight: 500, color: COLOR.text1 }}>
                吻合口血栓或狭窄
              </Typography>
              <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text3, mt: 0.5, lineHeight: 1.6 }}>
                LVB术后1周出现术侧头痛加重，需{" "}
                <Box component="span" sx={{ bgcolor: "#fff8c5", borderBottom: "2px solid #f0e040", borderRadius: "2px", px: "1px" }}>
                  警惕吻合口血栓或狭窄
                </Box>
                。建议复查荧光成像评估吻合口通畅性。
              </Typography>
              <Box sx={{ mt: 0.5 }}>
                <Box component="span" sx={{ fontSize: TYPE.micro.fontSize, color: "#e53935", bgcolor: "#fdecea", px: 1, py: 0.25, borderRadius: RADIUS.sm }}>
                  引用: {citedRuleTitle}
                </Box>
              </Box>
            </Box>
          </Box>
        </SpotlightHint>
        {/* Rows 2-3 — dimmed */}
        <Box sx={{ opacity: 0.5 }}>
          <Box sx={{ display: "flex", alignItems: "flex-start", gap: 1.5, px: 2, py: 1.5, borderBottom: `0.5px solid ${COLOR.borderLight}` }}>
            <Box sx={{ width: 18, height: 18, borderRadius: "50%", border: `1.5px solid ${COLOR.border}`, flexShrink: 0, mt: 0.5 }} />
            <Box sx={{ flex: 1, minWidth: 0 }}>
              <Typography sx={{ fontSize: TYPE.action.fontSize, fontWeight: 500, color: COLOR.text1 }}>术后正常反应</Typography>
              <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text4, mt: 0.5 }}>LVB术后轻度头痛头晕多为一过性，1-2周可缓解。</Typography>
            </Box>
          </Box>
          <Box sx={{ display: "flex", alignItems: "flex-start", gap: 1.5, px: 2, py: 1.5 }}>
            <Box sx={{ width: 18, height: 18, borderRadius: "50%", border: `1.5px solid ${COLOR.border}`, flexShrink: 0, mt: 0.5 }} />
            <Box sx={{ flex: 1, minWidth: 0 }}>
              <Typography sx={{ fontSize: TYPE.action.fontSize, fontWeight: 500, color: COLOR.text1 }}>切口血肿</Typography>
              <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text4, mt: 0.5 }}>右侧稍肿胀但无渗出，超声示少量积液，暂观察。</Typography>
            </Box>
          </Box>
        </Box>
      </Box>

      {/* ── Divider ────────────────────────────────────────────────── */}
      <Box sx={{ mx: 2, my: 2, borderTop: `0.5px solid ${COLOR.border}` }} />

      {/* ── Section B: 回复起草 ─────────────────────────────────────── */}
      <Box sx={{ display: "flex", justifyContent: "center" }}>
        <RuleArrowConnector label="AI 在回复中也引用了它" />
      </Box>

      {/* Last patient message */}
      <Box sx={{ mx: 2, mb: 1, display: "flex", alignItems: "flex-end", gap: 1 }}>
        <NameAvatar name="张阿姨" size={36} />
        <Box sx={{
          maxWidth: "72%", px: 1.5, py: 1,
          borderRadius: `${RADIUS.sm} ${RADIUS.sm} ${RADIUS.sm} 0`,
          bgcolor: COLOR.white, fontSize: TYPE.body.fontSize, lineHeight: 1.7, color: COLOR.text1,
        }}>
          她今天头更疼了，是不是手术出问题了？
        </Box>
      </Box>

      {/* AI draft card — read-only preview, no confirm action needed */}
      <Box sx={{ mx: 2, mb: 1, display: "flex", flexDirection: "row-reverse", alignItems: "flex-end", gap: 1 }}>
        <MsgAvatar isUser={false} size={36} />
        <Box sx={{ maxWidth: "78%", bgcolor: COLOR.primaryLight, border: `1px solid ${COLOR.primary}30`, borderRadius: RADIUS.md, px: 2, py: 1.5 }}>
          <Typography sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.primary, fontWeight: 600, mb: 0.5 }}>
            AI 已起草回复
          </Typography>
          <Typography sx={{ fontSize: TYPE.body.fontSize, color: COLOR.text1, lineHeight: 1.7 }}>
            {draftParts[0]}
            <Box component="span" sx={{ bgcolor: "#fff8c5", borderBottom: "2px solid #f0e040", borderRadius: "2px", px: "1px" }}>
              {HIGHLIGHTED_SENTENCE}
            </Box>
            {draftParts[1]}
          </Typography>
          <Box sx={{ mt: 1 }}>
            <Box component="span" sx={{ fontSize: TYPE.micro.fontSize, color: "#e53935", bgcolor: "#fdecea", px: 1, py: 0.25, borderRadius: RADIUS.sm }}>
              引用: {citedRuleTitle}
            </Box>
          </Box>
        </Box>
      </Box>

      <Box sx={{ pb: 2 }} />
    </>
  );
}

// ── Step 3: 确认并开始 ────────────────────────────────────────────────────────

function StepDoneContent({ doctorId, progress, updateProgress, setCanAdvance, api }) {
  const [ready, setReady] = useState(false);
  const [showInterview, setShowInterview] = useState(false);

  useEffect(() => {
    setCanAdvance(true);

    // Fetch a patient preview token in background so the sheet opens instantly
    const savedToken = progress?.interviewToken;
    if (savedToken) { setReady(true); return; }

    (async () => {
      try {
        const demoName = `体验患者${Date.now().toString(36).slice(-4)}`;
        const data = await api.createOnboardingPatientEntry(doctorId, { patientName: demoName, gender: "女", age: 65 });
        const patientToken = data?.portal_token || data?.token;
        if (patientToken) updateProgress({ interviewToken: patientToken });
        setReady(true);
      } catch {
        setReady(true);
      }
    })();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const interviewToken = progress?.interviewToken;

  return (
    <>
      <Box sx={{ display: "flex", flexDirection: "column", alignItems: "center", pt: 4, pb: 2, px: 2 }}>
        <CheckCircleOutlineIcon sx={{ fontSize: 64, color: COLOR.primary, mb: 2 }} />
        <Typography sx={{ fontSize: TYPE.title.fontSize, fontWeight: 700, color: COLOR.text1, mb: 1 }}>
          设置完成
        </Typography>
        <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text3, textAlign: "center", lineHeight: 1.7 }}>
          AI 已学会你的规则，现在试试看患者发来消息时 AI 如何帮你处理。
        </Typography>

        {/* Optional: inline patient interview sheet */}
        <Box sx={{
          mt: 3, width: "100%", p: 2.5,
          bgcolor: COLOR.surfaceAlt, borderRadius: RADIUS.lg,
          border: `1px solid ${COLOR.border}`,
        }}>
          <Typography sx={{ fontSize: TYPE.heading.fontSize, fontWeight: 600, color: COLOR.text1, mb: 0.5 }}>
            可选：体验患者端预问诊
          </Typography>
          <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text3, lineHeight: 1.6, mb: 2 }}>
            点击下方，在当前页面体验患者填写预问诊的完整流程
          </Typography>
          <AppButton
            variant="secondary" size="sm"
            onClick={() => setShowInterview(true)}
            disabled={!ready || !interviewToken}
          >
            体验患者端 →
          </AppButton>
        </Box>
      </Box>

      {/* Patient interview embedded in a bottom sheet — no navigation away */}
      <SheetDialog
        open={showInterview}
        onClose={() => setShowInterview(false)}
        title="患者预问诊体验"
      >
        <Box sx={{ height: "70vh", overflow: "hidden", display: "flex", flexDirection: "column" }}>
          {/* Only mount InterviewPage when sheet is open — avoids usePatientApi() crash
              when drawer children render eagerly with no PatientApiContext provider. */}
          {showInterview && interviewToken && (
            <PatientApiProvider>
              <PatientInterviewPage
                token={interviewToken}
                onBack={() => setShowInterview(false)}
                onLogout={() => setShowInterview(false)}
              />
            </PatientApiProvider>
          )}
        </Box>
      </SheetDialog>
    </>
  );
}

// ── Main Wizard ───────────────────────────────────────────────────────────────

export default function OnboardingWizard() {
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useAppNavigate();
  const { doctorId, accessToken, setAuth } = useDoctorStore(); // eslint-disable-line no-unused-vars
  const api = useApi();

  const stepParam = parseInt(searchParams.get("step") || "1", 10);
  const isDone = searchParams.get("step") === "done";

  // Load persisted progress
  const [progress, setProgress] = useState(() => getWizardProgress(doctorId));
  const [canAdvance, setCanAdvance] = useState(false);

  // Current step: clamp to valid range
  const step = isDone ? 0 : Math.max(1, Math.min(stepParam, TOTAL_STEPS));

  // Persist progress changes
  const updateProgress = useCallback((patch) => {
    const updated = setWizardProgress(doctorId, patch);
    setProgress(updated);
    return updated;
  }, [doctorId]);

  function goToStep(n) {
    setCanAdvance(false);
    setSearchParams({ step: String(n) }, { replace: true });
  }

  function handleAdvance() {
    const next = step + 1;
    const completedSteps = [...new Set([...(progress.completedSteps || []), step])];
    updateProgress({ completedSteps, currentStep: next });
    if (next > TOTAL_STEPS) {
      markWizardDone(doctorId, "completed");
      // Seed demo data in background — don't block navigation
      import("../../api").then(({ seedDemo }) => seedDemo(doctorId).catch(() => {}));
      navigate(dp());
    } else {
      goToStep(next);
    }
  }

  const [confirmSkip, setConfirmSkip] = useState(false);
  const [confirmRestart, setConfirmRestart] = useState(false);

  function handleSkip() {
    markWizardDone(doctorId, "skipped");
    navigate(dp());
  }

  function handleRestart() {
    clearWizardProgress(doctorId);
    setProgress(getWizardProgress(doctorId));
    goToStep(1);
  }

  function handleBack() {
    if (step > 1) goToStep(step - 1);
  }

  if (isDone) {
    navigate(dp());
    return null;
  }

  // Step content renderer
  function renderStep() {
    switch (step) {
      case 1: return <Step1Content doctorId={doctorId} progress={progress} updateProgress={updateProgress} setCanAdvance={setCanAdvance} api={api} />;
      case 2: return <StepProofContent progress={progress} setCanAdvance={setCanAdvance} />;
      case 3: return <StepDoneContent doctorId={doctorId} progress={progress} updateProgress={updateProgress} setCanAdvance={setCanAdvance} api={api} />;
      default: return null;
    }
  }

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%", bgcolor: COLOR.surfaceAlt }}>
      <SubpageHeader
        title={STEP_TITLES[step] || "引导"}
        onBack={step > 1 ? handleBack : undefined}
      />
      <ProgressBar step={step} />
      <Box sx={{ flex: 1, overflow: "auto" }}>
        {renderStep()}
      </Box>
      <WizardFooter
        canAdvance={canAdvance}
        onAdvance={handleAdvance}
        onSkip={() => setConfirmSkip(true)}
        onRestart={() => setConfirmRestart(true)}
        isLast={step === TOTAL_STEPS}
      />
      <ConfirmDialog
        open={confirmSkip}
        title="跳过引导？"
        message="跳过后可以在「我的AI」页面重新体验引导。"
        confirmLabel="跳过"
        onConfirm={handleSkip}
        onCancel={() => setConfirmSkip(false)}
      />
      <ConfirmDialog
        open={confirmRestart}
        title="重新开始？"
        message="当前进度将被清除，从第一步重新开始。"
        confirmLabel="重新开始"
        onConfirm={handleRestart}
        onCancel={() => setConfirmRestart(false)}
      />
    </Box>
  );
}

// Exported for use by step implementations
export { ContextCard, STEP_TITLES, SpotlightHint };
