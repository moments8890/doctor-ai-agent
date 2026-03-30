// frontend/web/src/pages/doctor/OnboardingWizard.jsx
import { useState, useEffect, useCallback, useRef } from "react";
import { useSearchParams } from "react-router-dom";
import { Box, Typography, LinearProgress, TextField } from "@mui/material";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";
import { useAppNavigate } from "../../hooks/useAppNavigate";
import { useApi } from "../../api/ApiContext";
import { useDoctorStore } from "../../store/doctorStore";
import SubpageHeader from "../../components/SubpageHeader";
import AppButton from "../../components/AppButton";
import ListCard from "../../components/ListCard";
import IconBadge from "../../components/IconBadge";
import KnowledgeCard from "../../components/KnowledgeCard";
import ConfirmDialog from "../../components/ConfirmDialog";
import MsgAvatar from "../../components/MsgAvatar";
import NameAvatar from "../../components/NameAvatar";
import { TYPE, COLOR, RADIUS } from "../../theme";
import { ICON_BADGES } from "./constants";
import {
  getWizardProgress,
  setWizardProgress,
  markWizardDone,
  clearWizardProgress,
} from "./onboardingWizardState";

const TOTAL_STEPS = 6;

const STEP_TITLES = {
  1: "了解产品",
  2: "让AI学习你的知识",
  3: "看诊断审核",
  4: "看 AI 处理消息",
  5: "体验患者预问诊",
  6: "查看生成任务",
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

// ── Step 1: 了解产品 (intro) ──────────────────────────────────────────────────

function Step0Content({ needsName, localName, setLocalName, accessToken, setAuth, doctorId, api, setCanAdvance }) {
  const [nameSaved, setNameSaved] = useState(false);
  useEffect(() => { setCanAdvance(!needsName || nameSaved); }, [needsName, nameSaved]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <Box sx={{ px: 2, pt: 2 }}>
      {/* Product intro */}
      <Typography sx={{ fontSize: TYPE.title.fontSize, fontWeight: 700, color: COLOR.text1, mb: 2 }}>
        欢迎使用医师的 AI 协作助手
      </Typography>

      {/* Name setup — shown when doctor name is not yet set */}
      {needsName && !nameSaved && (
        <Box sx={{ p: 2, mb: 2, bgcolor: COLOR.white, borderRadius: RADIUS.lg, border: `1px solid ${COLOR.border}` }}>
          <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text2, mb: 1 }}>
            先告诉 AI 你是谁
          </Typography>
          <TextField
            label="您的姓名"
            placeholder="如：张伟"
            value={localName}
            onChange={(e) => setLocalName(e.target.value)}
            fullWidth
            size="small"
            autoFocus
          />
          <AppButton
            variant="primary" size="sm" fullWidth
            disabled={!localName.trim()}
            onClick={async () => {
              try {
                await api.updateDoctorProfile(doctorId, { name: localName.trim() });
                setAuth(doctorId, localName.trim(), accessToken);
                localStorage.setItem(`onboarding_setup_done:${doctorId}`, "1");
              } catch { /* allow continuing even on error */ }
              setNameSaved(true);
              setCanAdvance(true);
            }}
            sx={{ mt: 1.5 }}
          >
            确认
          </AppButton>
        </Box>
      )}

      {/* Scenario setup */}
      <Box sx={{ p: 2, bgcolor: COLOR.primaryLight, borderRadius: RADIUS.lg, border: `1px solid ${COLOR.primary}30`, mb: 2 }}>
        <Typography sx={{ fontSize: TYPE.heading.fontSize, fontWeight: 600, color: COLOR.text1, mb: 1 }}>
          引导场景
        </Typography>
        <Typography sx={{ fontSize: TYPE.body.fontSize, color: COLOR.text2, lineHeight: 1.8 }}>
          你刚为张阿姨完成了颈深淋巴-静脉分流术（LVB）治疗阿尔茨海默病。接下来她的家属会通过手机向你咨询术后问题 — 看看 AI 怎么帮你处理。
        </Typography>
      </Box>

      {/* Patient card */}
      <Box sx={{ p: 2, bgcolor: COLOR.white, borderRadius: RADIUS.lg, border: `1px solid ${COLOR.border}` }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, mb: 1.5 }}>
          <NameAvatar name="张阿姨" size={44} />
          <Box>
            <Typography sx={{ fontSize: TYPE.heading.fontSize, fontWeight: 600, color: COLOR.text1 }}>
              张阿姨
            </Typography>
            <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4 }}>
              女 · 65岁
            </Typography>
          </Box>
        </Box>
        <Box sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
          <Box sx={{ px: 1.5, py: 1, bgcolor: COLOR.surfaceAlt, borderRadius: RADIUS.md }}>
            <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4, mb: 0.25 }}>上次就诊</Typography>
            <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text1, lineHeight: 1.5 }}>
              双侧颈深LVB术后1周，右侧头痛2天
            </Typography>
          </Box>
          <Box sx={{ px: 1.5, py: 1, bgcolor: COLOR.surfaceAlt, borderRadius: RADIUS.md }}>
            <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4, mb: 0.25 }}>既往病史</Typography>
            <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text1, lineHeight: 1.5 }}>
              高血压10年（氨氯地平）· 糖尿病5年（二甲双胍）
            </Typography>
          </Box>
        </Box>
      </Box>

      {/* Workflow timeline */}
      <Box sx={{ mt: 2.5, mb: 1 }}>
        <Typography sx={{ fontSize: TYPE.heading.fontSize, fontWeight: 600, color: COLOR.text1, mb: 1.5 }}>你将体验：</Typography>
        {[
          "教 AI 你的 LVB 术后管理规则",
          "看 AI 用你的规则审核张阿姨的病情",
          "看 AI 帮你起草回复张阿姨的消息",
          "体验张阿姨看到的问诊界面",
          "查看 AI 自动生成的随访任务",
        ].map((text, i, arr) => (
          <Box key={i} sx={{ display: "flex", gap: 1.5 }}>
            {/* Timeline dot + connector */}
            <Box sx={{ display: "flex", flexDirection: "column", alignItems: "center", width: 24, flexShrink: 0 }}>
              <Box sx={{
                width: 24, height: 24, borderRadius: "50%",
                bgcolor: COLOR.primary, color: COLOR.white,
                display: "flex", alignItems: "center", justifyContent: "center",
                fontSize: TYPE.caption.fontSize, fontWeight: 700,
              }}>
                {i + 1}
              </Box>
              {i < arr.length - 1 && (
                <Box sx={{ width: 2, flex: 1, minHeight: 12, bgcolor: COLOR.primaryLight, mt: 0.5, mb: 0.5, borderRadius: 1 }} />
              )}
            </Box>
            <Typography sx={{ fontSize: TYPE.body.fontSize, color: COLOR.text1, lineHeight: 1.5, pt: 0.25, pb: 1.5 }}>
              {text}
            </Typography>
          </Box>
        ))}
      </Box>
    </Box>
  );
}

