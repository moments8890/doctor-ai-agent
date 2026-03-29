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
import BarButton from "../../../components/BarButton";
import AppButton from "../../../components/AppButton";
import SheetDialog from "../../../components/SheetDialog";
import VoiceInput, { isVoiceSupported } from "../../../components/VoiceInput";
import { useApi } from "../../../api/ApiContext";
import { TYPE, COLOR, RADIUS } from "../../../theme";
import { useAppNavigate } from "../../../hooks/useAppNavigate";
import { markOnboardingStep, ONBOARDING_STEP } from "../constants";
import {
  getPreferredOnboardingRule,
  resolveDiagnosisProofDestination,
  resolveReplyProofDestination,
} from "../onboardingProofs";

const PREFILL_URL = "https://example.com/neurosurgery/post-op-headache-followup";
const PREFILL_TEXT = "术后头痛加重伴恶心呕吐时，优先排除迟发性颅内血肿或脑水肿，并尽快安排头颅CT。";
const PREFILL_FILE_NAME = "示例术后头痛处理单.jpg";
const PREFILL_FILE_TEXT = "术后头痛处理单\n\n开颅术后若出现头痛加重、恶心呕吐、肢体无力或意识改变，需优先排除迟发性颅内血肿、脑水肿或感染。建议尽快完成头颅CT，并结合生命体征与神经系统查体评估。";

