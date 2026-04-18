/**
 * @route /doctor/settings/persona-onboarding
 *
 * PersonaOnboardingSubpage v2 — pick-your-style onboarding wizard.
 * Shows scenarios one at a time, doctor picks a response style.
 * After all scenarios, shows summary of extracted rules.
 * antd-mobile only, no MUI.
 */
import { useState, useEffect, useRef } from "react";
import { NavBar, Button, SpinLoading, Toast } from "antd-mobile";
import { CheckOutline } from "antd-mobile-icons";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { QK } from "../../../../lib/queryKeys";
import { useApi } from "../../../../api/ApiContext";
import { useDoctorStore } from "../../../../store/doctorStore";
import { APP } from "../../../theme";

const FIELD_LABELS = {
  reply_style: "回复风格",
  closing: "常用结尾语",
  structure: "回复结构",
  avoid: "回避内容",
  edits: "常见修改",
};

export default function PersonaOnboardingSubpage({ onComplete }) {
  const navigate = useNavigate();
  const api = useApi();
  const queryClient = useQueryClient();
  const { doctorId } = useDoctorStore();

  const [scenarios, setScenarios] = useState(null);
  const [loadError, setLoadError] = useState(null);
  const [step, setStep] = useState(0);
  const [picks, setPicks] = useState({});
  const [extractedRules, setExtractedRules] = useState(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState(null);
  const confirmingRef = useRef(false);

  useEffect(() => {
    api.getOnboardingScenarios(doctorId)
      .then((data) => setScenarios(data.scenarios))
      .catch(() => setLoadError("加载失败，请重试"));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  function handlePick(scenarioId, optionId) {
    const newPicks = { ...picks, [scenarioId]: optionId };
    setPicks(newPicks);

    if (step < scenarios.length - 1) {
      setStep(step + 1);
    } else {
      // Last scenario — build preview and go to summary
      const preview = {};
      Object.entries(newPicks).forEach(([sid, oid]) => {
        const scenario = scenarios.find((s) => s.id === sid);
        if (!scenario) return;
        const option = scenario.options.find((o) => o.id === oid);
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
      Toast.show({ content: "风格已保存", position: "bottom" });
      if (onComplete) onComplete();
      else navigate(-1);
    } catch {
      setSaveError("保存失败，请重试");
    } finally {
      confirmingRef.current = false;
      setSaving(false);
    }
  }

  // ── Loading / error states ─────────────────────────────────────────

  if (loadError) {
    return (
      <div style={pageStyle}>
        <NavBar onBack={() => navigate(-1)} style={navStyle}>
          初始化风格
        </NavBar>
        <div style={{ padding: 24, textAlign: "center", color: "#FA5151", fontSize: "var(--adm-font-size-main)" }}>
          {loadError}
        </div>
      </div>
    );
  }

  if (!scenarios) {
    return (
      <div style={pageStyle}>
        <NavBar onBack={() => navigate(-1)} style={navStyle}>
          初始化风格
        </NavBar>
        <div style={{ display: "flex", justifyContent: "center", paddingTop: 48 }}>
          <SpinLoading color="primary" />
        </div>
      </div>
    );
  }

  const isSummaryStep = step >= scenarios.length;

  // ── Summary step ───────────────────────────────────────────────────

  if (isSummaryStep) {
    const ruleSummary = [];
    if (extractedRules) {
      for (const [field, rules] of Object.entries(extractedRules)) {
        for (const rule of rules) {
          ruleSummary.push({ field, text: rule.text });
        }
      }
    }

    return (
      <div style={pageStyle}>
        <NavBar
          onBack={() => setStep(scenarios.length - 1)}
          style={navStyle}
        >
          确认风格
        </NavBar>

        <div style={{ flex: 1, overflowY: "auto", padding: "16px" }}>
          <div style={{ fontSize: "var(--adm-font-size-sm)", color: APP.text4, marginBottom: 16 }}>
            根据你的选择，AI将按以下偏好回复患者：
          </div>

          {ruleSummary.length === 0 ? (
            <div style={{ color: APP.text4, fontSize: "var(--adm-font-size-main)" }}>
              未检测到偏好，请返回重新选择
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {ruleSummary.map((r, i) => (
                <div key={i} style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
                  <div style={{
                    width: 18, height: 18, borderRadius: 9,
                    background: "#07C160",
                    display: "flex", alignItems: "center", justifyContent: "center",
                    flexShrink: 0, marginTop: 2,
                    fontSize: 11, color: "#fff", fontWeight: 700,
                  }}>
                    <CheckOutline style={{ fontSize: 11 }} />
                  </div>
                  <div>
                    <div style={{ fontSize: "var(--adm-font-size-xs)", color: APP.text4 }}>
                      {FIELD_LABELS[r.field] || r.field}
                    </div>
                    <div style={{ fontSize: "var(--adm-font-size-main)", color: APP.text1 }}>
                      {r.text}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}

          {saveError && (
            <div style={{ color: "#FA5151", fontSize: "var(--adm-font-size-sm)", marginTop: 12 }}>
              {saveError}
            </div>
          )}
        </div>

        <div style={{ padding: "8px 16px 24px", display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
          <Button
            fill="outline"
            block
            onClick={() => setStep(scenarios.length - 1)}
            disabled={saving}
          >
            返回修改
          </Button>
          <Button
            color="primary"
            block
            loading={saving}
            onClick={handleConfirm}
          >
            确认开始
          </Button>
        </div>
      </div>
    );
  }

  // ── Scenario step ──────────────────────────────────────────────────

  const currentScenario = scenarios[step];
  const selectedOption = picks[currentScenario.id];
  const progress = (step / scenarios.length) * 100;

  return (
    <div style={pageStyle}>
      <NavBar
        onBack={step === 0 ? () => navigate(-1) : () => setStep(step - 1)}
        style={navStyle}
      >
        {step + 1} / {scenarios.length}
      </NavBar>

      <div style={{ flex: 1, overflowY: "auto", padding: "16px" }}>
        {/* Progress bar */}
        <div style={{ height: 3, background: APP.surfaceAlt, borderRadius: 2, marginBottom: 20, overflow: "hidden" }}>
          <div style={{
            height: "100%",
            background: "#07C160",
            width: `${progress}%`,
            transition: "width 0.3s ease",
          }} />
        </div>

        {/* Scenario title */}
        <div style={{ fontSize: "var(--adm-font-size-lg)", fontWeight: 600, color: APP.text1, marginBottom: 4 }}>
          {currentScenario.title}
        </div>

        {/* Patient info */}
        {currentScenario.patient_info && (
          <div style={{ fontSize: "var(--adm-font-size-sm)", color: APP.text4, marginBottom: 12 }}>
            {currentScenario.patient_info}
          </div>
        )}

        {/* Patient message */}
        <div style={{
          background: APP.surfaceAlt,
          borderRadius: 8,
          padding: "12px",
          marginBottom: 20,
          border: `0.5px solid ${APP.border}`,
          fontSize: "var(--adm-font-size-main)",
          color: APP.text2,
          lineHeight: 1.65,
        }}>
          {currentScenario.patient_message}
        </div>

        <div style={{ fontSize: "var(--adm-font-size-sm)", color: APP.text4, marginBottom: 8 }}>
          选择你更习惯的回复方式：
        </div>

        {/* Options */}
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {currentScenario.options.map((opt) => {
            const isSelected = selectedOption === opt.id;
            return (
              <div
                key={opt.id}
                onClick={() => handlePick(currentScenario.id, opt.id)}
                style={{
                  padding: "12px",
                  borderRadius: 8,
                  border: `1.5px solid ${isSelected ? "#07C160" : APP.border}`,
                  background: isSelected ? "#e7f8ee" : APP.surface,
                  cursor: "pointer",
                  fontSize: "var(--adm-font-size-main)",
                  color: APP.text1,
                  lineHeight: 1.65,
                  transition: "border-color 0.15s, background 0.15s",
                }}
              >
                {opt.text}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

const pageStyle = {
  height: "100%",
  display: "flex",
  flexDirection: "column",
  background: APP.surfaceAlt,
  overflow: "hidden",
};

const navStyle = {
  "--height": "44px",
  "--border-bottom": `0.5px solid ${APP.border}`,
  backgroundColor: APP.surface,
  flexShrink: 0,
};