// ── Step 2: 教 AI 三种来源的知识 ──────────────────────────────────────────────

function Step1Content({ doctorId, progress, updateProgress, setCanAdvance, api }) {
  const navigate = useAppNavigate();
  const [searchParams] = useSearchParams();

  // Check for return from AddKnowledgeSubpage
  const savedSource = searchParams.get("saved");
  const savedTitle = searchParams.get("savedTitle");
  const savedId = searchParams.get("savedId");
  useEffect(() => {
    if (savedSource) {
      updateProgress((prev) => ({
        savedSources: [...new Set([...prev.savedSources, savedSource])],
        savedTitles: { ...(prev.savedTitles || {}), [savedSource]: savedTitle || "已添加" },
        savedIds: { ...(prev.savedIds || {}), ...(savedId ? { [savedSource]: savedId } : {}) },
        savedRuleTitle: savedTitle || prev.savedRuleTitle,
      }));
      // Clean the URL params
      const params = new URLSearchParams(window.location.search);
      params.delete("saved");
      params.delete("savedTitle");
      params.delete("savedId");
      window.history.replaceState({}, "", `${window.location.pathname}?${params.toString()}`);
    }
  }, [savedSource]); // eslint-disable-line react-hooks/exhaustive-deps

  const savedSources = progress.savedSources || [];
  const savedTitles = progress.savedTitles || {};
  const savedIds = progress.savedIds || {};
  const allDone = savedSources.includes("file") && savedSources.includes("url") && savedSources.includes("text");

  // When all 3 done, call ensureOnboardingExamples and enable advance
  useEffect(() => {
    if (!allDone) { setCanAdvance(false); return; }
    if (progress.proofData) { setCanAdvance(true); return; }
    // Call backend to create proof data
    const lastRuleId = progress.savedRuleIds?.[progress.savedRuleIds.length - 1];
    (api.ensureOnboardingExamples || (() => Promise.resolve(null)))(doctorId, {
      knowledgeItemId: lastRuleId,
    }).then((data) => {
      if (data) updateProgress({ proofData: data });
      setCanAdvance(true);
    }).catch(() => { setCanAdvance(true); });
  }, [allDone]); // eslint-disable-line react-hooks/exhaustive-deps

  const [hintDismissed, setHintDismissed] = useState(false);

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
        让 AI 学会你的诊疗方法 — 从三种来源各添加一条知识
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
                navigate(`/doctor/settings/knowledge/add?onboarding=1&source=${s.key}&wizard=1`);
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
        <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4, textAlign: "center" }}>
          {savedSources.length}/3 完成
        </Typography>
      </Box>

      {/* Show saved knowledge cards */}
      {savedSources.length > 0 && (
        <Box sx={{ mt: 2 }}>
          <Box sx={{ px: 2, py: 1 }}>
            <Typography sx={{ fontSize: TYPE.caption.fontSize, fontWeight: 600, color: COLOR.text3 }}>
              已添加的知识
            </Typography>
          </Box>
          <Box sx={{ bgcolor: COLOR.white, borderTop: `0.5px solid ${COLOR.border}`, borderBottom: `0.5px solid ${COLOR.border}` }}>
            {savedSources.map((key, idx) => (
              <KnowledgeCard
                key={key}
                title={savedTitles[key] || "已添加"}
                summary={key === "text" ? "优先排除迟发性颅内血肿或脑水肿" : key === "file" ? "血压持续≥160/100mmHg时加用氨氯地平" : "DAPT疗程至少12个月"}
                referenceCount={0}
                source={key === "file" ? "upload:文件" : key === "url" ? "url:" : "doctor"}
                date="刚添加"
                /* no onClick during onboarding — detail view is in a different route tree */
                sx={idx === savedSources.length - 1 ? { borderBottom: "none" } : {}}
              />
            ))}
          </Box>
        </Box>
      )}
    </>
  );
}