export default function AddKnowledgeSubpage({ doctorId, onBack, isMobile }) {
  const api = useApi();
  const { addKnowledgeItem, uploadKnowledgeExtract, uploadKnowledgeSave, processKnowledgeText, fetchKnowledgeUrl } = api;
  const navigate = useAppNavigate();
  const onboardingMode = new URLSearchParams(window.location.search).get("onboarding") === "1";

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
  const [toast, setToast] = useState(null);
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

  // ── Manual text processing state ──
  const [processing, setProcessing] = useState(false);
  const [textPreviewOpen, setTextPreviewOpen] = useState(false);
  const [processedText, setProcessedText] = useState("");
  const [editedProcessedText, setEditedProcessedText] = useState("");
  const [textLlmProcessed, setTextLlmProcessed] = useState(false);

  useEffect(() => {
    if (!onboardingMode) return;
    setUrlInput((prev) => prev || PREFILL_URL);
    setContent((prev) => prev || PREFILL_TEXT);
  }, [onboardingMode]);

  function deriveRuleTitle(text) {
    const firstLine = (text || "").split("\n").find((line) => line.trim()) || "新规则";
    return firstLine.trim().slice(0, 18);
  }

  function handleKnowledgeSaved(text, knowledgeItemId = null) {
    const title = deriveRuleTitle(text);
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

  function showToast(msg) {
    setToast(msg);
    setTimeout(() => setToast(null), 2000);
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

  const formContent = (
    <Box sx={{ flex: 1, overflowY: "auto", p: 2 }}>
      {error && (
        <Alert severity="error" onClose={() => setError("")} sx={{ mb: 1.5 }}>
          {error}
        </Alert>
      )}

      {/* File upload section */}
      <Box sx={{ mb: 2.5 }}>
        <Typography sx={{ fontSize: TYPE.heading.fontSize, fontWeight: 600, color: COLOR.text1, mb: 1 }}>
          上传文件
        </Typography>
        <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4, mb: 1 }}>
          支持 PDF、Word、TXT 文件或拍照，AI 会自动提取并整理内容
        </Typography>
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
        <Box sx={{ display: "flex", gap: 1 }}>
          <AppButton
            variant="secondary"
            size="md"
            onClick={handleFileButtonClick}
            disabled={uploading}
            sx={{ display: "inline-flex", alignItems: "center", gap: 1 }}
          >
            {uploading ? (
              <>
                <CircularProgress size={16} sx={{ color: COLOR.primary }} />
                正在提取…
              </>
            ) : (
              <>
                <UploadFileOutlinedIcon sx={{ fontSize: 18 }} />
                上传文件
              </>
            )}
          </AppButton>
          <AppButton
            variant="secondary"
            size="md"
            onClick={() => cameraInputRef.current?.click()}
            disabled={uploading}
            sx={{ display: "inline-flex", alignItems: "center", gap: 1 }}
          >
            <CameraAltOutlinedIcon sx={{ fontSize: 18 }} />
            拍照
          </AppButton>
        </Box>
        {onboardingMode && (
          <Typography
            onClick={() => {
              setSourceFilename(PREFILL_FILE_NAME);
              setExtractedText(PREFILL_FILE_TEXT);
              setEditedText(PREFILL_FILE_TEXT);
              setLlmProcessed(true);
              setPreviewOpen(true);
            }}
            sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.primary, mt: 1, cursor: "pointer" }}
          >
            使用示例文件内容 ›
          </Typography>
        )}
      </Box>

      {/* URL fetch section */}
      <Box sx={{ mb: 2.5 }}>
        <Typography sx={{ fontSize: TYPE.heading.fontSize, fontWeight: 600, color: COLOR.text1, mb: 1 }}>
          从网页导入
        </Typography>
        <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4, mb: 1 }}>
          粘贴网址，AI 会自动提取并整理网页内容
        </Typography>
        <Box sx={{ display: "flex", gap: 1, alignItems: "flex-start" }}>
          <TextField
            fullWidth
            size="small"
            placeholder="https://..."
            value={urlInput}
            onChange={(e) => setUrlInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") handleFetchUrl(); }}
            sx={{ "& .MuiOutlinedInput-root": { borderRadius: RADIUS.md } }}
          />
          <AppButton
            variant="secondary"
            size="md"
            onClick={handleFetchUrl}
            disabled={fetchingUrl || !urlInput.trim()}
            sx={{ flexShrink: 0, display: "inline-flex", alignItems: "center", gap: 0.5 }}
          >
            {fetchingUrl ? (
              <>
                <CircularProgress size={16} sx={{ color: COLOR.primary }} />
                获取中…
              </>
            ) : (
              <>
                <LinkOutlinedIcon sx={{ fontSize: 18 }} />
                获取
              </>
            )}
          </AppButton>
        </Box>
      </Box>

      {/* Divider */}
      <Box sx={{ display: "flex", alignItems: "center", mb: 2.5 }}>
        <Box sx={{ flex: 1, height: "0.5px", bgcolor: COLOR.borderLight }} />
        <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4, px: 1.5 }}>或</Typography>
        <Box sx={{ flex: 1, height: "0.5px", bgcolor: COLOR.borderLight }} />
      </Box>

      {/* Text input */}
      <Box sx={{ mb: 2 }}>
        <Typography sx={{ fontSize: TYPE.heading.fontSize, fontWeight: 600, color: COLOR.text1, mb: 1 }}>
          手动输入
        </Typography>
        <TextField
          fullWidth
          multiline
          minRows={4}
          maxRows={8}
          size="small"
          placeholder="用自然语言描述您的临床经验、诊断规则、问诊策略等"
          value={content}
          onChange={(e) => setContent(e.target.value)}
          sx={{ "& .MuiOutlinedInput-root": { borderRadius: RADIUS.md } }}
        />
        <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mt: 0.5 }}>
          <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4, flex: 1 }}>
            {content.length >= 500 ? "内容较长，保存时AI将自动整理" : "用自然语言描述，AI 会在相关场景中参考"}
          </Typography>
          {isVoiceSupported() && (
            <Box
              onClick={() => setShowVoice(!showVoice)}
              sx={{
                width: 28, height: 28, borderRadius: "50%",
                display: "flex", alignItems: "center", justifyContent: "center",
                cursor: "pointer", flexShrink: 0, mx: 0.5,
                bgcolor: showVoice ? COLOR.primaryLight : COLOR.surface,
                "&:active": { opacity: 0.6 },
              }}
            >
              <MicIcon sx={{ fontSize: 16, color: showVoice ? COLOR.primary : COLOR.text4 }} />
            </Box>
          )}
          <Typography sx={{ fontSize: TYPE.caption.fontSize, color: content.length > 3000 ? COLOR.danger : COLOR.text4, flexShrink: 0 }}>
            {content.length}/3000
          </Typography>
        </Box>
        {showVoice && (
          <Box sx={{ mt: 1 }}>
            <VoiceInput
              onResult={(text) => {
                setContent((prev) => prev ? prev + text : text);
                setShowVoice(false);
              }}
              onCancel={() => setShowVoice(false)}
            />
          </Box>
        )}
      </Box>
    </Box>
  );

  return (
    <>
      <PageSkeleton
        title="添加知识"
        onBack={isMobile ? onBack : undefined}
        headerRight={
          <BarButton onClick={handleAdd} loading={adding || processing} disabled={!content.trim()}>
            添加
          </BarButton>
        }
        isMobile={isMobile}
        listPane={formContent}
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
            <AppButton variant="ghost" size="md" sx={{ flex: 1 }} onClick={handleCancelPreview}>
              取消
            </AppButton>
            <AppButton
              variant="primary"
              size="md"
              sx={{ flex: 2 }}
              onClick={handleSaveExtracted}
              disabled={!editedText.trim() || saving}
            >
              {saving ? <CircularProgress size={16} sx={{ color: "#fff" }} /> : "保存"}
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
            <AppButton variant="ghost" size="md" sx={{ flex: 1 }} onClick={handleCancelTextPreview}>
              取消
            </AppButton>
            <AppButton
              variant="primary"
              size="md"
              sx={{ flex: 2 }}
              onClick={handleSaveProcessedText}
              disabled={!editedProcessedText.trim() || saving}
            >
              {saving ? <CircularProgress size={16} sx={{ color: "#fff" }} /> : "保存"}
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

      {/* Toast */}
      {toast && (
        <Box
          sx={{
            position: "fixed",
            top: "20%",
            left: "50%",
            transform: "translateX(-50%)",
            bgcolor: "rgba(0,0,0,0.7)",
            color: "#fff",
            px: 3,
            py: 1.5,
            borderRadius: 2,
            fontSize: TYPE.body.fontSize,
            zIndex: 9999,
            pointerEvents: "none",
          }}
        >
          {toast}
        </Box>
      )}

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
            <AppButton variant="secondary" size="md" fullWidth onClick={() => navigate("/doctor")}>
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
