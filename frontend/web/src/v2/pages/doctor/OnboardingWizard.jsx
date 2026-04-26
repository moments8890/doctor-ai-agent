/**
 * v2 OnboardingWizard — antd-mobile rewrite of the doctor onboarding flow.
 *
 * Steps:
 *   1. 添加一条规则   — navigate to knowledge add, return with ?saved=...
 *   2. 看AI怎么用它   — interactive demo: confirm diagnosis + send reply
 *   3. 确认并开始     — completion screen with optional patient intake preview
 *
 * No MUI, no framer-motion, no src/components/, no src/theme.js
 */
import { useState, useEffect, useCallback } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { NavBar, Button, Result, Dialog, SafeArea, Steps } from "antd-mobile";
import { CheckCircleFill, FileOutline, GlobalOutline, EditSOutline, CheckOutline } from "antd-mobile-icons";
import { useApi } from "../../../api/ApiContext";
import { useDoctorStore } from "../../../store/doctorStore";
import { useQueryClient } from "@tanstack/react-query";
import { QK } from "../../../lib/queryKeys";
import {
  getWizardProgress,
  setWizardProgress,
  markWizardDone,
  clearWizardProgress,
} from "./onboardingWizardState";
import { seedDemo, updateDoctorProfile } from "../../../api";
import { markAllReleasesSeen } from "../../../store/releaseStore";
import { dp } from "../../../utils/doctorBasePath";
import { APP, FONT, RADIUS } from "../../theme";

const TOTAL_STEPS = 3;

const STEP_TITLES = {
  1: "添加一条规则",
  2: "看AI怎么用它",
  3: "确认并开始",
};

// ── Shared layout helpers ──────────────────────────────────────────────────────

function ContextCard({ children }) {
  return (
    <div
      style={{
        margin: "12px 16px 0",
        padding: "12px 14px",
        backgroundColor: APP.primaryLight,
        border: `1px solid rgba(7,193,96,0.18)`,
        borderRadius: RADIUS.md,
        fontSize: FONT.base,
        color: APP.text2,
        lineHeight: 1.7,
      }}
    >
      {children}
    </div>
  );
}

function RuleArrowConnector({ label }) {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        padding: "6px 0",
        gap: 3,
      }}
    >
      <div
        style={{
          width: 2,
          height: 18,
          backgroundColor: APP.primary,
          borderRadius: RADIUS.xs,
        opacity: 0.5,
        }}
      />
      {/* downward triangle */}
      <div
        style={{
          width: 0,
          height: 0,
          borderLeft: "6px solid transparent",
          borderRight: "6px solid transparent",
          borderTop: `8px solid ${APP.primary}`,
          opacity: 0.6,
        }}
      />
      <span
        style={{
          fontSize: FONT.xs,
          color: APP.primary,
          fontWeight: 600,
          marginTop: 4,
        }}
      >
        {label}
      </span>
    </div>
  );
}

function RuleEchoCard({ title, body }) {
  return (
    <div
      style={{
        margin: "12px 16px 0",
        padding: "12px 14px",
        backgroundColor: APP.primaryLight,
        border: "1px solid rgba(7,193,96,0.18)",
        borderRadius: RADIUS.md,
      }}
    >
      <div
        style={{
          fontSize: FONT.xs,
          fontWeight: 600,
          color: APP.primary,
          marginBottom: 4,
          textTransform: "uppercase",
          letterSpacing: "0.3px",
        }}
      >
        你刚添加的规则
      </div>
      <div
        style={{
          fontSize: FONT.md,
          fontWeight: 700,
          color: APP.text1,
          marginBottom: 3,
        }}
      >
        {title}
      </div>
      <div style={{ fontSize: FONT.sm, color: APP.text2, lineHeight: 1.6 }}>{body}</div>
    </div>
  );
}

// ── Step 1: 添加一条规则 ───────────────────────────────────────────────────────

const SOURCES = [
  { key: "file", label: "文件上传", subtitle: "PDF、Word、图片" },
  { key: "url", label: "网址导入", subtitle: "粘贴网页链接" },
  { key: "text", label: "手动输入", subtitle: "直接输入规则文本" },
];

