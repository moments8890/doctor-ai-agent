/**
 * @route /doctor/settings/knowledge/add
 *
 * AddKnowledgeSubpage v2 — add knowledge via text input or URL import.
 * antd-mobile only, no MUI.
 */
import { useState, useRef } from "react";
import { NavBar, Button, TextArea, Input, Toast, SpinLoading, Dialog, Tabs } from "antd-mobile";
import { LinkOutline } from "antd-mobile-icons";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { QK } from "../../../../lib/queryKeys";
import { useApi } from "../../../../api/ApiContext";
import { useDoctorStore } from "../../../../store/doctorStore";
import { APP, FONT, RADIUS } from "../../../theme";
import { pageContainer, navBarStyle, scrollable } from "../../../layouts";
import { ActionFooter } from "../../../components";


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
      <div style={pageContainer}>
        <NavBar
          onBack={() => setPreviewOpen(false)}
          style={navBarStyle}
        >
          内容预览
        </NavBar>

        <div style={{ ...scrollable, padding: "16px" }}>
          {sourceFilename && (
            <div style={{ fontSize: FONT.sm, color: APP.text4, marginBottom: 12, wordBreak: "break-all" }}>
              来源：{sourceFilename.length > 50 ? sourceFilename.slice(0, 50) + "…" : sourceFilename}
            </div>
          )}
          {error && (
            <div style={{ color: "var(--adm-color-danger)", fontSize: FONT.sm, marginBottom: 12 }}>
              {error}
            </div>
          )}
          <TextArea
            value={previewText}
            onChange={setPreviewText}
            autoSize={{ minRows: 10, maxRows: 24 }}
            style={{
              "--font-size": FONT.main,
              backgroundColor: APP.surface,
              borderRadius: RADIUS.lg,
              padding: "12px",
            }}
          />
          <div style={{ fontSize: FONT.sm, color: APP.text4, textAlign: "right", marginTop: 4 }}>
            {previewText.length} 字
          </div>
        </div>

        <ActionFooter>
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
        </ActionFooter>
      </div>
    );
  }

  return (
    <div style={pageContainer}>
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
        style={navBarStyle}
      >
        添加知识
      </NavBar>

      <div style={scrollable}>
        {/* Source tabs */}
        <Tabs
          activeKey={sourceTab}
          onChange={(key) => {
            setSourceTab(key);
            if (key === "file") fileInputRef.current?.click();
          }}
          style={{
            "--active-line-color": APP.primary,
            "--active-title-color": APP.primary,
            "--title-font-size": FONT.main,
            backgroundColor: APP.surface,
          }}
        >
          <Tabs.Tab title="手动输入" key="text" />
          <Tabs.Tab title="网页导入" key="url" />
          <Tabs.Tab title="上传文件" key="file" />
        </Tabs>

        <div style={{ padding: "16px" }}>
          {error && (
            <div
              style={{
                color: "var(--adm-color-danger)",
                fontSize: FONT.sm,
                marginBottom: 12,
                padding: "8px 12px",
                backgroundColor: APP.dangerLight,
                borderRadius: RADIUS.sm,
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
                  "--font-size": FONT.main,
                  "--placeholder-color": APP.text4,
                  backgroundColor: APP.surface,
                  borderRadius: RADIUS.lg,
                  padding: "12px",
                }}
              />
              {content.length >= 500 && (
                <div style={{ fontSize: FONT.sm, color: APP.text4, marginTop: 6 }}>
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
                  borderRadius: RADIUS.lg,
                  padding: "10px 12px",
                }}
              >
                <Input
                  placeholder="https://..."
                  value={urlInput}
                  onChange={setUrlInput}
                  onEnterPress={handleFetchUrl}
                  style={{ "--font-size": FONT.main }}
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
                fontSize: FONT.main,
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
        <ActionFooter>
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
        </ActionFooter>
      )}
    </div>
  );
}
