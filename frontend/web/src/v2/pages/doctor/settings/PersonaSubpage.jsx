/**
 * @route /doctor/settings/persona
 *
 * PersonaSubpage v2 — edit AI persona free-text summary.
 * antd-mobile only, no MUI.
 */
import { useState, useEffect, useMemo } from "react";
import { SafeArea, NavBar, TextArea, Button, Toast } from "antd-mobile";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { QK } from "../../../../lib/queryKeys";
import { useApi } from "../../../../api/ApiContext";
import { usePersona } from "../../../../lib/doctorQueries";
import { useDoctorStore } from "../../../../store/doctorStore";
import { APP, FONT, RADIUS } from "../../../theme";
import { pageContainer, navBarStyle, scrollable } from "../../../layouts";
import { LoadingCenter, AiDisclaimer } from "../../../components";
import SubpageBackHome from "../../../components/SubpageBackHome";

const PLACEHOLDER = `写下你希望 AI 如何工作，可以参考下面这几个方面：

身份：张医生（神经内科）的AI助手
沟通风格：口语化表达，用昵称称呼患者
回复方式：先给结论再解释原因，简短直接
注意事项：不主动展开罕见风险`;

/** Parse "### Section\ncontent" into [{title, items}] */
function parseSections(text) {
  if (!text) return [];
  const sections = [];
  const parts = text.split(/^###\s+/m).filter(Boolean);
  for (const part of parts) {
    const [firstLine, ...rest] = part.split("\n");
    const title = firstLine.trim();
    const body = rest.join("\n").trim();
    const items = body
      .split(/\s*·\s*|\n/)
      .map((s) => s.trim())
      .filter(Boolean);
    if (title) sections.push({ title, items });
  }
  return sections;
}

export default function PersonaSubpage() {
  const navigate = useNavigate();
  const api = useApi();
  const queryClient = useQueryClient();
  const { doctorId } = useDoctorStore();

  const { data: persona, isLoading: loading } = usePersona();

  const savedSummary = persona?.summary_text || "";
  const fallbackFromRules = (() => {
    if (!persona?.fields) return "";
    const LABELS = {
      reply_style: "沟通风格",
      structure: "回复结构",
      avoid: "回避内容",
      closing: "结尾方式",
      edits: "修改习惯",
    };
    const parts = Object.entries(LABELS)
      .map(([key, label]) => {
        const rules = (persona.fields[key] || []).map((r) => r.text).filter(Boolean);
        return rules.length > 0 ? `${label}：${rules.join("；")}` : "";
      })
      .filter(Boolean);
    return parts.join("\n");
  })();
  const displayText = savedSummary || fallbackFromRules;

  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(displayText || "");
  const [saving, setSaving] = useState(false);
  const [templates, setTemplates] = useState([]);
  const [selectedTemplate, setSelectedTemplate] = useState(null);
  const [applying, setApplying] = useState(null);

  useEffect(() => {
    if (persona && !editing) {
      setDraft(displayText);
    }
  }, [persona]); // eslint-disable-line react-hooks/exhaustive-deps

  // Load persona templates for the empty-state picker
  useEffect(() => {
    if (!loading && !displayText && doctorId) {
      api.getPersonaTemplates(doctorId)
        .then((res) => setTemplates(res?.templates || []))
        .catch(() => {}); // templates are optional — silent fail
    }
  }, [loading, displayText, doctorId]); // eslint-disable-line react-hooks/exhaustive-deps

  async function handleApplyTemplate(templateId) {
    setApplying(templateId);
    try {
      await api.applyPersonaTemplate(doctorId, templateId);
      queryClient.invalidateQueries({ queryKey: QK.persona(doctorId) });
      Toast.show({ content: "已应用", position: "bottom" });
      setSelectedTemplate(null);
    } catch {
      Toast.show({ content: "应用失败，请重试", position: "bottom" });
    } finally {
      setApplying(null);
    }
  }

  async function handleSave() {
    const trimmed = draft.trim();
    setSaving(true);
    try {
      await api.updatePersonaSummary(doctorId, trimmed);
      queryClient.invalidateQueries({ queryKey: QK.persona(doctorId) });
      Toast.show({ content: "已保存", position: "bottom" });
      setEditing(false);
    } catch {
      Toast.show({ content: "保存失败，请重试", position: "bottom" });
    } finally {
      setSaving(false);
    }
  }

  const sections = useMemo(() => parseSections(displayText), [displayText]);
  const previewSections = useMemo(() => parseSections(draft), [draft]);

  const sectionColorMap = {
    身份: APP.primary,
    沟通风格: APP.accent,
    回复方式: APP.warning,
    注意事项: APP.danger,
    结尾习惯: APP.text4,
    修改习惯: APP.text4,
  };

  return (
    <div style={pageContainer}>
      <SafeArea position="top" />
      <NavBar backArrow={<SubpageBackHome />}
        onBack={() => navigate(-1)}
        right={
          editing ? (
            <Button
              size="small"
              color="primary"
              loading={saving}
              onClick={handleSave}
              style={{ "--border-radius": "6px" }}
            >
              保存
            </Button>
          ) : (
            <Button
              size="small"
              fill="none"
              color="primary"
              onClick={() => { setDraft(displayText); setEditing(true); }}
            >
              编辑
            </Button>
          )
        }
        style={navBarStyle}
      >
        AI风格
      </NavBar>

      <div style={{ ...scrollable, padding: "16px" }}>
        {/* <AiDisclaimer /> */}
        {loading && <LoadingCenter />}

        {/* Empty state — show template picker first */}
        {!loading && !displayText && !editing && !selectedTemplate && (
          <div>
            <div style={{ fontSize: FONT.md, fontWeight: 600, color: APP.text1, marginBottom: 2 }}>
              选择一个沟通风格开始
            </div>
            <div style={{ fontSize: FONT.sm, color: APP.text3, marginBottom: 12 }}>
              点击预览，确认后再应用
            </div>

            {/* Template cards */}
            {templates.length > 0 && (
              <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 16 }}>
                {templates.map((t) => (
                  <div
                    key={t.id}
                    onClick={() => setSelectedTemplate(t)}
                    style={{
                      borderRadius: RADIUS.lg,
                      padding: "12px 14px",
                      cursor: "pointer",
                      background: APP.surface,
                    }}
                  >
                    <div style={{ fontSize: FONT.md, fontWeight: 600, color: APP.text1 }}>
                      {t.name}
                    </div>
                    <div style={{ fontSize: FONT.sm, color: APP.text3, marginTop: 2 }}>
                      {t.subtitle}
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Or divider */}
            <div style={{ display: "flex", alignItems: "center", gap: 12, margin: "16px 0" }}>
              <div style={{ flex: 1, height: "0.5px", background: APP.border }} />
              <span style={{ fontSize: FONT.xs, color: APP.text4 }}>或者</span>
              <div style={{ flex: 1, height: "0.5px", background: APP.border }} />
            </div>

            {/* Secondary options */}
            <div style={{ display: "flex", gap: 8 }}>
              <Button block fill="outline" onClick={() => { setDraft(""); setEditing(true); }}>
                直接写
              </Button>
            </div>
          </div>
        )}

        {/* Template preview — after picking, before confirming */}
        {!loading && !displayText && !editing && selectedTemplate && (() => {
          const previewSecs = parseSections(selectedTemplate.summary_text);
          return (
            <div>
              <div style={{ fontSize: FONT.md, fontWeight: 600, color: APP.text1, marginBottom: 2 }}>
                {selectedTemplate.name}
              </div>
              <div style={{ fontSize: FONT.sm, color: APP.text3, marginBottom: 12 }}>
                {selectedTemplate.subtitle}
              </div>

              {/* Sample reply — the big "this is what your AI would say" preview */}
              {selectedTemplate.sample_reply && (
                <div style={{
                  background: APP.primaryLight,
                  borderRadius: RADIUS.md,
                  padding: "12px 14px",
                  marginBottom: 12,
                }}>
                  <div style={{
                    fontSize: FONT.xs, fontWeight: 600, color: APP.primary, marginBottom: 6,
                  }}>
                    示例回复
                  </div>
                  <div style={{ fontSize: FONT.sm, color: APP.text1, lineHeight: 1.7 }}>
                    {selectedTemplate.sample_reply}
                  </div>
                </div>
              )}

              {/* Structured sections */}
              {previewSecs.length > 0 && (
                <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 16 }}>
                  {previewSecs.map((sec) => {
                    const color = sectionColorMap[sec.title] || APP.text4;
                    return (
                      <div key={sec.title} style={{
                        background: APP.surfaceAlt,
                        borderRadius: RADIUS.sm,
                        padding: "10px 12px",
                      }}>
                        <div style={{ fontSize: FONT.xs, fontWeight: 600, color, marginBottom: 4 }}>
                          {sec.title}
                        </div>
                        <div style={{ fontSize: FONT.sm, color: APP.text2, lineHeight: 1.6 }}>
                          {sec.items.join(" · ")}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}

              <div style={{ display: "flex", gap: 8 }}>
                <Button
                  block fill="outline"
                  onClick={() => setSelectedTemplate(null)}
                  disabled={!!applying}
                >
                  重新选择
                </Button>
                <Button
                  block color="primary"
                  onClick={() => handleApplyTemplate(selectedTemplate.id)}
                  loading={!!applying}
                >
                  确认使用
                </Button>
              </div>
            </div>
          );
        })()}

        {!loading && editing && (
          <>
            <TextArea
              placeholder={PLACEHOLDER}
              value={draft}
              onChange={setDraft}
              autoSize={{ minRows: 8, maxRows: 20 }}
              maxLength={800}
              showCount
              style={{
                "--font-size": FONT.md,
                "--placeholder-color": APP.text4,
                backgroundColor: APP.surface,
                borderRadius: RADIUS.md,
                padding: "12px",
                border: `0.5px solid ${APP.border}`,
                lineHeight: 1.7,
              }}
            />

            {/* Live preview */}
            {previewSections.length > 0 && (
              <div style={{ marginTop: 16 }}>
                <div style={{ fontSize: FONT.sm, color: APP.text4, marginBottom: 8 }}>预览</div>
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  {previewSections.map((sec) => {
                    const color = sectionColorMap[sec.title] || APP.text4;
                    return (
                      <div
                        key={sec.title}
                        style={{
                          backgroundColor: APP.surfaceAlt,
                          borderRadius: RADIUS.sm,
                          padding: "10px 14px",
                          border: `0.5px solid ${APP.border}`,
                        }}
                      >
                        <div style={{ fontSize: FONT.xs, fontWeight: 600, color, marginBottom: 4, textTransform: "uppercase", letterSpacing: 0.5 }}>
                          {sec.title}
                        </div>
                        <div style={{ fontSize: FONT.sm, color: APP.text2, lineHeight: 1.6 }}>
                          {sec.items.join(" · ")}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            <div style={{ marginTop: 16, display: "flex", gap: 8 }}>
              {displayText && (
                <Button
                  fill="outline"
                  block
                  onClick={() => { setDraft(displayText); setEditing(false); }}
                  disabled={saving}
                >
                  取消
                </Button>
              )}
              <Button
                color="primary"
                block
                loading={saving}
                onClick={handleSave}
              >
                保存
              </Button>
            </div>
          </>
        )}

        {!loading && !editing && (
          <div>
            {sections.length > 0 ? (
              <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                {sections.map((sec) => {
                  const color = sectionColorMap[sec.title] || APP.text4;
                  return (
                    <div
                      key={sec.title}
                      style={{
                        backgroundColor: APP.surface,
                        borderRadius: RADIUS.lg,
                        padding: "12px 16px",
                      }}
                    >
                      <div style={{
                        fontSize: FONT.xs,
                        fontWeight: 600,
                        color,
                        textTransform: "uppercase",
                        letterSpacing: 0.5,
                        marginBottom: 6,
                      }}>
                        {sec.title}
                      </div>
                      <div style={{ fontSize: FONT.main, color: APP.text1, lineHeight: 1.7 }}>
                        {sec.items.join(" · ")}
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              /* Fallback for non-sectioned text */
              <div
                style={{
                  backgroundColor: APP.surface,
                  borderRadius: RADIUS.lg,
                  padding: "16px",
                  fontSize: FONT.main,
                  color: APP.text1,
                  lineHeight: 1.8,
                  whiteSpace: "pre-wrap",
                  wordBreak: "break-word",
                }}
              >
                {displayText}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