// ── Step 3: 看 AI 如何用于诊断审核 ────────────────────────────────────────────

function Step2Content({ doctorId, progress, updateProgress, setCanAdvance, api }) {
  const proofData = progress.proofData;
  const [suggestion, setSuggestion] = useState(null);
  const [loading, setLoading] = useState(true);
  const [confirmed, setConfirmed] = useState(false);
  const [confirming, setConfirming] = useState(false);

  const { getSuggestions, decideSuggestion, finalizeReview } = api;

  useEffect(() => {
    if (!proofData?.diagnosis_record_id) { setLoading(false); setCanAdvance(true); return; }
    getSuggestions(proofData.diagnosis_record_id, doctorId)
      .then((data) => {
        const items = Array.isArray(data) ? data : (data.suggestions || data.items || []);
        const first = items.find((s) => s.section === "differential") || items[0];
        setSuggestion(first || null);
      })
      .catch(() => {})
      .finally(() => { setLoading(false); setCanAdvance(true); });
  }, [proofData?.diagnosis_record_id, doctorId]); // eslint-disable-line react-hooks/exhaustive-deps

  async function handleConfirm() {
    if (confirming) return;
    // No real suggestion data (examples API unavailable) — just toggle UI
    if (!suggestion) {
      setConfirmed(true);
      setCanAdvance(true);
      return;
    }
    setConfirming(true);
    try {
      await decideSuggestion(suggestion.id, "accept");
      const allData = await getSuggestions(proofData.diagnosis_record_id, doctorId);
      const allItems = Array.isArray(allData) ? allData : (allData.suggestions || allData.items || []);
      for (const item of allItems) {
        if (item.id !== suggestion.id && !item.decision) {
          await decideSuggestion(item.id, "accept").catch(() => {});
        }
      }
      const result = await finalizeReview(proofData.diagnosis_record_id, doctorId);
      updateProgress({ followUpTaskIds: result?.follow_up_task_ids || [] });
      setConfirmed(true);
      setCanAdvance(true);
    } catch {
      setConfirmed(true);
      setCanAdvance(true);
    } finally {
      setConfirming(false);
    }
  }

  if (loading) {
    return <Box sx={{ p: 3, textAlign: "center" }}><Typography sx={{ color: COLOR.text4 }}>加载中...</Typography></Box>;
  }

  return (
    <>
      <ContextCard>
        你刚保存的规则会在诊断审核中被引用：
      </ContextCard>
      {(progress.savedTitles?.text || progress.savedRuleTitle) && (
        <Box sx={{ mx: 2, mt: 1, px: 2, py: 1.5, bgcolor: COLOR.white, borderRadius: RADIUS.md, border: `0.5px solid ${COLOR.border}` }}>
          <Typography sx={{ fontSize: TYPE.secondary.fontSize, fontWeight: 600, color: COLOR.text1, mb: 0.5 }}>
            {progress.savedTitles?.text || progress.savedRuleTitle}
          </Typography>
          <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text3, lineHeight: 1.6 }}>
            LVB术后吻合口评估：术后复查荧光成像评估吻合口通畅性。警惕：运动时静脉压增加致返流→吻合口血栓。吻合口狭窄征象：术侧头痛加重、认知改善后再次下降。
          </Typography>
        </Box>
      )}

      {/* Patient record */}
      <Box sx={{ mt: 1, bgcolor: COLOR.white, borderTop: `0.5px solid ${COLOR.border}`, borderBottom: `0.5px solid ${COLOR.border}` }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1, px: 2, py: 1.5, borderBottom: `0.5px solid ${COLOR.borderLight}` }}>
          <Typography sx={{ fontSize: TYPE.action.fontSize, fontWeight: 500 }}>张阿姨</Typography>
          <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4 }}>女 · 65岁</Typography>
          <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4, ml: "auto" }}>2026-03-27</Typography>
        </Box>
        {[
          { label: "主诉", value: "颈深淋巴-静脉分流术（LVB）后1周，右侧头痛2天" },
          { label: "现病史", value: "患者因阿尔茨海默病（MMSE 18分）于1周前行双侧颈深LVB手术，术中鼻黏膜ICG注射法显影满意，吻合淋巴管3根+淋巴结1枚。术后第3天开始右侧轻度头痛，昨日加重，伴轻度头晕。家属诉术后记忆较前有改善，能记起家人名字。无恶心呕吐，无肢体无力。" },
          { label: "既往史", value: "阿尔茨海默病2年，口服多奈哌齐5mg/日。高血压病史8年，口服氨氯地平5mg/日。无药物过敏史。" },
          { label: "体格", value: "神清，定向力部分保留。双侧颈部切口愈合可，右侧稍肿胀，无渗出。MMSE 20分（术前18分）。四肢肌力V级，病理征（-）。" },
          { label: "辅助", value: "术中荧光成像示双侧吻合口通畅，ICG可见淋巴管→静脉引流。术后颈部超声：切口区域少量积液，淋巴结未见异常肿大。" },
        ].map(({ label, value }) => (
          <Box key={label} sx={{ display: "flex", gap: 1.5, px: 2, py: 1, borderBottom: `0.5px solid ${COLOR.borderLight}`, "&:last-child": { borderBottom: "none" } }}>
            <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4, fontWeight: 500, flexShrink: 0, minWidth: 48 }}>{label}</Typography>
            <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text2, lineHeight: 1.6 }}>{value}</Typography>
          </Box>
        ))}
      </Box>

      {/* AI differentials */}
      <Box sx={{ px: 2, py: 1, bgcolor: COLOR.surfaceAlt, borderTop: `0.5px solid ${COLOR.border}`, borderBottom: `0.5px solid ${COLOR.border}` }}>
        <Typography sx={{ fontSize: TYPE.micro.fontSize, fontWeight: 600, color: COLOR.text4, letterSpacing: 0.3 }}>AI 鉴别诊断</Typography>
      </Box>
      <Box sx={{ bgcolor: COLOR.white, borderBottom: `0.5px solid ${COLOR.border}` }}>
        <SpotlightHint active={!confirmed}>
          <Box sx={{ display: "flex", alignItems: "flex-start", gap: 1.5, px: 2, py: 1.5, borderBottom: `0.5px solid ${COLOR.borderLight}` }}>
            <Box onClick={!confirmed ? handleConfirm : undefined}
              sx={{ width: 18, height: 18, borderRadius: "50%", flexShrink: 0, mt: 0.5, cursor: confirmed ? "default" : "pointer",
                ...(confirmed
                  ? { bgcolor: COLOR.primary, display: "flex", alignItems: "center", justifyContent: "center" }
                  : { border: `1.5px solid ${COLOR.border}` }),
              }}>
              {confirmed && <Typography sx={{ color: COLOR.white, fontSize: 11, lineHeight: 1 }}>✓</Typography>}
            </Box>
            <Box sx={{ flex: 1, minWidth: 0 }}>
              <Typography sx={{ fontSize: TYPE.action.fontSize, fontWeight: 500, color: COLOR.text1 }}>
                {suggestion?.content || "吻合口血栓或狭窄"}
              </Typography>
              <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text3, mt: 0.5, lineHeight: 1.6 }}>
                {suggestion ? (suggestion.detail || "").replace(/\[KB-\d+\]/g, "").trim() : "LVB术后1周出现术侧头痛加重，需警惕吻合口血栓或狭窄。建议复查荧光成像评估吻合口通畅性。"}
              </Typography>
              <Typography sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.danger, mt: 0.5 }}>
                引用: {progress.savedTitles?.text || progress.savedRuleTitle || "LVB术后吻合口评估"}
              </Typography>
            </Box>
          </Box>
        </SpotlightHint>
        <Box sx={{ display: "flex", alignItems: "flex-start", gap: 1.5, px: 2, py: 1.5, borderBottom: `0.5px solid ${COLOR.borderLight}` }}>
          <Box sx={{ width: 18, height: 18, borderRadius: "50%", border: `1.5px solid ${COLOR.border}`, flexShrink: 0, mt: 0.5 }} />
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Typography sx={{ fontSize: TYPE.action.fontSize, fontWeight: 500, color: COLOR.text1 }}>术后正常反应</Typography>
            <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text4, mt: 0.5 }}>LVB术后轻度头痛头晕多为一过性，1-2周可缓解。目前认知改善趋势良好（MMSE 18→20）。</Typography>
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

      {/* AI workup suggestions */}
      <Box sx={{ px: 2, py: 1, bgcolor: COLOR.surfaceAlt }}>
        <Typography sx={{ fontSize: TYPE.micro.fontSize, fontWeight: 600, color: COLOR.text4, letterSpacing: 0.3 }}>AI 检查建议</Typography>
      </Box>
      <Box sx={{ bgcolor: COLOR.white, borderBottom: `0.5px solid ${COLOR.border}` }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, px: 2, py: 1.5, borderBottom: `0.5px solid ${COLOR.borderLight}` }}>
          <Box sx={{ width: 18, height: 18, borderRadius: "50%", border: `1.5px solid ${COLOR.border}`, flexShrink: 0 }} />
          <Typography sx={{ fontSize: TYPE.action.fontSize, fontWeight: 500, color: COLOR.text1 }}>复查荧光成像评估吻合口通畅性</Typography>
        </Box>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, px: 2, py: 1.5 }}>
          <Box sx={{ width: 18, height: 18, borderRadius: "50%", border: `1.5px solid ${COLOR.border}`, flexShrink: 0 }} />
          <Typography sx={{ fontSize: TYPE.action.fontSize, fontWeight: 500, color: COLOR.text1 }}>颈部超声复查排除血肿增大</Typography>
        </Box>
      </Box>
    </>
  );
}

