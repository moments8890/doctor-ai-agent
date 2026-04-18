/**
 * @route /doctor/settings/knowledge/add
 *
 * AddKnowledgeSubpage v2 — add knowledge via text input or URL import.
 * antd-mobile only, no MUI.
 */
import { useState, useRef } from "react";
import { NavBar, Button, TextArea, Input, Toast, SpinLoading, Dialog } from "antd-mobile";
import { LinkOutline } from "antd-mobile-icons";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { QK } from "../../../../lib/queryKeys";
import { useApi } from "../../../../api/ApiContext";
import { useDoctorStore } from "../../../../store/doctorStore";
import { APP } from "../../../theme";

const TABS = [
  { key: "text", label: "手动输入" },
  { key: "url",  label: "网页导入" },
  { key: "file", label: "上传文件" },
];

export default function AddKnowledgeSubpage() {
  const navigate = useNavigate();
  const api = useApi();
  const queryClient = useQueryClient();
  const { doctorId } = useDoctorStore();
  const fileInputRef = useRef(null);

  const [sourceTab, setSourceTab] = useState("text");
  const [content, setContent] = useState("");
  const [urlInput, setUrlInput] = useState("");

  const [adding, setAdding]         = useState(false);
  const [fetchingUrl, setFetchingUrl] = useState(false);
  const [uploading, setUploading]    = useState(false);
  const [processing, setProcessing]  = useState(false);
  const [saving, setSaving]          = useState(false);
  const [error, setError]            = useState("");

  // Preview state (file extract / long text)
  const [previewText, setPreviewText]   = useState("");
  const [previewOpen, setPreviewOpen]   = useState(false);
  const [sourceFilename, setSourceFilename] = useState("");

  const busy = adding || fetchingUrl || uploading || processing || saving;

  function handleBack() {
    const hasWork = content.trim() || urlInput.trim() || previewOpen;
    if (hasWork) {
      Dialog.confirm({
        title: "确认离开？",
        content: "未保存的内容将会丢失",
        confirmText: "离开",
        cancelText: "取消",
        onConfirm: () => navigate(-1),
      });
    } else {
      navigate(-1);
    }
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
        const result = await api.processKnowledgeText(doctorId, trimmed);
        setSourceFilename("手动输入");
        setPreviewText(result.processed_text || trimmed);
        setPreviewOpen(true);
      } catch (e) {
        setError(e.message || "处理失败");
      } finally {
        setProcessing(false);
      }
      return;
    }

    setAdding(true);
    setError("");
    try {
      await api.addKnowledgeItem(doctorId, trimmed);
      queryClient.invalidateQueries({ queryKey: QK.knowledge(doctorId) });
      Toast.show({ content: "已添加到知识库", position: "bottom" });
      navigate(-1);
    } catch (e) {
      setError(e.message || "添加失败");
    } finally {
      setAdding(false);
    }
  }

  // ── URL fetch ──
  async function handleFetchUrl() {
    const url = urlInput.trim();
    if (!url) return;
    setFetchingUrl(true);
    setError("");
    try {
      const result = await api.fetchKnowledgeUrl(doctorId, url);
      setSourceFilename(url);
      setPreviewText(result.extracted_text || "");
      setPreviewOpen(true);
    } catch (e) {
      setError(e.message || "无法获取该网页");
    } finally {
      setFetchingUrl(false);
    }
  }

  // ── File upload ──
  async function handleFileChange(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    e.target.value = "";
    setUploading(true);
    setError("");
    try {
      const result = await api.uploadKnowledgeExtract(doctorId, file);
      setSourceFilename(result.source_filename || file.name);
      setPreviewText(result.extracted_text || "");
      setPreviewOpen(true);
    } catch (e) {
      setError(e.message || "文件提取失败");
    } finally {
      setUploading(false);
    }
  }

  // ── Save from preview ──
  async function handleSavePreview() {
    const trimmed = previewText.trim();
    if (!trimmed) return;
    setSaving(true);
    setError("");
    try {
      const isUrl = sourceFilename.startsWith("http://") || sourceFilename.startsWith("https://");
      await api.uploadKnowledgeSave(
        doctorId,
        trimmed,
        isUrl ? "url" : sourceFilename,
        isUrl ? { sourceUrl: sourceFilename } : {}
      );
      queryClient.invalidateQueries({ queryKey: QK.knowledge(doctorId) });
      Toast.show({ content: "已保存到知识库", position: "bottom" });
      setPreviewOpen(false);
      navigate(-1);
    } catch (e) {
      setError(e.message || "保存失败");
    } finally {
      setSaving(false);
    }
  }

  // ── Preview modal ──
  if (previewOpen) {
    return (
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          height: "100%",
          backgroundColor: APP.surfaceAlt,
          overflow: "hidden",
        }}
      >
        <NavBar
          onBack={() => setPreviewOpen(false)}
          style={{
            "--height": "44px",
            "--border-bottom": `0.5px solid ${APP.border}`,
            backgroundColor: APP.surface,
            flexShrink: 0,
          }}
        >
          内容预览
        </NavBar>

        <div style={{ flex: 1, overflowY: "auto", padding: "16px" }}>
          {sourceFilename && (
            <div style={{ fontSize: 12, color: APP.text4, marginBottom: 12, wordBreak: "break-all" }}>
              来源：{sourceFilename.length > 50 ? sourceFilename.slice(0, 50) + "…" : sourceFilename}
            </div>
          )}
          {error && (
            <div style={{ color: "var(--adm-color-danger)", fontSize: 13, marginBottom: 12 }}>
              {error}
            </div>
          )}
          <TextArea
            value={previewText}
            onChange={setPreviewText}
            autoSize={{ minRows: 10, maxRows: 24 }}
            style={{
              "--font-size": "14px",
              backgroundColor: APP.surface,
              borderRadius: 8,
              padding: "12px",
              border: `0.5px solid ${APP.border}`,
            }}
          />
          <div style={{ fontSize: 12, color: APP.text4, textAlign: "right", marginTop: 4 }}>
            {previewText.length} 字
          </div>
        </div>

        <div
          style={{
            padding: "12px 16px",
            paddingBottom: "calc(12px + env(safe-area-inset-bottom, 0px))",
            backgroundColor: APP.surface,
            borderTop: `0.5px solid ${APP.border}`,
            display: "flex",
            gap: 8,
            flexShrink: 0,
          }}
        >
          <Button fill="outline" block onClick={() => setPreviewOpen(false)}>
            取消
          </Button>
          <Button
            color="primary"
            block
            loading={saving}
            disabled={!previewText.trim()}
            onClick={handleSavePreview}
          >
            保存
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100%",
        backgroundColor: APP.surfaceAlt,
        overflow: "hidden",
      }}
    >
      {/* Hidden file input */}
      <input
        ref={fileInputRef}
        type="file"
        accept=".pdf,.docx,.doc,.txt,image/jpeg,image/png,image/webp"
        style={{ display: "none" }}
        onChange={handleFileChange}
      />

      <NavBar
        onBack={handleBack}
        style={{
          "--height": "44px",
          "--border-bottom": `0.5px solid ${APP.border}`,
          backgroundColor: APP.surface,
          flexShrink: 0,
        }}
      >
        添加知识
      </NavBar>

      <div style={{ flex: 1, overflowY: "auto" }}>
        {/* Source tabs */}
        <div
          style={{
            display: "flex",
            backgroundColor: APP.surface,
            borderBottom: `0.5px solid ${APP.border}`,
          }}
        >
          {TABS.map((tab) => {
            const active = sourceTab === tab.key;
            return (
              <div
                key={tab.key}
                onClick={() => {
                  setSourceTab(tab.key);
                  if (tab.key === "file") fileInputRef.current?.click();
                }}
                style={{
                  flex: 1,
                  textAlign: "center",
                  padding: "10px 0",
                  fontSize: 14,
                  fontWeight: active ? 600 : 400,
                  color: active ? "#07C160" : APP.text3,
                  borderBottom: active ? "2px solid #07C160" : "2px solid transparent",
                  cursor: "pointer",
                  transition: "color 0.15s",
                }}
              >
                {tab.label}
              </div>
            );
          })}
        </div>

        <div style={{ padding: "16px" }}>
          {error && (
            <div
              style={{
                color: "var(--adm-color-danger)",
                fontSize: 13,
                marginBottom: 12,
                padding: "8px 12px",
                backgroundColor: "#fff0f0",
                borderRadius: 6,
              }}
            >
              {error}
            </div>
          )}

          {/* Text input */}
          {sourceTab === "text" && (
            <>
              <TextArea
                placeholder="用自然语言描述您的临床经验、诊断规则、问诊策略等"
                value={content}
                onChange={setContent}
                autoSize={{ minRows: 8, maxRows: 16 }}
                maxLength={3000}
                showCount
                style={{
                  "--font-size": "14px",
                  "--placeholder-color": APP.text4,
                  backgroundColor: APP.surface,
                  borderRadius: 8,
                  padding: "12px",
                  border: `0.5px solid ${APP.border}`,
                }}
              />
              {content.length >= 500 && (
                <div style={{ fontSize: 12, color: APP.text4, marginTop: 6 }}>
                  内容较长，保存时AI将自动整理
                </div>
              )}
            </>
          )}

          {/* URL input */}
          {sourceTab === "url" && (
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <div
                style={{
                  flex: 1,
                  backgroundColor: APP.surface,
                  border: `0.5px solid ${APP.border}`,
                  borderRadius: 8,
                  padding: "10px 12px",
                }}
              >
                <Input
                  placeholder="https://..."
                  value={urlInput}
                  onChange={setUrlInput}
                  onEnterPress={handleFetchUrl}
                  style={{ "--font-size": "14px" }}
                />
              </div>
              <Button
                color="default"
                size="middle"
                loading={fetchingUrl}
                disabled={!urlInput.trim() || fetchingUrl}
                onClick={handleFetchUrl}
              >
                获取
              </Button>
            </div>
          )}

          {/* File upload */}
          {sourceTab === "file" && (
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                justifyContent: "center",
                gap: 12,
                padding: "40px 0",
                color: APP.text4,
                fontSize: 14,
              }}
            >
              {uploading ? (
                <SpinLoading color="primary" />
              ) : (
                <>
                  <LinkOutline style={{ fontSize: 36, color: APP.text4 }} />
                  <div>支持 PDF / Word / 图片</div>
                  <Button
                    color="primary"
                    size="small"
                    onClick={() => fileInputRef.current?.click()}
                  >
                    选择文件
                  </Button>
                </>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Bottom action bar */}
      {(sourceTab === "text" || sourceTab === "url") && (
        <div
          style={{
            padding: "12px 16px",
            paddingBottom: "calc(12px + env(safe-area-inset-bottom, 0px))",
            backgroundColor: APP.surface,
            borderTop: `0.5px solid ${APP.border}`,
            flexShrink: 0,
          }}
        >
          {sourceTab === "text" && (
            <Button
              color="primary"
              block
              size="large"
              loading={busy}
              disabled={!content.trim() || busy}
              onClick={handleAdd}
            >
              添加
            </Button>
          )}
          {sourceTab === "url" && (
            <Button
              color="primary"
              block
              size="large"
              loading={fetchingUrl}
              disabled={!urlInput.trim() || fetchingUrl}
              onClick={handleFetchUrl}
            >
              获取内容
            </Button>
          )}
        </div>
      )}
    </div>
  );
}