function Step1Content({ doctorId, progress, updateProgress, setCanAdvance, api }) {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

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
          ...(savedId
            ? { savedRuleIds: [...new Set([...(prev.savedRuleIds || []), savedId])] }
            : {}),
        };
      });
      const params = new URLSearchParams(window.location.search);
      params.delete("saved");
      params.delete("savedTitle");
      params.delete("savedId");
      window.history.replaceState({}, "", `${window.location.pathname}?${params.toString()}`);
    }
  }, [savedSource]); // eslint-disable-line react-hooks/exhaustive-deps

  const savedSources = progress.savedSources || [];
  const allDone = savedSources.length >= 1;

  useEffect(() => {
    if (!allDone) {
      setCanAdvance(false);
      return;
    }
    if (progress.proofData) {
      setCanAdvance(true);
      return;
    }
    const lastRuleId = Object.values(progress.savedIds || {})
      .filter(Boolean)
      .pop();
    (api.ensureOnboardingExamples || (() => Promise.resolve(null)))(doctorId, {
      knowledgeItemId: lastRuleId,
    })
      .then((data) => {
        if (data) updateProgress({ proofData: data });
        setCanAdvance(true);
      })
      .catch(() => {
        setCanAdvance(true);
      });
  }, [allDone]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <>
      <ContextCard>添加一条你的诊疗规则，让 AI 学会你的思维方式</ContextCard>

      <div
        style={{
          marginTop: 16,
          backgroundColor: APP.surface,
          borderTop: `0.5px solid ${APP.border}`,
          borderBottom: `0.5px solid ${APP.border}`,
        }}
      >
        {SOURCES.map((s, i) => {
          const done = savedSources.includes(s.key);
          return (
            <div
              key={s.key}
              onClick={() => {
                navigate(
                  `${dp("settings/knowledge/add")}?onboarding=1&source=${s.key}&wizard=1`,
                );
              }}
              style={{
                display: "flex",
                alignItems: "center",
                padding: "14px 16px",
                borderBottom:
                  i < SOURCES.length - 1 ? `0.5px solid ${APP.border}` : "none",
                cursor: "pointer",
                backgroundColor: APP.surface,
              }}
            >
              {/* Icon placeholder */}
              <div
                style={{
                  width: 36,
                  height: 36,
                  borderRadius: RADIUS.md,
                  backgroundColor: APP.primaryLight,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  flexShrink: 0,
                  marginRight: 12,
                  fontSize: FONT.lg,
                  color: APP.primary,
                }}
              >
                {s.key === "file" ? <FileOutline style={{ fontSize: ICON.xs }} /> : s.key === "url" ? <GlobalOutline style={{ fontSize: ICON.xs }} /> : <EditSOutline style={{ fontSize: ICON.xs }} />}
              </div>

              <div style={{ flex: 1 }}>
                <div style={{ fontSize: FONT.md, fontWeight: 500, color: APP.text1 }}>
                  {s.label}
                </div>
                <div style={{ fontSize: FONT.sm, color: APP.text4, marginTop: 2 }}>
                  {s.subtitle}
                </div>
              </div>

              <div
                style={{
                  fontSize: FONT.sm,
                  color: done ? APP.primary : APP.text4,
                  fontWeight: done ? 600 : 400,
                  marginRight: 6,
                }}
              >
                {done ? "已完成" : "待添加"}
              </div>
              <div style={{ color: APP.text4, fontSize: FONT.main }}>›</div>
            </div>
          );
        })}
      </div>

      <div
        style={{
          padding: "8px 16px",
          textAlign: "center",
          fontSize: FONT.sm,
        color: allDone ? APP.primary : APP.text4,
          fontWeight: allDone ? 600 : 400,
        }}
      >
        {allDone ? "已完成" : "添加任意一条即可继续"}
      </div>
    </>
  );
}

// ── Step 2: 看AI怎么用它 ──────────────────────────────────────────────────────

const STEP2_DRAFT_TEXT =
  "您好，高血压患者出现头痛加重伴呕吐、视物模糊，需要警惕高血压脑病或颅内出血。建议立即测量血压，如果血压明显升高，请尽快到急诊就诊做头颅CT检查。在就医前请卧床休息，避免情绪激动。";
const HIGHLIGHTED_SENTENCE =
  "高血压患者出现头痛加重伴呕吐、视物模糊，需要警惕高血压脑病或颅内出血";