// ── Step 3: 看 AI 处理患者消息 (chat bubble view matching PatientDetail) ──────

const STEP3_MESSAGES = [
  { id: 1, role: "patient", content: "医生，我妈术后一周了，可以出门散步吗？脖子能转动吗？", time: "09:15" },
  { id: 2, role: "ai", content: "您好，根据LVB术后护理要点，术后1周应避免剧烈转头和颈部过度活动。可以在家中缓慢散步，但暂不建议外出远行。", time: "09:15", cited: "LVB术后护理与观察要点" },
  { id: 3, role: "patient", content: "好的。对了她最近说右边头有点疼，而且之前能记住的名字又记不住了", time: "14:20" },
  { id: 4, role: "ai", content: "已通知医生。术后头痛加重伴认知功能变化需要关注。", time: "14:20" },
  { id: 5, role: "patient", content: "她今天头更疼了，是不是手术出问题了？", time: "18:45" },
];
const STEP3_DRAFT_TEXT = "张阿姨家属您好，LVB术后出现头痛加重伴认知改善后再次下降，需要警惕吻合口狭窄或血栓。请尽快带张阿姨来医院复查荧光成像，评估吻合口通畅性。在此之前请让她卧床休息，避免剧烈活动。";
const STEP3_DRAFT_CITED = "LVB术后吻合口评估";

