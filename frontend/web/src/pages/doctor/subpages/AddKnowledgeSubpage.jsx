/**
 * AddKnowledgeSubpage — add knowledge via text input or file upload.
 *
 * Two entry paths:
 *   1. Text input — type content directly, saved with addKnowledgeItem()
 *   2. File upload — extract text from PDF/DOCX/TXT, preview & edit, then save
 */
import { useState, useRef } from "react";
import { Alert, Box, CircularProgress, TextField, Typography } from "@mui/material";
import UploadFileOutlinedIcon from "@mui/icons-material/UploadFileOutlined";
import AutoFixHighOutlinedIcon from "@mui/icons-material/AutoFixHighOutlined";
import MicIcon from "@mui/icons-material/Mic";
import PageSkeleton from "../../../components/PageSkeleton";
import BarButton from "../../../components/BarButton";
import AppButton from "../../../components/AppButton";
import SheetDialog from "../../../components/SheetDialog";
import VoiceInput, { isVoiceSupported } from "../../../components/VoiceInput";
import { useApi } from "../../../api/ApiContext";
import { TYPE, COLOR } from "../../../theme";

export default function AddKnowledgeSubpage({ doctorId, onBack, isMobile }) {
  const { addKnowledgeItem, uploadKnowledgeExtract, uploadKnowledgeSave, processKnowledgeText } = useApi();

  // ── Text input state ──
  const [content, setContent] = useState("");
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState("");

  // ── File upload state ──
  const fileInputRef = useRef(null);
  const [uploading, setUploading] = useState(false);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [extractedText, setExtractedText] = useState("");
  const [editedText, setEditedText] = useState("");
  const [sourceFilename, setSourceFilename] = useState("");
  const [llmProcessed, setLlmProcessed] = useState(false);
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState(null);

  // ── Voice input state ──
  const [showVoice, setShowVoice] = useState(false);

  // ── Manual text processing state ──
  const [processing, setProcessing] = useState(false);
  const [textPreviewOpen, setTextPreviewOpen] = useState(false);
  const [processedText, setProcessedText] = useState("");
  const [editedProcessedText, setEditedProcessedText] = useState("");
  const [textLlmProcessed, setTextLlmProcessed] = useState(false);

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
      await addKnowledgeItem(doctorId, trimmed);
      onBack();
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

  async function handleSaveExtracted() {
    const trimmed = editedText.trim();
    if (!trimmed) return;
    setSaving(true);
    setError("");
    try {
      await uploadKnowledgeSave(doctorId, trimmed, sourceFilename);
      setPreviewOpen(false);
      showToast("已保存到知识库");
      setTimeout(() => onBack(), 600);
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
      await addKnowledgeItem(doctorId, trimmed);
      setTextPreviewOpen(false);
      showToast("已保存到知识库");
      setTimeout(() => onBack(), 600);
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
        <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4, mb: 1.2 }}>
          支持 PDF、Word、TXT 文件，AI 会自动提取并整理内容
        </Typography>
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.docx,.doc,.txt"
          style={{ display: "none" }}
          onChange={handleFileChange}
        />
        <AppButton
          variant="secondary"
          size="md"
          onClick={handleFileButtonClick}
          disabled={uploading}
          sx={{
            display: "inline-flex",
            alignItems: "center",
            gap: 0.8,
          }}
        >
          {uploading ? (
            <>
              <CircularProgress size={16} sx={{ color: COLOR.primary }} />
              正在提取文件内容…
            </>
          ) : (
            <>
              <UploadFileOutlinedIcon sx={{ fontSize: 18 }} />
              上传文件
            </>
          )}
        </AppButton>
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
          sx={{ "& .MuiOutlinedInput-root": { borderRadius: "6px" } }}
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
        <Box sx={{ display: "flex", alignItems: "center", gap: 0.8, mb: 1.5 }}>
          <UploadFileOutlinedIcon sx={{ fontSize: 16, color: COLOR.text4 }} />
          <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text3, flex: 1, minWidth: 0 }} noWrap>
            {sourceFilename}
          </Typography>
          {llmProcessed && (
            <Box
              sx={{
                display: "inline-flex",
                alignItems: "center",
                gap: 0.3,
                px: 0.8,
                py: 0.2,
                borderRadius: "3px",
                bgcolor: "#E8F5E9",
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
          sx={{ "& .MuiOutlinedInput-root": { borderRadius: "6px" } }}
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
              display: "inline-flex", alignItems: "center", gap: 0.3,
              px: 0.8, py: 0.2, borderRadius: "3px", bgcolor: "#E8F5E9",
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
          sx={{ "& .MuiOutlinedInput-root": { borderRadius: "6px" } }}
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
    </>
  );
}