function Step2Content({ progress, setCanAdvance }) {
  const [diagConfirmed, setDiagConfirmed] = useState(false);
  const [replySent, setReplySent] = useState(false);

  useEffect(() => {
    setCanAdvance(diagConfirmed && replySent);
  }, [diagConfirmed, replySent]); // eslint-disable-line react-hooks/exhaustive-deps

  const ruleTitle = progress.savedRuleTitle || "高血压患者头痛鉴别要点";
  const ruleBody = "高血压患者新发头痛 → 排除高血压脑病、颅内出血、后循环缺血";
  const draftParts = STEP2_DRAFT_TEXT.split(HIGHLIGHTED_SENTENCE);

  return (
    <>
      {/* Rule echo */}
      <RuleEchoCard title={ruleTitle} body={ruleBody} />

      {/* Diagnosis section */}
      <div style={{ display: "flex", justifyContent: "center" }}>
        <RuleArrowConnector label="AI 在诊断中引用了它" />
      </div>

      {/* Patient strip */}
      <div
        style={{
          margin: "0 16px 8px",
          padding: "10px 14px",
          backgroundColor: APP.surface,
          borderRadius: RADIUS.md,
          border: `0.5px solid ${APP.border}`,
          display: "flex",
          alignItems: "center",
          gap: 10,
        }}
      >
        <div
          style={{
            width: 36,
            height: 36,
            borderRadius: "50%",
            backgroundColor: APP.accentLight,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            flexShrink: 0,
            fontSize: FONT.md,
            fontWeight: 700,
            color: APP.accent,
          }}
        >
          张
        </div>
        <div>
          <div style={{ fontSize: FONT.main, fontWeight: 500, color: APP.text1 }}>
            张秀兰 · 72岁
          </div>
          <div style={{ fontSize: FONT.sm, color: APP.text4 }}>头痛头晕3天 · 高血压10年</div>
        </div>
      </div>

      {/* AI differential rows */}
      <div
        style={{
          margin: "0 16px",
          backgroundColor: APP.surface,
          borderRadius: RADIUS.md,
          border: `0.5px solid ${APP.border}`,
          overflow: "hidden",
        }}
      >
        {/* Row 1 — tappable */}
        <div
          onClick={() => setDiagConfirmed(true)}
          style={{
            display: "flex",
            alignItems: "flex-start",
            gap: 10,
            padding: "12px 14px",
            borderBottom: `0.5px solid ${APP.borderLight}`,
            cursor: diagConfirmed ? "default" : "pointer",
            outline: diagConfirmed ? "none" : `2px dashed ${APP.primary}`,
            outlineOffset: -2,
          }}
        >
          <div
            style={{
              width: 18,
              height: 18,
              borderRadius: "50%",
              flexShrink: 0,
              marginTop: 2,
              backgroundColor: diagConfirmed ? APP.primary : "transparent",
              border: diagConfirmed ? "none" : `1.5px solid ${APP.border}`,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            {diagConfirmed && (
              <CheckOutline style={{ color: APP.white, fontSize: FONT.xs, lineHeight: 1 }} />
            )}
          </div>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: FONT.main, fontWeight: 500, color: APP.text1 }}>
              高血压脑病/高血压急症
            </div>
            <div
              style={{ fontSize: FONT.sm, color: APP.text3, marginTop: 4, lineHeight: 1.6 }}
            >
              患者有10年高血压病史，本次出现头痛加重伴呕吐，需{" "}
              <span
                style={{
                  backgroundColor: APP.highlightBg,
                  borderBottom: "2px solid #f0e040",
                  borderRadius: RADIUS.xs,
                  padding: "0 1px",
                }}
              >
                警惕高血压脑病或颅内出血
              </span>
              。需紧急评估血压及靶器官损害。
            </div>
            <div style={{ marginTop: 4 }}>
              <span
                style={{
                  fontSize: FONT.xs,
                  color: APP.danger,
                  backgroundColor: APP.dangerLight,
                  padding: "2px 6px",
                  borderRadius: RADIUS.xs,
                }}
              >
                引用: {ruleTitle}
              </span>
            </div>
          </div>
        </div>

        {/* Rows 2–3 — dimmed */}
        <div style={{ opacity: 0.45 }}>
          {[
            { title: "后循环缺血", body: "头晕伴视物模糊，需MRA评估椎基底动脉供血。" },
            { title: "偏头痛", body: "胀痛伴恶心呕吐，但高血压背景下需先排除继发性原因。" },
          ].map((row, i) => (
            <div
              key={i}
              style={{
                display: "flex",
                alignItems: "flex-start",
                gap: 10,
                padding: "12px 14px",
                borderBottom:
                  i === 0 ? `0.5px solid ${APP.borderLight}` : "none",
              }}
            >
              <div
                style={{
                  width: 18,
                  height: 18,
                  borderRadius: "50%",
                  border: `1.5px solid ${APP.border}`,
                  flexShrink: 0,
                  marginTop: 2,
                }}
              />
              <div>
                <div style={{ fontSize: FONT.main, fontWeight: 500, color: APP.text1 }}>
                  {row.title}
                </div>
                <div style={{ fontSize: FONT.sm, color: APP.text4, marginTop: 4 }}>
                  {row.body}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Divider */}
      <div
        style={{
          margin: "14px 16px",
          borderTop: `0.5px solid ${APP.border}`,
        }}
      />

      {/* Reply section */}
      <div style={{ display: "flex", justifyContent: "center" }}>
        <RuleArrowConnector label="AI 在回复中也引用了它" />
      </div>

      {/* Patient message bubble */}
      <div
        style={{
          margin: "0 16px 8px",
          display: "flex",
          alignItems: "flex-end",
          gap: 8,
        }}
      >
        <div
          style={{
            width: 34,
            height: 34,
            borderRadius: "50%",
            backgroundColor: APP.accentLight,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            flexShrink: 0,
            fontSize: FONT.main,
            fontWeight: 700,
            color: APP.accent,
          }}
        >
          张
        </div>
        <div
          style={{
            maxWidth: "72%",
            padding: "10px 12px",
            borderRadius: "8px 8px 8px 0",
            backgroundColor: APP.surface,
            fontSize: FONT.main,
            lineHeight: 1.7,
            color: APP.text1,
            border: `0.5px solid ${APP.border}`,
          }}
        >
          医生，我妈这两天头疼得厉害，还吐了一次，看东西也模糊，需要来医院吗？
        </div>
      </div>

      {/* AI draft */}
      {!replySent && (
        <div
          style={{
            margin: "0 16px 8px",
            display: "flex",
            flexDirection: "row-reverse",
            alignItems: "flex-end",
            gap: 8,
          }}
        >
          <div
            style={{
              width: 34,
              height: 34,
              borderRadius: "50%",
              backgroundColor: APP.primaryLight,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              flexShrink: 0,
              fontSize: FONT.md,
              color: APP.primary,
            }}
          >
            AI
          </div>
          <div
            style={{
              maxWidth: "78%",
              padding: "12px 14px",
              borderRadius: RADIUS.md,
              backgroundColor: APP.primaryLight,
              border: "1px solid rgba(7,193,96,0.18)",
            }}
          >
            <div
              style={{
                fontSize: FONT.xs,
                color: APP.primary,
                fontWeight: 600,
                marginBottom: 4,
              }}
            >
              AI起草回复 · 待你确认
            </div>
            <div style={{ fontSize: FONT.main, color: APP.text1, lineHeight: 1.7 }}>
              {draftParts[0]}
              <span
                style={{
                  backgroundColor: APP.highlightBg,
                  borderBottom: "2px solid #f0e040",
                  borderRadius: RADIUS.xs,
                  padding: "0 1px",
                }}
              >
                {HIGHLIGHTED_SENTENCE}
              </span>
              {draftParts[1]}
            </div>
            <div style={{ marginTop: 6 }}>
              <span
                style={{
                  fontSize: FONT.xs,
                  color: APP.danger,
                  backgroundColor: APP.dangerLight,
                  padding: "2px 6px",
                  borderRadius: RADIUS.xs,
                }}
              >
                引用: {ruleTitle}
              </span>
            </div>
            <div
              style={{
                display: "flex",
                justifyContent: "flex-end",
                gap: 16,
                marginTop: 10,
                paddingTop: 8,
                borderTop: "0.5px solid rgba(7,193,96,0.15)",
              }}
            >
              <span style={{ fontSize: FONT.sm, color: APP.text4 }}>修改</span>
              <span
                onClick={() => setReplySent(true)}
                style={{
                  fontSize: FONT.sm,
                  color: APP.primary,
                  fontWeight: 600,
                  cursor: "pointer",
                  padding: "1px 4px",
                  outline: `2px dashed ${APP.primary}`,
                  outlineOffset: 1,
                  borderRadius: RADIUS.xs,
                }}
              >
                确认发送 ›
              </span>
            </div>
          </div>
        </div>
      )}

      {replySent && (
        <div
          style={{
            margin: "0 16px 8px",
            display: "flex",
            flexDirection: "row-reverse",
            alignItems: "flex-end",
            gap: 8,
          }}
        >
          <div
            style={{
              width: 34,
              height: 34,
              borderRadius: "50%",
              backgroundColor: APP.primaryLight,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              flexShrink: 0,
              fontSize: FONT.md,
              color: APP.primary,
            }}
          >
            我
          </div>
          <div
            style={{
              maxWidth: "72%",
              padding: "10px 12px",
              borderRadius: "8px 8px 0 8px",
              backgroundColor: APP.wechatGreen,
              fontSize: FONT.main,
              lineHeight: 1.7,
              color: APP.text1,
            }}
          >
            {STEP2_DRAFT_TEXT}
          </div>
        </div>
      )}

      <div style={{ paddingBottom: 16 }} />
    </>
  );
}

// ── Step 3: 确认并开始 ────────────────────────────────────────────────────────

function Step3Content({ doctorId, progress, updateProgress, setCanAdvance, api }) {
  const queryClient = useQueryClient();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    setCanAdvance(true);

    const savedToken = progress?.intakeToken;
    if (savedToken) {
      setReady(true);
      return;
    }

    (async () => {
      try {
        const demoName = `体验患者${Date.now().toString(36).slice(-4)}`;
        const data = await api.createOnboardingPatientEntry(doctorId, {
          patientName: demoName,
          gender: "女",
          age: 65,
        });
        const patientToken = data?.portal_token || data?.token;
        if (patientToken) updateProgress({ intakeToken: patientToken });
        queryClient.invalidateQueries({ queryKey: QK.patients(doctorId) });
        setReady(true);
      } catch {
        setReady(true);
      }
    })();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        padding: "32px 20px 16px",
      }}
    >
      <CheckCircleFill
        style={{ fontSize: 64, color: APP.primary, marginBottom: 16 }} // lint-ui-ignore: hero illustration
      />
      <div
        style={{
          fontSize: FONT.xl,
          fontWeight: 700,
          color: APP.text1,
          marginBottom: 8,
        }}
      >
        设置完成
      </div>
      <div
        style={{
          fontSize: FONT.main,
          color: APP.text3,
          textAlign: "center",
          lineHeight: 1.7,
          maxWidth: 280,
        }}
      >
        AI 已学会你的规则，现在试试看患者发来消息时 AI 如何帮你处理。
      </div>

      <div
        style={{
          marginTop: 24,
          width: "100%",
          padding: 16,
          backgroundColor: APP.surfaceAlt,
          borderRadius: RADIUS.md,
          border: `1px solid ${APP.border}`,
        }}
      >
        <div
          style={{ fontSize: FONT.md, fontWeight: 600, color: APP.text1, marginBottom: 4 }}
        >
          可选：体验患者端预问诊
        </div>
        <div
          style={{
            fontSize: FONT.sm,
            color: APP.text3,
            lineHeight: 1.6,
            marginBottom: 12,
          }}
        >
          以体验患者的身份填写预问诊，AI 会引用已有病历记录来辅助问诊
        </div>
        <Button
          size="small"
          disabled={!ready || !progress?.intakeToken}
          onClick={() => {
            const token = progress?.intakeToken;
            if (token) {
              window.open(`/patient?token=${token}`, "_blank");
            }
          }}
          style={{
            "--border-color": APP.primary,
            "--text-color": APP.primary,
          }}
        >
          体验患者端 →
        </Button>
      </div>
    </div>
  );
}