function ChatBubble({ role, content, time, cited }) {
  const isPatient = role === "patient";
  return (
    <Box sx={{ display: "flex", flexDirection: isPatient ? "row" : "row-reverse", alignItems: "flex-end", gap: 1, px: 1.5 }}>
      {isPatient ? (
        <NameAvatar name="张阿姨" size={36} />
      ) : (
        <MsgAvatar isUser={false} size={36} />
      )}
      <Box sx={{ maxWidth: "72%", display: "flex", flexDirection: "column", alignItems: isPatient ? "flex-start" : "flex-end" }}>
        <Box sx={{
          px: 1.5, py: 1,
          borderRadius: isPatient ? `${RADIUS.sm} ${RADIUS.sm} ${RADIUS.sm} 0` : `${RADIUS.sm} ${RADIUS.sm} 0 ${RADIUS.sm}`,
          bgcolor: COLOR.white,
          fontSize: TYPE.body.fontSize, whiteSpace: "pre-wrap", lineHeight: 1.7, color: COLOR.text1,
        }}>
          {role === "ai" && <Typography sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.primary, fontWeight: 500, mb: 0.5 }}>AI 自动回复</Typography>}
          {content}
          {cited && (
            <Typography sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.danger, mt: 0.5 }}>
              引用: {cited}
            </Typography>
          )}
        </Box>
        <Typography sx={{ mt: 0.5, px: 0.5, fontSize: TYPE.micro.fontSize, color: COLOR.text4 }}>{time}</Typography>
      </Box>
    </Box>
  );
}

