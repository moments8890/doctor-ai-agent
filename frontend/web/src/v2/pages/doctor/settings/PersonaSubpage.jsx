/**
 * @route /doctor/settings/persona
 *
 * PersonaSubpage v2 — edit AI persona free-text summary.
 * antd-mobile only, no MUI.
 */
import { useState, useEffect, useMemo } from "react";
import { NavBar, TextArea, Button, SpinLoading, Toast } from "antd-mobile";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { QK } from "../../../../lib/queryKeys";
import { useApi } from "../../../../api/ApiContext";
import { usePersona } from "../../../../lib/doctorQueries";
import { useDoctorStore } from "../../../../store/doctorStore";
import { APP, FONT, RADIUS } from "../../../theme";

const PLACEHOLDER = `用 ### 分节，用 · 分隔要点，例如：

### 身份
张医生（神经内科）的AI助手

### 沟通风格
口语化表达 · 用昵称称呼患者

### 回复方式
先给结论再解释原因 · 简短直接

### 注意事项
不主动展开罕见风险`;

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

  const [editing, setEditing] = useState(!displayText);
  const [draft, setDraft] = useState(displayText || "");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (persona && !editing) {
      setDraft(displayText);
    }
  }, [persona]); // eslint-disable-line react-hooks/exhaustive-deps

  // If persona loads and is empty, enter edit mode automatically
  useEffect(() => {
    if (!loading && !displayText) {
      setEditing(true);
    }
  }, [loading, displayText]);

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
        style={{
          "--height": "44px",
          "--border-bottom": `0.5px solid ${APP.border}`,
          backgroundColor: APP.surface,
          flexShrink: 0,
        }}
      >
        AI风格
      </NavBar>

      <div style={{ flex: 1, overflowY: "auto", padding: "16px" }}>
        {loading && (
          <div style={{ display: "flex", justifyContent: "center", paddingTop: 48 }}>
            <SpinLoading color="primary" />
          </div>
        )}

        {!loading && editing && (
          <>
            <TextArea
              placeholder={PLACEHOLDER}
              value={draft}
              onChange={setDraft}
              autoSize={{ minRows: 8, maxRows: 20 }}
              maxLength={2000}
              showCount
              style={{
                "--font-size": "14px",
                "--placeholder-color": APP.text4,
                fontFamily: "monospace",
                backgroundColor: APP.surface,
                borderRadius: RADIUS.md,
                padding: "12px",
                border: `0.5px solid ${APP.border}`,
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
                        borderRadius: RADIUS.md,
                        padding: "12px 16px",
                        border: `0.5px solid ${APP.border}`,
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
                  borderRadius: RADIUS.md,
                  padding: "16px",
                  border: `0.5px solid ${APP.border}`,
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