// ── Main Wizard ───────────────────────────────────────────────────────────────

export default function OnboardingWizard() {
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const { doctorId } = useDoctorStore();
  const api = useApi();
  const queryClient = useQueryClient();

  const stepParam = parseInt(searchParams.get("step") || "1", 10);
  const isDone = searchParams.get("step") === "done";

  const [progress, setProgress] = useState(() => getWizardProgress(doctorId));
  const [canAdvance, setCanAdvance] = useState(false);
  const [confirmSkipVisible, setConfirmSkipVisible] = useState(false);
  const [confirmRestartVisible, setConfirmRestartVisible] = useState(false);

  const step = isDone ? 0 : Math.max(1, Math.min(stepParam, TOTAL_STEPS));

  const updateProgress = useCallback(
    (patch) => {
      const updated = setWizardProgress(doctorId, patch);
      setProgress(updated);
      return updated;
    },
    [doctorId],
  );

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
      updateDoctorProfile(doctorId, { finished_onboarding: true }).catch(() => {});
      markAllReleasesSeen(doctorId);
      navigate(dp());
      seedDemo(doctorId)
        .then(() => queryClient.invalidateQueries())
        .catch(() => {});
    } else {
      goToStep(next);
    }
  }

  function handleSkip() {
    markWizardDone(doctorId, "skipped");
    updateDoctorProfile(doctorId, { finished_onboarding: true }).catch(() => {});
    markAllReleasesSeen(doctorId);
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

  function renderStepContent() {
    switch (step) {
      case 1:
        return (
          <Step1Content
            doctorId={doctorId}
            progress={progress}
            updateProgress={updateProgress}
            setCanAdvance={setCanAdvance}
            api={api}
          />
        );
      case 2:
        return <Step2Content progress={progress} setCanAdvance={setCanAdvance} />;
      case 3:
        return (
          <Step3Content
            doctorId={doctorId}
            progress={progress}
            updateProgress={updateProgress}
            setCanAdvance={setCanAdvance}
            api={api}
          />
        );
      default:
        return null;
    }
  }

  return (
    <div
      style={{
        height: "100%",
        display: "flex",
        flexDirection: "column",
        backgroundColor: APP.surfaceAlt,
        overflow: "hidden",
      }}
    >
      <SafeArea position="top" />

      {/* NavBar */}
      <NavBar
        onBack={step > 1 ? handleBack : undefined}
        backArrow={step > 1}
        style={{
          "--height": "44px",
          "--border-bottom": `0.5px solid ${APP.border}`,
          backgroundColor: APP.surface,
          flexShrink: 0,
        }}
      >
        {STEP_TITLES[step] || "引导"}
      </NavBar>

      {/* Progress steps */}
      <div
        style={{
          padding: "8px 16px 6px",
          backgroundColor: APP.surface,
          borderBottom: `0.5px solid ${APP.border}`,
          flexShrink: 0,
        }}
      >
        <Steps
          current={step - 1}
          style={{
            "--title-font-size": FONT.xs,
            "--description-font-size": FONT.xs,
            "--icon-size": "22px",
          }}
        >
          <Steps.Step title="添加规则" />
          <Steps.Step title="看AI用它" />
          <Steps.Step title="开始使用" />
        </Steps>
      </div>

      {/* Scrollable content */}
      <div style={{ flex: 1, overflowY: "auto", WebkitOverflowScrolling: "touch" }}>
        {renderStepContent()}
      </div>

      {/* Footer buttons */}
      <div
        style={{
          padding: "12px 16px",
          borderTop: `0.5px solid ${APP.border}`,
          backgroundColor: APP.surface,
          flexShrink: 0,
          display: "flex",
          flexDirection: "column",
          gap: 8,
        }}
      >
        <Button
          block
          color="primary"
          disabled={!canAdvance}
          onClick={handleAdvance}
          style={{ "--background-color": APP.primary, "--border-color": APP.primary }}
        >
          {step === TOTAL_STEPS ? "完成引导" : "下一步"}
        </Button>
        <div style={{ display: "flex", gap: 8 }}>
          <Button
            block
            onClick={() => setConfirmRestartVisible(true)}
            style={{ flex: 1 }}
          >
            重新开始
          </Button>
          <Button
            block
            onClick={() => setConfirmSkipVisible(true)}
            style={{ flex: 1 }}
          >
            跳过引导
          </Button>
        </div>
      </div>

      <SafeArea position="bottom" />

      {/* Skip confirm dialog */}
      <Dialog
        visible={confirmSkipVisible}
        title="跳过引导？"
        content="跳过后可以在「我的AI」页面重新体验引导。"
        closeOnMaskClick
        onClose={() => setConfirmSkipVisible(false)}
        actions={[
          [
            {
              key: "cancel",
              text: "取消",
              onClick: () => setConfirmSkipVisible(false),
            },
            {
              key: "confirm",
              text: "跳过",
              bold: true,
              danger: false,
              onClick: () => {
                setConfirmSkipVisible(false);
                handleSkip();
              },
            },
          ],
        ]}
      />

      {/* Restart confirm dialog */}
      <Dialog
        visible={confirmRestartVisible}
        title="重新开始？"
        content="当前进度将被清除，从第一步重新开始。"
        closeOnMaskClick
        onClose={() => setConfirmRestartVisible(false)}
        actions={[
          [
            {
              key: "cancel",
              text: "取消",
              onClick: () => setConfirmRestartVisible(false),
            },
            {
              key: "confirm",
              text: "重新开始",
              bold: true,
              onClick: () => {
                setConfirmRestartVisible(false);
                handleRestart();
              },
            },
          ],
        ]}
      />
    </div>
  );
}
