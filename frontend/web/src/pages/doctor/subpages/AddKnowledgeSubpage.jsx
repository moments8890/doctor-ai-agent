/**
 * AddKnowledgeSubpage — add knowledge via text input or file upload.
 *
 * Two entry paths:
 *   1. Text input — type content directly, saved with addKnowledgeItem()
 *   2. File upload — extract text from PDF/DOCX/TXT, preview & edit, then save
 */
import { useEffect, useState, useRef } from "react";
import { Alert, Box, CircularProgress, TextField, Typography } from "@mui/material";
import UploadFileOutlinedIcon from "@mui/icons-material/UploadFileOutlined";
import CameraAltOutlinedIcon from "@mui/icons-material/CameraAltOutlined";
import LinkOutlinedIcon from "@mui/icons-material/LinkOutlined";
import AutoFixHighOutlinedIcon from "@mui/icons-material/AutoFixHighOutlined";
import MicIcon from "@mui/icons-material/Mic";
import PageSkeleton from "../../../components/PageSkeleton";
import { SpotlightHint } from "../OnboardingWizard";
import BarButton from "../../../components/BarButton";
import AppButton from "../../../components/AppButton";
import SheetDialog from "../../../components/SheetDialog";
import VoiceInput, { isVoiceSupported } from "../../../components/VoiceInput";
import Toast, { useToast } from "../../../components/Toast";
import ConfirmDialog from "../../../components/ConfirmDialog";
import { useApi } from "../../../api/ApiContext";
import { TYPE, COLOR, RADIUS } from "../../../theme";
import { dp } from "../../../utils/doctorBasePath";
import { useAppNavigate } from "../../../hooks/useAppNavigate";
import { markOnboardingStep, ONBOARDING_STEP } from "../constants";
import {
  getPreferredOnboardingRule,
  resolveDiagnosisProofDestination,
  resolveReplyProofDestination,
} from "../onboardingProofs";

const PREFILL_URL = `${window.location.origin}/examples/pci-antiplatelet-guide.html`;
const PREFILL_TEXT = "LVB术后吻合口评估：术后复查荧光成像评估吻合口通畅性。警惕：运动时静脉压增加致静脉血返流→吻合口血栓。建议术后早期限制剧烈运动。吻合口狭窄征象：术侧头痛加重、认知改善后再次下降。出现上述征象需立即复查荧光成像。";
const PREFILL_FILE_NAME = "LVB术后护理与观察要点.jpg";
const PREFILL_FILE_TEXT = "LVB术后护理与观察要点\n\n术后24h内观察颈部切口有无渗血肿胀。术后1周避免剧烈转头和颈部过度活动。密切观察认知功能变化（记忆、情绪、行为），建议家属每日记录。术后常见头晕多为一过性，1-2周缓解。术后1月、3月、6月复查PET及脑淋巴MRI黑血序列评估淋巴引流效果。注意观察吻合口通畅性，如认知改善后再次下降需警惕吻合口狭窄或血栓。";

