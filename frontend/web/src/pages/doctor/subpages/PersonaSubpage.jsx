/**
 * PersonaSubpage — editable free-text AI style bio.
 *
 * The doctor reads and directly edits a natural-language description
 * of how their AI assistant communicates.
 *
 * @see /doctor/settings/persona
 */
import { useState, useEffect, useMemo } from "react";
import { Box, TextField, Typography } from "@mui/material";
import { TYPE, COLOR, RADIUS } from "../../../theme";
import HelpTip from "../../../components/HelpTip";
import PageSkeleton from "../../../components/PageSkeleton";
import AppButton from "../../../components/AppButton";
import SectionLoading from "../../../components/SectionLoading";
import { useQueryClient } from "@tanstack/react-query";
import { QK } from "../../../lib/queryKeys";
import { useApi } from "../../../api/ApiContext";
import { usePersona, usePersonaPending } from "../../../lib/doctorQueries";
import { useAppNavigate } from "../../../hooks/useAppNavigate";
import { dp } from "../../../utils/doctorBasePath";
import { useDoctorStore } from "../../../store/doctorStore";
import { PAGE_HELP } from "../constants";

const PLACEHOLDER = `用 ### 分节，用 · 分隔要点，例如：

### 身份
张医生（神经内科）的AI助手

### 沟通风格
口语化表达 · 用昵称称呼患者

### 回复方式
先给结论再解释原因 · 简短直接

### 注意事项
不主动展开罕见风险`;