function Step3Content({ doctorId, progress, setCanAdvance }) {
  const [confirmed, setConfirmed] = useState(false);
  const citedRuleTitle = STEP3_DRAFT_CITED || progress.savedTitles?.text || progress.savedRuleTitle;

  return (
    <>
      <ContextCard>AI 会根据你的知识库自动回复患者消息。紧急情况会升级给你确认。</ContextCard>
      <Box sx={{ mx: 2, mt: 1, bgcolor: COLOR.white, borderRadius: RADIUS.md, border: `0.5px solid ${COLOR.border}`, overflow: "hidden" }}>
        <Typography sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.text4, px: 2, pt: 1.5, pb: 0.5 }}>AI 在这段对话中引用了你保存的两条知识：</Typography>
        <Box sx={{ px: 2, py: 1, borderBottom: `0.5px solid ${COLOR.borderLight}` }}>
          <Typography sx={{ fontSize: TYPE.secondary.fontSize, fontWeight: 600, color: COLOR.primary, mb: 0.5 }}>LVB术后护理与观察要点</Typography>
          <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text3, lineHeight: 1.5 }}>
            术后1周避免剧烈转头。观察认知功能变化。术后1月、3月、6月复查PET及MRI黑血序列。
          </Typography>
          <Typography sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.primary, mt: 0.5 }}>→ 用于自动回复家属术后护理问题</Typography>
        </Box>
        <Box sx={{ px: 2, py: 1 }}>
          <Typography sx={{ fontSize: TYPE.secondary.fontSize, fontWeight: 600, color: COLOR.danger, mb: 0.5 }}>LVB术后吻合口评估</Typography>
          <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text3, lineHeight: 1.5 }}>
            警惕吻合口血栓：术侧头痛加重、认知改善后再次下降。需复查荧光成像评估通畅性。
          </Typography>
          <Typography sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.danger, mt: 0.5 }}>→ 识别术后并发症征象，升级给医生确认</Typography>
        </Box>
      </Box>

      {/* Chat bubble area — matches PatientDetail bubbleView */}
      <Box sx={{ flex: 1, py: 2, display: "flex", flexDirection: "column", gap: 1.5, bgcolor: COLOR.surfaceAlt }}>
        {STEP3_MESSAGES.map((msg) => (
          <ChatBubble key={msg.id} role={msg.role} content={msg.content} time={msg.time} cited={msg.cited} />
        ))}

        {/* AI draft card */}
        {!confirmed && (
          <Box sx={{ display: "flex", flexDirection: "row-reverse", alignItems: "flex-end", gap: 1, px: 1.5 }}>
            <MsgAvatar isUser={false} size={36} />
            <Box sx={{ maxWidth: "78%" }}>
              <Box sx={{
                bgcolor: COLOR.primaryLight, border: `1px solid ${COLOR.primary}30`,
                borderRadius: RADIUS.md, px: 2, py: 1.5,
              }}>
                <Typography sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.primary, fontWeight: 600, mb: 0.5 }}>
                  AI起草回复 · 待你确认
                </Typography>
                <Typography sx={{ fontSize: TYPE.body.fontSize, color: COLOR.text1, lineHeight: 1.7, whiteSpace: "pre-wrap" }}>
                  {STEP3_DRAFT_TEXT}
                </Typography>
                {citedRuleTitle && (
                  <Box sx={{ mt: 1 }}>
                    <Box component="span" sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.danger, bgcolor: COLOR.dangerLight, px: 1, py: 0.5, borderRadius: RADIUS.sm }}>
                      引用: {citedRuleTitle}
                    </Box>
                  </Box>
                )}
                <Box sx={{ display: "flex", justifyContent: "flex-end", gap: 2, mt: 1.5, pt: 1, borderTop: `0.5px solid ${COLOR.primary}20` }}>
                  <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text4 }}>
                    修改
                  </Typography>
                  <Typography
                    onClick={() => { setConfirmed(true); setCanAdvance(true); }}
                    sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.primary, fontWeight: 600, cursor: "pointer", "&:active": { opacity: 0.5 } }}
                  >
                    确认发送 ›
                  </Typography>
                </Box>
              </Box>
            </Box>
          </Box>
        )}

        {/* Sent confirmation */}
        {confirmed && (
          <Box sx={{ display: "flex", flexDirection: "row-reverse", alignItems: "flex-end", gap: 1, px: 1.5 }}>
            <MsgAvatar isUser={true} size={36} />
            <Box sx={{ maxWidth: "72%", display: "flex", flexDirection: "column", alignItems: "flex-end" }}>
              <Box sx={{
                px: 1.5, py: 1, borderRadius: `${RADIUS.sm} ${RADIUS.sm} 0 ${RADIUS.sm}`,
                bgcolor: COLOR.wechatGreen, fontSize: TYPE.body.fontSize, whiteSpace: "pre-wrap", lineHeight: 1.7, color: COLOR.text1,
              }}>
                {STEP3_DRAFT_TEXT}
              </Box>
              <Typography sx={{ mt: 0.5, px: 0.5, fontSize: TYPE.micro.fontSize, color: COLOR.primary, fontWeight: 600 }}>
                ✓ 已发送
              </Typography>
            </Box>
          </Box>
        )}
      </Box>

      {/* Hint below chat */}
      {!confirmed && (
        <Box sx={{ px: 2, py: 0.5 }}>
          <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.primary, lineHeight: 1.5 }}>
            紧急消息需要医生确认后才发送
          </Typography>
        </Box>
      )}
    </>
  );
}

// ── Step 4: 体验患者预问诊 (embeds real patient interview with LLM) ───────────

