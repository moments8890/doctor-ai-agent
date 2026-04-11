/**
 * PersonaOnboardingSubpage — pick-your-style onboarding wizard.
 * Shows 3 scenarios one at a time, doctor picks a response style.
 * After all 3, shows summary of extracted rules.
 */
import { useState, useEffect, useRef } from "react";
import { Box, CircularProgress, Typography } from "@mui/material";
import CheckCircleOutlinedIcon from "@mui/icons-material/CheckCircleOutlined";
import { TYPE, COLOR, RADIUS } from "../../../theme";
import PageSkeleton from "../../../components/PageSkeleton";
import AppButton from "../../../components/AppButton";
import { useApi } from "../../../api/ApiContext";
import { useQueryClient } from "@tanstack/react-query";
import { QK } from "../../../lib/queryKeys";
import { useDoctorStore } from "../../../store/doctorStore";

const FIELD_LABELS = {
  reply_style: "回复风格",
  closing: "常用结尾语",
  structure: "回复结构",
  avoid: "回避内容",
  edits: "常见修改",
};

export default function PersonaOnboardingSubpage({ onBack, isMobile, onComplete }) {
  const api = useApi();
  const queryClient = useQueryClient();
  const { doctorId } = useDoctorStore();

  const [scenarios, setScenarios] = useState(null);
  const [loadError, setLoadError] = useState(null);
  const [step, setStep] = useState(0); // 0..N-1 = scenarios, N = summary
  const [picks, setPicks] = useState({}); // { scenario_id: option_id }
  const [extractedRules, setExtractedRules] = useState(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState(null);
  const confirmingRef = useRef(false);

  // Load scenarios on first render
  useEffect(() => {
    api.getOnboardingScenarios(doctorId)
      .then((data) => setScenarios(data.scenarios))
      .catch(() => setLoadError("加载失败，请重试"));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  if (loadError) {
    return (
      <PageSkeleton title="初始化人设" onBack={onBack} mobileView={isMobile}>
        <Box sx={{ px: 2, pt: 4, textAlign: "center" }}>
          <Typography sx={{ color: COLOR.danger, fontSize: TYPE.body.fontSize }}>{loadError}</Typography>
        </Box>
      </PageSkeleton>
    );
  }

  if (!scenarios) {
    return (
      <PageSkeleton title="初始化人设" onBack={onBack} mobileView={isMobile}>
        <Box sx={{ display: "flex", justifyContent: "center", pt: 6 }}>
          <CircularProgress size={32} />
        </Box>
      </PageSkeleton>
    );
  }

  const currentScenario = step < scenarios.length ? scenarios[step] : null;
  const isSummaryStep = step >= scenarios.length;

  // Compute extracted rules from picks for summary display
  function getRuleSummary() {
    if (!extractedRules) return [];
    const result = [];
    for (const [field, rules] of Object.entries(extractedRules)) {
      for (const rule of rules) {
        result.push({ field, text: rule.text });
      }
    }
    return result;
  }

  function handlePick(scenarioId, optionId) {
    const newPicks = { ...picks, [scenarioId]: optionId };
    setPicks(newPicks);

    if (step < scenarios.length - 1) {
      // Advance to next scenario
      setStep(step + 1);
    } else {
      // Last scenario picked — compute preview and go to summary
      const picksArr = Object.entries(newPicks).map(([scenario_id, option_id]) => ({ scenario_id, option_id }));
      // Local preview: gather traits from picks
      const preview = {};
      picksArr.forEach(({ scenario_id, option_id }) => {
        const scenario = scenarios.find((s) => s.id === scenario_id);
        if (!scenario) return;
        const option = scenario.options.find((o) => o.id === option_id);
        if (!option) return;
        Object.entries(option.traits || {}).forEach(([field, text]) => {
          if (!preview[field]) preview[field] = [];
          if (!preview[field].some((r) => r.text === text)) {
            preview[field].push({ text });
          }
        });
      });
      setExtractedRules(preview);
      setStep(scenarios.length);
    }
  }

  async function handleConfirm() {
    if (confirmingRef.current) return;
    confirmingRef.current = true;
    setSaving(true);
    setSaveError(null);
    try {
      const picksArr = Object.entries(picks).map(([scenario_id, option_id]) => ({ scenario_id, option_id }));
      await api.completeOnboarding(doctorId, picksArr);
      queryClient.invalidateQueries({ queryKey: QK.persona(doctorId) });
      if (onComplete) onComplete();
      else onBack();
    } catch {
      setSaveError("保存失败，请重试");
    } finally {
      confirmingRef.current = false;
      setSaving(false);
    }
  }

  // Summary step
  if (isSummaryStep) {
    const ruleSummary = getRuleSummary();
    return (
      <PageSkeleton title="确认人设" onBack={() => setStep(scenarios.length - 1)} mobileView={isMobile}>
        <Box sx={{ px: 2, py: 2, flex: 1, overflowY: "auto" }}>
          <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text4, mb: 2 }}>
            根据你的选择，AI将按以下偏好回复患者：
          </Typography>
          {ruleSummary.length === 0 ? (
            <Typography sx={{ color: COLOR.text4, fontSize: TYPE.body.fontSize }}>未检测到偏好，请返回重新选择</Typography>
          ) : (
            ruleSummary.map((r, i) => (
              <Box key={i} sx={{ display: "flex", gap: 1.25, mb: 1, alignItems: "flex-start" }}>
                <CheckCircleOutlinedIcon sx={{ fontSize: 18, color: COLOR.success, mt: 0.25, flexShrink: 0 }} />
                <Box>
                  <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4 }}>
                    {FIELD_LABELS[r.field] || r.field}
                  </Typography>
                  <Typography sx={{ fontSize: TYPE.body.fontSize, color: COLOR.text1 }}>{r.text}</Typography>
                </Box>
              </Box>
            ))
          )}
          {saveError && (
            <Typography sx={{ color: COLOR.danger, fontSize: TYPE.secondary.fontSize, mt: 1 }}>{saveError}</Typography>
          )}
        </Box>
        <Box sx={{ px: 2, pb: 3, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 1 }}>
          <AppButton variant="secondary" size="md" fullWidth onClick={() => setStep(scenarios.length - 1)} disabled={saving}>
            返回修改
          </AppButton>
          <AppButton variant="primary" size="md" fullWidth onClick={handleConfirm} loading={saving} loadingLabel="保存中…">
            确认开始
          </AppButton>
        </Box>
      </PageSkeleton>
    );
  }

  // Scenario step
  const selectedOption = picks[currentScenario.id];
  const progress = ((step) / scenarios.length) * 100;

  return (
    <PageSkeleton title={`${step + 1} / ${scenarios.length}`} onBack={step === 0 ? onBack : () => setStep(step - 1)} mobileView={isMobile}>
      <Box sx={{ px: 2, py: 1.5, flex: 1, overflowY: "auto" }}>
        {/* Progress bar */}
        <Box sx={{ height: 3, bgcolor: COLOR.surfaceAlt, borderRadius: 2, mb: 2, overflow: "hidden" }}>
          <Box sx={{ height: "100%", bgcolor: COLOR.primary, width: `${progress}%`, transition: "width 0.3s ease" }} />
        </Box>

        {/* Scenario header */}
        <Typography sx={{ fontSize: TYPE.heading.fontSize, fontWeight: 600, color: COLOR.text1, mb: 0.5 }}>
          {currentScenario.title}
        </Typography>
        <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text4, mb: 1.5 }}>
          {currentScenario.patient_info}
        </Typography>

        {/* Patient message */}
        <Box sx={{
          bgcolor: COLOR.surfaceAlt,
          borderRadius: RADIUS.md,
          p: 1.5,
          mb: 2,
          border: `0.5px solid ${COLOR.border}`,
        }}>
          <Typography sx={{ fontSize: TYPE.body.fontSize, color: COLOR.text2, lineHeight: 1.65 }}>
            {currentScenario.patient_message}
          </Typography>
        </Box>

        <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text4, mb: 1 }}>
          选择你更习惯的回复方式：
        </Typography>

        {/* Options */}
        {currentScenario.options.map((opt) => {
          const isSelected = selectedOption === opt.id;
          return (
            <Box
              key={opt.id}
              onClick={() => handlePick(currentScenario.id, opt.id)}
              sx={{
                mb: 1.25,
                p: 1.5,
                borderRadius: RADIUS.md,
                border: `1.5px solid ${isSelected ? COLOR.primary : COLOR.border}`,
                bgcolor: isSelected ? COLOR.primaryLight : COLOR.white,
                cursor: "pointer",
                transition: "border-color 0.15s, background-color 0.15s",
              }}
            >
              <Typography sx={{ fontSize: TYPE.body.fontSize, color: COLOR.text1, lineHeight: 1.65 }}>
                {opt.text}
              </Typography>
            </Box>
          );
        })}
      </Box>
    </PageSkeleton>
  );
}