/** Parse "### Section\ncontent" format into [{title, items}] */
function parseSections(text) {
  if (!text) return [];
  const sections = [];
  const parts = text.split(/^###\s+/m).filter(Boolean);
  for (const part of parts) {
    const [firstLine, ...rest] = part.split("\n");
    const title = firstLine.trim();
    const body = rest.join("\n").trim();
    // Split by · or newlines for items
    const items = body
      .split(/\s*·\s*|\n/)
      .map((s) => s.trim())
      .filter(Boolean);
    if (title) sections.push({ title, items });
  }
  return sections;
}

const SECTION_COLORS = {
  "身份": COLOR.primary,
  "沟通风格": COLOR.accent,
  "回复方式": COLOR.warning,
  "注意事项": COLOR.danger,
  "结尾习惯": COLOR.text4,
  "修改习惯": COLOR.text4,
};

export default function PersonaSubpage({ doctorId, onBack, isMobile }) {
  const api = useApi();
  const queryClient = useQueryClient();
  const navigate = useAppNavigate();
  const { data: persona, isLoading: loading } = usePersona();
  const { data: pendingData } = usePersonaPending();
  const pendingCount = pendingData?.count || 0;
  const { doctorId: storeDoctorId } = useDoctorStore();
  const resolvedDoctorId = doctorId || storeDoctorId;

  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);
  const [generating, setGenerating] = useState(false);

  // Build display text: summary_text first, then fallback to concatenated rules
  const savedSummary = persona?.summary_text || "";
  const fallbackFromRules = (() => {
    if (!persona?.fields) return "";
    const LABELS = { reply_style: "沟通风格", structure: "回复结构", avoid: "回避内容", closing: "结尾方式", edits: "修改习惯" };
    const parts = Object.entries(LABELS)
      .map(([key, label]) => {
        const rules = (persona.fields[key] || []).map((r) => r.text).filter(Boolean);
        return rules.length > 0 ? `${label}：${rules.join("；")}` : "";
      })
      .filter(Boolean);
    return parts.join("\n");
  })();
  const displayText = savedSummary || fallbackFromRules;

  useEffect(() => {
    if (persona && !editing) {
      setDraft(displayText);
    }
  }, [persona]); // eslint-disable-line react-hooks/exhaustive-deps

  function startEditing() {
    setDraft(displayText);
    setEditing(true);
  }

  async function handleSave() {
    const trimmed = draft.trim();
    setSaving(true);
    try {
      await api.updatePersonaSummary(resolvedDoctorId, trimmed);
      queryClient.invalidateQueries({ queryKey: QK.persona(resolvedDoctorId) });
      setEditing(false);
    } catch {
      // stay in edit mode
    } finally {
      setSaving(false);
    }
  }

  const hasRules = persona?.fields
    ? Object.values(persona.fields).flat().length > 0
    : false;

  async function handleGenerate() {
    setGenerating(true);
    try {
      const result = await api.generatePersonaProfile(resolvedDoctorId);
      queryClient.invalidateQueries({ queryKey: QK.persona(resolvedDoctorId) });
      if (result.summary_text) setDraft(result.summary_text);
    } catch {
      // silent
    } finally {
      setGenerating(false);
    }
  }

  const hasContent = displayText.length > 0;
  const sections = useMemo(() => parseSections(displayText), [displayText]);

  const listContent = (
    <Box sx={{ flex: 1, overflowY: "auto" }}>
      {pendingCount > 0 && (
        <Box
          onClick={() => navigate(dp("settings/persona/pending"))}
          sx={{
            mx: 2, mt: 1.5,
            bgcolor: COLOR.warningLight,
            px: 1.5, py: 1.25,
            borderRadius: RADIUS.md,
            border: `0.5px solid ${COLOR.amberBorder}`,
            display: "flex", justifyContent: "space-between", alignItems: "center",
            cursor: "pointer",
          }}
        >
          <Typography sx={{ fontSize: TYPE.body.fontSize, fontWeight: 500, color: COLOR.amberText }}>
            AI发现 {pendingCount} 条待确认
          </Typography>
          <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.amberText }}>
            查看 ›
          </Typography>
        </Box>
      )}

      {loading && <SectionLoading rows={5} />}

      {!loading && (
        <Box sx={{ px: 2, py: 2 }}>
          {/* Empty state with onboarding CTA */}
          {!hasContent && !editing && (
            <Box sx={{
              bgcolor: COLOR.primaryLight,
              borderRadius: RADIUS.md,
              border: `0.5px solid ${COLOR.primaryBorder}`,
              p: 2, mb: 2,
            }}>
              <Typography sx={{ fontSize: TYPE.body.fontSize, fontWeight: 600, color: COLOR.primaryText, mb: 0.5 }}>
                还没有AI风格描述
              </Typography>
              <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text3, mb: 1.5, lineHeight: 1.6 }}>
                描述你希望AI如何与患者沟通，或用引导流程快速生成
              </Typography>
              <Box sx={{ display: "flex", gap: 1 }}>
                <AppButton variant="primary" size="sm" onClick={startEditing}>
                  直接写
                </AppButton>
                {hasRules ? (
                  <AppButton
                    variant="secondary" size="sm"
                    onClick={handleGenerate}
                    loading={generating}
                    loadingLabel="生成中…"
                  >
                    AI生成
                  </AppButton>
                ) : (
                  <AppButton
                    variant="secondary" size="sm"
                    onClick={() => navigate(dp("settings/persona/onboarding"))}
                  >
                    引导生成
                  </AppButton>
                )}
              </Box>
            </Box>
          )}

          {/* Read mode — render sections as styled cards */}
          {hasContent && !editing && (
            <Box>
              {sections.length > 0 ? (
                <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5 }}>
                  {sections.map((sec) => {
                    const color = SECTION_COLORS[sec.title] || COLOR.text4;
                    return (
                      <Box key={sec.title} sx={{
                        bgcolor: COLOR.white,
                        borderRadius: RADIUS.md,
                        border: `0.5px solid ${COLOR.border}`,
                        p: 1.5,
                      }}>
                        <Typography sx={{
                          fontSize: TYPE.caption.fontSize,
                          fontWeight: 600,
                          color,
                          textTransform: "uppercase",
                          letterSpacing: 0.5,
                          mb: 0.75,
                        }}>
                          {sec.title}
                        </Typography>
                        <Typography sx={{ fontSize: TYPE.body.fontSize, color: COLOR.text1, lineHeight: 1.7 }}>
                          {sec.items.join(" · ")}
                        </Typography>
                      </Box>
                    );
                  })}
                </Box>
              ) : (
                /* Fallback for non-sectioned text */
                <Box sx={{
                  bgcolor: COLOR.white,
                  borderRadius: RADIUS.md,
                  border: `0.5px solid ${COLOR.border}`,
                  p: 2,
                }}>
                  <Typography sx={{ fontSize: TYPE.body.fontSize, color: COLOR.text1, lineHeight: 1.8, whiteSpace: "pre-wrap" }}>
                    {displayText}
                  </Typography>
                </Box>
              )}
              <Box sx={{ display: "flex", gap: 1, mt: 2 }}>
                <AppButton variant="primary" size="md" fullWidth onClick={startEditing}>
                  编辑
                </AppButton>
                <AppButton
                  variant="secondary" size="md" fullWidth
                  onClick={() => navigate(dp("settings/persona/teach"))}
                >
                  教AI新偏好
                </AppButton>
              </Box>
            </Box>
          )}

          {/* Edit mode */}
          {editing && (() => {
            const previewSections = parseSections(draft);
            return (
              <Box>
                <TextField
                  fullWidth
                  multiline
                  minRows={6}
                  maxRows={12}
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  placeholder={PLACEHOLDER}
                  disabled={saving}
                  inputProps={{ maxLength: 2000 }}
                  sx={{
                    "& .MuiOutlinedInput-root": { borderRadius: RADIUS.md, fontSize: TYPE.secondary.fontSize },
                    "& .MuiInputBase-input": { fontFamily: "monospace", lineHeight: 1.6 },
                  }}
                />
                <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4, textAlign: "right", mt: 0.5 }}>
                  {draft.length} / 2000
                </Typography>

                {/* Live preview */}
                {previewSections.length > 0 && (
                  <Box sx={{ mt: 1.5 }}>
                    <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4, mb: 0.75 }}>
                      预览
                    </Typography>
                    <Box sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
                      {previewSections.map((sec) => {
                        const color = SECTION_COLORS[sec.title] || COLOR.text4;
                        return (
                          <Box key={sec.title} sx={{ bgcolor: COLOR.surfaceAlt, borderRadius: RADIUS.sm, px: 1.5, py: 1 }}>
                            <Typography sx={{ fontSize: TYPE.caption.fontSize, fontWeight: 600, color, mb: 0.5 }}>
                              {sec.title}
                            </Typography>
                            <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text2, lineHeight: 1.6 }}>
                              {sec.items.join(" · ")}
                            </Typography>
                          </Box>
                        );
                      })}
                    </Box>
                  </Box>
                )}

                <Box sx={{ display: "flex", gap: 1, mt: 1.5 }}>
                  <AppButton
                    variant="secondary" size="md" fullWidth
                    onClick={() => setEditing(false)}
                    disabled={saving}
                  >
                    取消
                  </AppButton>
                  <AppButton
                    variant="primary" size="md" fullWidth
                    onClick={handleSave}
                    loading={saving}
                    loadingLabel="保存中…"
                  >
                    保存
                  </AppButton>
                </Box>
              </Box>
            );
          })()}
        </Box>
      )}
    </Box>
  );

  return (
    <PageSkeleton
      title="AI 风格"
      headerRight={<HelpTip message={PAGE_HELP.persona} />}
      onBack={onBack}
      isMobile={isMobile}
      listPane={listContent}
    />
  );
}