function Step4Content({ doctorId, setCanAdvance, api }) {
  const [ready, setReady] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    setCanAdvance(true); // Always advanceable — this is a demo step
    // Create a patient entry and store the token so the real patient page can auth
    (async () => {
      try {
        // Use unique name to avoid resuming old interview sessions
        const demoName = `体验患者${Date.now().toString(36).slice(-4)}`;
        const data = await api.createOnboardingPatientEntry(doctorId, { patientName: demoName, gender: "女", age: 65 });
        const patientToken = data?.portal_token || data?.token;
        if (patientToken) {
          // Save token for the patient iframe to pick up
          const prevToken = localStorage.getItem("patient_portal_token");
          localStorage.setItem("patient_portal_token", patientToken);
          localStorage.setItem("_wizard_prev_patient_token", prevToken || "");
          setReady(true);
        } else {
          setReady(true); // Fall back to mock
        }
      } catch {
        setReady(true); // Fall back to mock
      }
    })();
    return () => {
      // Restore previous patient token on unmount
      const prev = localStorage.getItem("_wizard_prev_patient_token");
      if (prev) {
        localStorage.setItem("patient_portal_token", prev);
      } else {
        localStorage.removeItem("patient_portal_token");
      }
      localStorage.removeItem("_wizard_prev_patient_token");
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const starterSuggestions = "最近记性变差了,头痛头晕好几天了,脖子伤口有点肿,走路不太稳,经常忘记吃药";
  const basePath = ready && localStorage.getItem("patient_portal_token")
    ? "/patient/records/interview"
    : "/debug/patient/records/interview";
  const iframeSrc = `${basePath}?starter_suggestions=${encodeURIComponent(starterSuggestions)}`;

  return (
    <>
      <ContextCard>下面是患者看到的预问诊界面 — 点击症状开始，或自己输入</ContextCard>

      <Box sx={{
        mx: 2, mb: 1,
        border: `2px solid ${COLOR.border}`,
        borderRadius: RADIUS.lg,
        overflow: "hidden",
        height: "calc(100vh - 440px)",
        minHeight: 240,
      }}>
        {ready ? (
          <Box
            component="iframe"
            src={iframeSrc}
            sx={{ width: "100%", height: "100%", border: "none" }}
          />
        ) : (
          <Box sx={{ p: 3, textAlign: "center" }}>
            <Typography sx={{ color: COLOR.text4 }}>准备中...</Typography>
          </Box>
        )}
      </Box>
    </>
  );
}

// ── Step 5: 查看患者详情 — shows the complete result of onboarding ───────────

function Step5Content({ setCanAdvance }) {
  useEffect(() => { setCanAdvance(true); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <>
      <ContextCard>
        这就是你日常使用的患者详情页。病历、消息、待办都在这里 — 浏览一下，然后完成引导。
      </ContextCard>

      {/* Static patient header */}
      <Box sx={{ bgcolor: COLOR.white, borderBottom: `0.5px solid ${COLOR.border}`, mt: 1 }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, px: 2, py: 1.5 }}>
          <NameAvatar name="张阿姨" size={44} />
          <Box sx={{ flex: 1 }}>
            <Typography sx={{ fontSize: TYPE.heading.fontSize, fontWeight: 600, color: COLOR.text1 }}>张阿姨</Typography>
            <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4 }}>女 · 65岁</Typography>
          </Box>
        </Box>
        {/* Stats row */}
        <Box sx={{ display: "flex", px: 2, py: 1, gap: 2, borderTop: `0.5px solid ${COLOR.borderLight}` }}>
          {[
            { label: "门诊", value: "1" },
            { label: "检验", value: "0" },
            { label: "影像", value: "1" },
            { label: "最近", value: "今天" },
          ].map((s) => (
            <Box key={s.label} sx={{ textAlign: "center", flex: 1 }}>
              <Typography sx={{ fontSize: TYPE.heading.fontSize, fontWeight: 600, color: s.value === "0" ? COLOR.text4 : COLOR.text1 }}>{s.value}</Typography>
              <Typography sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.text4 }}>{s.label}</Typography>
            </Box>
          ))}
        </Box>
      </Box>

      {/* Patient messages */}
      <ListCard
        avatar={<IconBadge config={ICON_BADGES.followup} />}
        title="患者消息"
        subtitle="查看聊天记录"
        chevron
        sx={{ mt: 1 }}
      />

      {/* Medical record */}
      <Box sx={{ mt: 1, bgcolor: COLOR.white, borderTop: `0.5px solid ${COLOR.border}`, borderBottom: `0.5px solid ${COLOR.border}` }}>
        <Box sx={{ px: 2, pt: 1.5, pb: 1 }}>
          <Typography sx={{ fontSize: TYPE.heading.fontSize, fontWeight: 600, color: COLOR.text2 }}>病历记录</Typography>
        </Box>
        <Box sx={{ px: 2, pb: 1.5 }}>
          {/* Record card */}
          <Box sx={{ p: 1.5, bgcolor: COLOR.surfaceAlt, borderRadius: RADIUS.md, mb: 1 }}>
            <Box sx={{ display: "flex", justifyContent: "space-between", mb: 0.5 }}>
              <Typography sx={{ fontSize: TYPE.body.fontSize, fontWeight: 500, color: COLOR.text1 }}>LVB术后复查</Typography>
              <Typography sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.text4 }}>今天</Typography>
            </Box>
            <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text3, lineHeight: 1.5 }}>
              主诉：双侧颈深LVB术后1周，右侧头痛2天
            </Typography>
            <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text3, lineHeight: 1.5, mt: 0.5 }}>
              既往：高血压10年（氨氯地平）· 糖尿病5年（二甲双胍）
            </Typography>
            <Box sx={{ display: "flex", gap: 0.5, mt: 1 }}>
              <Box sx={{ px: 1, py: 0.25, bgcolor: COLOR.primaryLight, borderRadius: RADIUS.sm, fontSize: TYPE.micro.fontSize, color: COLOR.primary }}>
                AI已审核
              </Box>
              <Box sx={{ px: 1, py: 0.25, bgcolor: COLOR.warningLight, borderRadius: RADIUS.sm, fontSize: TYPE.micro.fontSize, color: COLOR.amberText }}>
                随访中
              </Box>
            </Box>
          </Box>
        </Box>
      </Box>

      {/* Follow-up tasks */}
      <Box sx={{ mt: 1, bgcolor: COLOR.white, borderTop: `0.5px solid ${COLOR.border}`, borderBottom: `0.5px solid ${COLOR.border}` }}>
        <Box sx={{ px: 2, pt: 1.5, pb: 1 }}>
          <Typography sx={{ fontSize: TYPE.heading.fontSize, fontWeight: 600, color: COLOR.text2 }}>随访任务</Typography>
        </Box>
        {[
          { title: "血压复测", tag: "待完成", tagColor: COLOR.warning, tagBg: COLOR.warningLight },
          { title: "术后1周复查CT", tag: "待完成", tagColor: COLOR.warning, tagBg: COLOR.warningLight },
          { title: "复查颈动脉超声", tag: "待完成", tagColor: COLOR.warning, tagBg: COLOR.warningLight },
        ].map((t) => (
          <Box key={t.title} sx={{ px: 2, py: 1.5, borderBottom: `0.5px solid ${COLOR.borderLight}`, display: "flex", alignItems: "center" }}>
            <Typography sx={{ flex: 1, fontSize: TYPE.body.fontSize, color: COLOR.text1 }}>{t.title}</Typography>
            <Box sx={{ px: 1, py: 0.25, bgcolor: t.tagBg, color: t.tagColor, borderRadius: "999px", fontSize: 11, fontWeight: 600 }}>
              {t.tag}
            </Box>
          </Box>
        ))}
      </Box>
    </>
  );
}