export default function AddKnowledgeSubpage({ doctorId, onBack, isMobile }) {
  const api = useApi();
  const { addKnowledgeItem, uploadKnowledgeExtract, uploadKnowledgeSave, processKnowledgeText, fetchKnowledgeUrl } = api;
  const navigate = useAppNavigate();
  const _params = new URLSearchParams(window.location.search);
  const onboardingMode = _params.get("onboarding") === "1";
  const wizardSource = _params.get("wizard") === "1" ? (_params.get("source") || "") : "";

  // ── Text input state ──
  const [content, setContent] = useState("");
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState("");

  // ── File upload state ──
  const fileInputRef = useRef(null);
  const cameraInputRef = useRef(null);
  const [uploading, setUploading] = useState(false);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [extractedText, setExtractedText] = useState("");
  const [editedText, setEditedText] = useState("");
  const [sourceFilename, setSourceFilename] = useState("");
  const [llmProcessed, setLlmProcessed] = useState(false);
  const [showVoice, setShowVoice] = useState(false);
  const [saving, setSaving] = useState(false);
  const [toast, showToast] = useToast();
  const [nextStepOpen, setNextStepOpen] = useState(false);
  const [savedRuleTitle, setSavedRuleTitle] = useState("");
  const [routingProof, setRoutingProof] = useState(false);

  // ── URL fetch state ──
  const [urlInput, setUrlInput] = useState("");
  const [fetchingUrl, setFetchingUrl] = useState(false);

  // ── Voice input state ──
  const [voiceRecording, setVoiceRecording] = useState(false);
  const voiceRecRef = useRef(null);
  const voiceTimerRef = useRef(null);
  const [voiceSeconds, setVoiceSeconds] = useState(0);

  // ── Source tab state ──
  const [sourceTab, setSourceTab] = useState(wizardSource || "text");

  // ── Cancel confirmation state ──
  const [showCancelConfirm, setShowCancelConfirm] = useState(false);

  // ── Manual text processing state ──
  const [processing, setProcessing] = useState(false);
  const [textPreviewOpen, setTextPreviewOpen] = useState(false);
  const [processedText, setProcessedText] = useState("");
  const [editedProcessedText, setEditedProcessedText] = useState("");
  const [textLlmProcessed, setTextLlmProcessed] = useState(false);

  useEffect(() => {
    if (!onboardingMode) return;
    const sourceParam = new URLSearchParams(window.location.search).get("source");
    if (sourceParam === "url") {
      setUrlInput((prev) => prev || PREFILL_URL);
    } else if (sourceParam === "text") {
      setContent((prev) => prev || PREFILL_TEXT);
    }
    // file source: no prefill needed — user uses "使用示例文件内容" button
  }, [onboardingMode]);

  function deriveRuleTitle(text) {
    const firstLine = (text || "").split("\n").find((line) => line.trim()) || "新规则";
    return firstLine.trim().slice(0, 18);
  }

  function handleKnowledgeSaved(text, knowledgeItemId = null) {
    const title = deriveRuleTitle(text);
    const params = new URLSearchParams(window.location.search);
    const wizardMode = params.get("wizard") === "1";
    const sourceType = params.get("source") || "text";

    if (wizardMode) {
      const idParam = knowledgeItemId ? `&savedId=${knowledgeItemId}` : "";
      navigate(`${dp("onboarding")}?step=2&saved=${sourceType}&savedTitle=${encodeURIComponent(title)}${idParam}`);
      return;
    }

    markOnboardingStep(doctorId, ONBOARDING_STEP.knowledge, {
      lastSavedRuleTitle: title,
      lastSavedRuleId: knowledgeItemId,
      lastSavedRuleAt: new Date().toISOString(),
    });
    if (onboardingMode) {
      setSavedRuleTitle(title);
      setNextStepOpen(true);
      return;
    }
    onBack();
  }

  // ── Text input submit ──
  async function handleAdd() {
    const trimmed = content.trim();
    if (!trimmed) return;

    // Long text → LLM process → preview
    if (trimmed.length >= 500) {
      setProcessing(true);
      setError("");
      try {
        const result = await processKnowledgeText(doctorId, trimmed);
        setProcessedText(result.processed_text);
        setEditedProcessedText(result.processed_text);
        setTextLlmProcessed(result.llm_processed);
        setTextPreviewOpen(true);
      } catch (e) {
        setError(e.message || "处理失败");
      } finally {
        setProcessing(false);
      }
      return;
    }

    // Short text → save directly
    setAdding(true);
    setError("");
    try {
      const result = await addKnowledgeItem(doctorId, trimmed);
      handleKnowledgeSaved(trimmed, result?.id || null);
    } catch (e) {
      setError(e.message || "添加失败");
    } finally {
      setAdding(false);
    }
  }

  // ── File upload flow ──
  function handleFileButtonClick() {
    fileInputRef.current?.click();
  }

  async function handleFileChange(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    // Reset input so same file can be re-selected
    e.target.value = "";

    setUploading(true);
    setError("");
    try {
      const result = await uploadKnowledgeExtract(doctorId, file);
      setSourceFilename(result.source_filename || file.name);
      setExtractedText(result.extracted_text || "");
      setEditedText(result.extracted_text || "");
      setLlmProcessed(!!result.llm_processed);
      setPreviewOpen(true);
    } catch (e) {
      setError(e.message || "文件提取失败");
    } finally {
      setUploading(false);
    }
  }

  async function handleFetchUrl() {
    const url = urlInput.trim();
    if (!url) return;
    setFetchingUrl(true);
    setError("");
    try {
      const result = await fetchKnowledgeUrl(doctorId, url);
      setSourceFilename(url);
      setExtractedText(result.extracted_text || "");
      setEditedText(result.extracted_text || "");
      setLlmProcessed(!!result.llm_processed);
      setPreviewOpen(true);
    } catch (e) {
      setError(e.message || "无法获取该网页");
    } finally {
      setFetchingUrl(false);
    }
  }

  async function handleSaveExtracted() {
    const trimmed = editedText.trim();
    if (!trimmed) return;
    setSaving(true);
    setError("");
    try {
      const isUrl = sourceFilename.startsWith("http://") || sourceFilename.startsWith("https://");
      const result = await uploadKnowledgeSave(doctorId, trimmed, isUrl ? "url" : sourceFilename, isUrl ? { sourceUrl: sourceFilename } : {});
      setPreviewOpen(false);
      showToast("已保存到知识库");
      setTimeout(() => handleKnowledgeSaved(trimmed, result?.id || null), 600);
    } catch (e) {
      setError(e.message || "保存失败");
    } finally {
      setSaving(false);
    }
  }

  function handleCancelPreview() {
    setPreviewOpen(false);
    setExtractedText("");
    setEditedText("");
    setSourceFilename("");
    setLlmProcessed(false);
  }

  async function handleSaveProcessedText() {
    const trimmed = editedProcessedText.trim();
    if (!trimmed) return;
    setSaving(true);
    setError("");
    try {
      const result = await addKnowledgeItem(doctorId, trimmed);
      setTextPreviewOpen(false);
      showToast("已保存到知识库");
      setTimeout(() => handleKnowledgeSaved(trimmed, result?.id || null), 600);
    } catch (e) {
      setError(e.message || "保存失败");
    } finally {
      setSaving(false);
    }
  }

  function handleCancelTextPreview() {
    setTextPreviewOpen(false);
    setProcessedText("");
    setEditedProcessedText("");
    setTextLlmProcessed(false);
  }

  async function handleOpenDiagnosisProof() {
    if (routingProof) return;
    setRoutingProof(true);
    try {
      const { preferredRuleId, preferredRuleTitle } = getPreferredOnboardingRule(doctorId, {
        preferredRuleTitle: savedRuleTitle || "",
      });
      const destination = await resolveDiagnosisProofDestination(api, doctorId, {
        preferredRuleId,
        preferredRuleTitle,
      });
      setNextStepOpen(false);
      navigate(destination);
    } finally {
      setRoutingProof(false);
    }
  }

  async function handleOpenReplyProof() {
    if (routingProof) return;
    setRoutingProof(true);
    try {
      const { preferredRuleId, preferredRuleTitle } = getPreferredOnboardingRule(doctorId, {
        preferredRuleTitle: savedRuleTitle || "",
      });
      const destination = await resolveReplyProofDestination(api, doctorId, {
        preferredRuleId,
        preferredRuleTitle,
      });
      setNextStepOpen(false);
      navigate(destination);
    } finally {
      setRoutingProof(false);
    }
  }

  function handleBack() {
    const hasWork = content.trim() || urlInput.trim() || previewOpen || textPreviewOpen;
    if (hasWork) {
      setShowCancelConfirm(true);
    } else {
      onBack();
    }
  }

  const formContent = (
    <Box sx={{ flex: 1, overflowY: "auto", p: 2 }}>
      {error && (
        <Alert severity="error" onClose={() => setError("")} sx={{ mb: 1.5 }}>
          {error}
        </Alert>
      )}

      {/* Hidden file inputs — must stay in DOM for refs */}
      <input
        ref={fileInputRef}
        type="file"
        accept=".pdf,.docx,.doc,.txt,image/jpeg,image/png,image/webp"
        style={{ display: "none" }}
        onChange={handleFileChange}
      />
      <input
        ref={cameraInputRef}
        type="file"
        accept="image/*"
        capture="environment"
        style={{ display: "none" }}
        onChange={handleFileChange}
      />

      {/* Source tab picker */}
      <Box sx={{ px: 2, pt: 1.5, pb: 1 }}>
        <Typography sx={{ fontSize: TYPE.secondary.fontSize, fontWeight: 600, color: COLOR.text2, mb: 1 }}>选择来源</Typography>
        <Box sx={{ display: "flex", gap: 1 }}>
          {[
            { key: "file", label: "上传文件", sub: "PDF/Word/图片", Icon: UploadFileOutlinedIcon, bg: COLOR.primaryLight, fg: COLOR.primary, wizardKey: "file" },
            { key: "url", label: "网页导入", sub: "粘贴网址", Icon: LinkOutlinedIcon, bg: COLOR.accentLight, fg: COLOR.accent, wizardKey: "url" },
            { key: "camera", label: "拍照", sub: "识别图片", Icon: CameraAltOutlinedIcon, bg: COLOR.warningLight, fg: COLOR.warning },
            { key: "text", label: "手动输入", sub: "自然语言", Icon: AutoFixHighOutlinedIcon, bg: COLOR.primaryLight, fg: COLOR.primary, wizardKey: "text" },
          ].map((tab) => {
            const isActive = sourceTab === tab.key;
            const isWizardTarget = wizardSource && tab.wizardKey === wizardSource;
            const card = (
              <Box onClick={() => {
                  setSourceTab(tab.key);
                  if (tab.key === "file") {
                    if (wizardSource === "file") {
                      // Wizard mode: skip file picker, show prefilled example directly
                      setSourceFilename(PREFILL_FILE_NAME);
                      setExtractedText(PREFILL_FILE_TEXT);
                      setEditedText(PREFILL_FILE_TEXT);
                      setLlmProcessed(true);
                      setPreviewOpen(true);
                    } else if (!uploading) {
                      fileInputRef.current?.click();
                    }
                  }
                  if (tab.key === "camera") cameraInputRef.current?.click();
                }}
                sx={{
                  flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 0.5, py: 1.5,
                  borderRadius: RADIUS.md, cursor: "pointer",
                  bgcolor: isActive ? tab.bg : COLOR.surface,
                  border: isActive ? `1.5px solid ${tab.fg}` : (isWizardTarget ? `1.5px dashed ${COLOR.primary}` : "1.5px solid transparent"),
                  "&:active": { opacity: 0.7 },
                }}>
                <Box sx={{ width: 32, height: 32, borderRadius: RADIUS.sm, bgcolor: isActive ? tab.fg : tab.bg, display: "flex", alignItems: "center", justifyContent: "center" }}>
                  {tab.key === "file" && uploading ? <CircularProgress size={16} sx={{ color: isActive ? COLOR.white : tab.fg }} /> : <tab.Icon sx={{ fontSize: 16, color: isActive ? COLOR.white : tab.fg }} />}
                </Box>
                <Typography sx={{ fontSize: TYPE.micro.fontSize, fontWeight: 500, color: isActive ? tab.fg : COLOR.text2 }}>{tab.label}</Typography>
              </Box>
            );
            return (
              <Box key={tab.key} sx={{ flex: 1, display: "flex" }}>
                {card}
              </Box>
            );
          })}
        </Box>
      </Box>

      {/* URL input — shown when "网页导入" selected */}
      {sourceTab === "url" && (
        <SpotlightHint active={wizardSource === "url"} hint="已预填示例网址，点击「获取」抓取内容">
        <Box sx={{ px: 2, pt: 0.5, pb: 1.5 }}>
          <Box sx={{ display: "flex", gap: 1, alignItems: "flex-start" }}>
            <TextField fullWidth size="small" placeholder="https://..." value={urlInput}
              onChange={(e) => setUrlInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") handleFetchUrl(); }}
              autoFocus
              sx={{ "& .MuiOutlinedInput-root": { borderRadius: RADIUS.md } }} />
            <AppButton variant="secondary" size="md" onClick={handleFetchUrl} disabled={fetchingUrl || !urlInput.trim()}
              sx={{ flexShrink: 0, display: "inline-flex", alignItems: "center", gap: 0.5 }}>
              {fetchingUrl ? <><CircularProgress size={16} sx={{ color: COLOR.primary }} /> 获取中…</> : <><LinkOutlinedIcon sx={{ fontSize: 18 }} /> 获取</>}
            </AppButton>
          </Box>
        </Box>
        </SpotlightHint>
      )}

      {/* Text input — shown when "手动输入" selected */}
      {sourceTab === "text" && (
        <SpotlightHint active={wizardSource === "text"} hint="已预填示例规则，直接点击底部「添加」保存">
        <Box sx={{ px: 2, mb: 2 }}>
          <TextField fullWidth multiline minRows={5} maxRows={10} size="small"
            placeholder="用自然语言描述您的临床经验、诊断规则、问诊策略等"
            value={content} onChange={(e) => setContent(e.target.value)} autoFocus
            sx={{ "& .MuiOutlinedInput-root": { borderRadius: RADIUS.md } }} />
          <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mt: 0.5 }}>
            <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4, flex: 1 }}>
              {content.length >= 500 ? "内容较长，保存时AI将自动整理" : "用自然语言描述，AI 会在相关场景中参考"}
            </Typography>
            <Typography sx={{ fontSize: TYPE.caption.fontSize, color: content.length > 3000 ? COLOR.danger : COLOR.text4, flexShrink: 0 }}>
              {content.length}/3000
            </Typography>
          </Box>
          {isVoiceSupported() && (
            showVoice ? (
              <Box sx={{ mt: 1 }}>
                <VoiceInput onResult={(text) => { setContent((prev) => prev ? prev + text : text); setShowVoice(false); }} onCancel={() => setShowVoice(false)} />
              </Box>
            ) : (
              <Box onClick={() => setShowVoice(true)}
                sx={{ mt: 1, display: "flex", alignItems: "center", justifyContent: "center", gap: 1,
                  py: 1.5, bgcolor: COLOR.surface, borderRadius: RADIUS.md, cursor: "pointer",
                  border: `0.5px solid ${COLOR.borderLight}`, "&:active": { bgcolor: COLOR.borderLight } }}>
                <MicIcon sx={{ fontSize: 18, color: COLOR.text4 }} />
                <Typography sx={{ fontSize: TYPE.body.fontSize, color: COLOR.text3 }}>按住说话</Typography>
              </Box>
            )
          )}
        </Box>
        </SpotlightHint>
      )}
    </Box>
  );

  return (
    <>
      <PageSkeleton
        title="添加知识"
        onBack={isMobile ? handleBack : undefined}
        isMobile={isMobile}
        listPane={
          <Box sx={{ display: "flex", flexDirection: "column", height: "100%" }}>
            <Box sx={{ flex: 1, overflow: "auto" }}>{formContent}</Box>
            <Box sx={{ px: 2, pt: 1.5, pb: "calc(12px + env(safe-area-inset-bottom))", bgcolor: COLOR.white, borderTop: `0.5px solid ${COLOR.border}` }}>
              <AppButton variant="primary" size="lg" fullWidth onClick={handleAdd} loading={adding || processing}
                disabled={sourceTab === "text" ? !content.trim() : false}>
                添加
              </AppButton>
            </Box>
          </Box>
        }
      />

      {/* File extract preview dialog */}
      <SheetDialog
        open={previewOpen}
        onClose={handleCancelPreview}
        title="文件内容预览"
        desktopMaxWidth={480}
        mobileMaxHeight="90vh"
        footer={
          <Box sx={{ display: "flex", gap: 1 }}>
            <AppButton variant="secondary" size="md" fullWidth onClick={handleCancelPreview}>
              取消
            </AppButton>
            <AppButton
              variant="primary"
              size="md"
              fullWidth
              onClick={handleSaveExtracted}
              disabled={!editedText.trim() || saving}
            >
              {saving ? <CircularProgress size={16} sx={{ color: COLOR.white }} /> : "保存"}
            </AppButton>
          </Box>
        }
      >
        {/* Source filename */}
        <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 1.5 }}>
          <UploadFileOutlinedIcon sx={{ fontSize: 16, color: COLOR.text4 }} />
          <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text3, flex: 1, minWidth: 0 }} noWrap>
            {sourceFilename}
          </Typography>
          {llmProcessed && (
            <Box
              sx={{
                display: "inline-flex",
                alignItems: "center",
                gap: 0.5,
                px: 1,
                py: 0.5,
                borderRadius: RADIUS.sm,
                bgcolor: COLOR.successLight,
                flexShrink: 0,
              }}
            >
              <AutoFixHighOutlinedIcon sx={{ fontSize: 12, color: COLOR.primary }} />
              <Typography sx={{ fontSize: 10, color: COLOR.primary, fontWeight: 500 }}>
                AI已整理
              </Typography>
            </Box>
          )}
        </Box>

        {/* Editable text area */}
        <TextField
          fullWidth
          multiline
          minRows={8}
          maxRows={16}
          size="small"
          value={editedText}
          onChange={(e) => setEditedText(e.target.value)}
          sx={{ "& .MuiOutlinedInput-root": { borderRadius: RADIUS.md } }}
        />

        {/* Character count */}
        <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4, mt: 0.5, textAlign: "right" }}>
          {editedText.length} 字
        </Typography>
      </SheetDialog>

      {/* Manual text LLM preview dialog */}
      <SheetDialog
        open={textPreviewOpen}
        onClose={handleCancelTextPreview}
        title="内容预览"
        desktopMaxWidth={480}
        mobileMaxHeight="90vh"
        footer={
          <Box sx={{ display: "flex", gap: 1 }}>
            <AppButton variant="secondary" size="md" fullWidth onClick={handleCancelTextPreview}>
              取消
            </AppButton>
            <AppButton
              variant="primary"
              size="md"
              fullWidth
              onClick={handleSaveProcessedText}
              disabled={!editedProcessedText.trim() || saving}
            >
              {saving ? <CircularProgress size={16} sx={{ color: COLOR.white }} /> : "保存"}
            </AppButton>
          </Box>
        }
      >
        {textLlmProcessed && (
          <Box
            sx={{
              display: "inline-flex", alignItems: "center", gap: 0.5,
              px: 1, py: 0.5, borderRadius: RADIUS.sm, bgcolor: COLOR.successLight,
              mb: 1.5,
            }}
          >
            <AutoFixHighOutlinedIcon sx={{ fontSize: 12, color: COLOR.primary }} />
            <Typography sx={{ fontSize: 10, color: COLOR.primary, fontWeight: 500 }}>
              AI已整理
            </Typography>
          </Box>
        )}
        <TextField
          fullWidth
          multiline
          minRows={8}
          maxRows={16}
          size="small"
          value={editedProcessedText}
          onChange={(e) => setEditedProcessedText(e.target.value)}
          sx={{ "& .MuiOutlinedInput-root": { borderRadius: RADIUS.md } }}
        />
        <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4, mt: 0.5, textAlign: "right" }}>
          {editedProcessedText.length} 字
        </Typography>
      </SheetDialog>

      <Toast message={toast} />

      <ConfirmDialog
        open={showCancelConfirm}
        onClose={() => setShowCancelConfirm(false)}
        onCancel={() => setShowCancelConfirm(false)}
        onConfirm={() => { setShowCancelConfirm(false); onBack(); }}
        title="确认离开？"
        message="未保存的内容将会丢失"
        confirmLabel="离开"
        cancelLabel="取消"
        confirmTone="danger"
      />

      <SheetDialog
        open={nextStepOpen}
        onClose={() => setNextStepOpen(false)}
        title="已保存到知识库"
        desktopMaxWidth={400}
        footer={
          <Box sx={{ display: "grid", gap: 1, gridTemplateColumns: "1fr" }}>
            <AppButton variant="primary" size="md" fullWidth onClick={handleOpenDiagnosisProof} disabled={routingProof}>
              看诊断示例
            </AppButton>
            <AppButton variant="secondary" size="md" fullWidth onClick={handleOpenReplyProof} disabled={routingProof}>
              看回复示例
            </AppButton>
            <AppButton variant="secondary" size="md" fullWidth onClick={() => navigate(dp())}>
              返回我的AI
            </AppButton>
          </Box>
        }
      >
        <Typography sx={{ fontSize: TYPE.heading.fontSize, fontWeight: 600, color: COLOR.text1 }}>
          {savedRuleTitle || "新规则"}
        </Typography>
        <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text3, mt: 0.5, lineHeight: 1.6 }}>
          接下来直接看两个确定会出现的场景：一个诊断审核示例，一个患者回复示例。
          医生第一次上手时不需要自己猜下一步。
        </Typography>
      </SheetDialog>
    </>
  );
}