// ── Completion Screen ─────────────────────────────────────────────────────────

function CompletionScreen() {
  const navigate = useAppNavigate();

  return (
    <Box sx={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", minHeight: "60vh", p: 3 }}>
      <CheckCircleOutlineIcon sx={{ fontSize: 48, color: COLOR.primary, mb: 2 }} />
      <Typography sx={{ fontSize: TYPE.title.fontSize, fontWeight: 600, color: COLOR.text1 }}>
        设置完成，开始使用
      </Typography>
      <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text3, mt: 1, textAlign: "center", lineHeight: 1.6 }}>
        你的 AI 已学会你的诊疗方法，可以开始处理患者消息了
      </Typography>
      <AppButton
        variant="primary" size="md"
        onClick={() => navigate("/doctor")}
        sx={{ mt: 3, minWidth: 200 }}
      >
        进入工作台
      </AppButton>
      {/* Next step: share QR with patients */}
      <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4, mt: 3, textAlign: "center", lineHeight: 1.6 }}>
        下一步：在「我的AI」页面分享预问诊码给患者，即可开始接收问诊
      </Typography>
      <Typography sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.text4, mt: 1, textAlign: "center" }}>
        引导中的示例数据会在工作台中显示，可随时在设置中清理
      </Typography>
    </Box>
  );
}

// ── Main Wizard ───────────────────────────────────────────────────────────────

export default function OnboardingWizard() {
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useAppNavigate();
  const { doctorId, doctorName, accessToken, setAuth } = useDoctorStore();
  const api = useApi();
  const [localName, setLocalName] = useState("");
  const needsName = !doctorName || doctorName === doctorId;

  const stepParam = parseInt(searchParams.get("step") || "1", 10);
  const isDone = searchParams.get("step") === "done";

  // Load persisted progress
  const [progress, setProgress] = useState(() => getWizardProgress(doctorId));
  const [canAdvance, setCanAdvance] = useState(false);

  // Current step: use URL param, but don't go below persisted progress
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
      setSearchParams({ step: "done" }, { replace: true });
    } else {
      goToStep(next);
    }
  }

  const [confirmSkip, setConfirmSkip] = useState(false);
  const [confirmRestart, setConfirmRestart] = useState(false);

  function handleSkip() {
    markWizardDone(doctorId, "skipped");
    navigate("/doctor");
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
    navigate("/doctor");
    return null;
  }

  // Step content renderer
  function renderStep() {
    switch (step) {
      case 1: return <Step0Content needsName={needsName} localName={localName} setLocalName={setLocalName} accessToken={accessToken} setAuth={setAuth} doctorId={doctorId} api={api} setCanAdvance={setCanAdvance} />;
      case 2: return <Step1Content doctorId={doctorId} progress={progress} updateProgress={updateProgress} setCanAdvance={setCanAdvance} api={api} />;
      case 3: return <Step2Content doctorId={doctorId} progress={progress} updateProgress={updateProgress} setCanAdvance={setCanAdvance} api={api} />;
      case 4: return <Step3Content doctorId={doctorId} progress={progress} setCanAdvance={setCanAdvance} />;
      case 5: return <Step4Content doctorId={doctorId} setCanAdvance={setCanAdvance} api={api} />;
      case 6: return <Step5Content setCanAdvance={setCanAdvance} />;
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
