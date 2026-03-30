/**
 * MessageItem — pending patient message card with AI draft, edit, send actions.
 *
 * Shared between ReviewQueuePage (门诊 tab) and TaskPage.
 * Shows patient message bubble, AI-drafted reply, citation chips,
 * inline edit with voice input, and send/cancel actions.
 */
import { useState, useRef } from "react";
import { Box, Typography } from "@mui/material";
import MicIcon from "@mui/icons-material/Mic";
import NameAvatar from "../NameAvatar";
import StatusBadge from "../StatusBadge";
import VoiceInput, { isVoiceSupported } from "../VoiceInput";
import { useApi } from "../../api/ApiContext";
import { useAppNavigate } from "../../hooks/useAppNavigate";
import { TYPE, COLOR, RADIUS } from "../../theme";

const BADGE_COLOR_MAP = {
  "新消息": COLOR.warning,
  "紧急": COLOR.danger,
};
const BADGE_LABEL = { new: "新消息", urgent: "紧急" };

export { BADGE_COLOR_MAP, BADGE_LABEL };

export default function MessageItem({ item, onSend, onTeachPrompt }) {
  const [editing, setEditing] = useState(false);
  const [editText, setEditText] = useState(item.draft_text || "");
  const textareaRef = useRef(null);
  const [saving, setSaving] = useState(false);
  const [showVoice, setShowVoice] = useState(false);
  const api = useApi();
  const navigate = useAppNavigate();

  const badgeLabel = BADGE_LABEL[item.badge];

  const handleStartEdit = () => {
    setEditText(item.draft_text || "");
    setEditing(true);
    setTimeout(() => {
      if (textareaRef.current) {
        textareaRef.current.style.height = "auto";
        textareaRef.current.style.height = textareaRef.current.scrollHeight + "px";
      }
    }, 0);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const result = await (api.editDraft || (() => Promise.resolve({})))(item.id, null, editText);
      item.draft_text = editText;
      setEditing(false);
      if (result?.teach_prompt && result?.edit_id && onTeachPrompt) {
        onTeachPrompt(result.edit_id);
      }
    } catch {
      // silently fail
    } finally {
      setSaving(false);
    }
  };

  const handleCancel = () => {
    setEditText(item.draft_text || "");
    setEditing(false);
  };

  return (
    <Box sx={{ px: 2, py: 1.5, borderBottom: `0.5px solid ${COLOR.borderLight}`, "&:last-child": { borderBottom: "none" } }}>
      {/* Header: avatar + name + time + badge */}
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 1 }}>
        <NameAvatar name={item.patient_name} size={32} />
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography sx={{ fontSize: TYPE.body.fontSize, color: COLOR.text1 }}>
            {item.patient_name}
          </Typography>
          <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4 }}>
            {item.time}
          </Typography>
        </Box>
        {badgeLabel && (
          <StatusBadge label={badgeLabel} colorMap={BADGE_COLOR_MAP} sx={{ ml: "auto" }} />
        )}
      </Box>

      {/* Patient message bubble */}
      {item.patient_message && (
        <Box sx={{
          bgcolor: COLOR.surface,
          borderRadius: RADIUS.md,
          px: 1.5, py: 1, mb: 1,
          fontSize: TYPE.secondary.fontSize,
          color: COLOR.text2,
          lineHeight: 1.5,
        }}>
          {item.patient_message}
        </Box>
      )}

      {/* No-draft notice */}
      {!item.draft_text && item.status === "no_draft" && (
        <Box sx={{
          bgcolor: COLOR.amberLight,
          border: `0.5px solid ${COLOR.amberBorder}`,
          borderRadius: RADIUS.md,
          px: 1.5, py: 1, mb: 1,
        }}>
          <Typography sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.amberText, fontWeight: 500, mb: 0.5 }}>
            AI未找到可引用的知识条目，无法起草回复
          </Typography>
          {editing ? (
            <Box
              component="textarea"
              ref={textareaRef}
              value={editText}
              onChange={(e) => { setEditText(e.target.value); const ta = e.target; ta.style.height = "auto"; ta.style.height = ta.scrollHeight + "px"; }}
              placeholder="请手动输入回复..."
              sx={{
                width: "100%", minHeight: 80,
                border: `1px solid ${COLOR.border}`, borderRadius: RADIUS.sm,
                p: 1, fontSize: TYPE.secondary.fontSize, color: COLOR.text2,
                lineHeight: 1.5, resize: "vertical", fontFamily: "inherit",
                outline: "none", "&:focus": { borderColor: COLOR.primary },
              }}
            />
          ) : (
            <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text4 }}>
              请手动回复此消息，或添加相关知识条目后重新生成
            </Typography>
          )}
        </Box>
      )}

      {/* AI draft card */}
      {item.draft_text && (
        <Box sx={{
          bgcolor: COLOR.white,
          border: `0.5px solid ${COLOR.border}`,
          borderRadius: RADIUS.md,
          px: 1.5, py: 1, mb: 1,
        }}>
          <Typography sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.primary, fontWeight: 500, mb: 0.5 }}>
            AI按你的话术起草
          </Typography>

          {editing ? (
            <Box>
              <Box sx={{ display: "flex", gap: 0.5, alignItems: "flex-start" }}>
                <Box
                  component="textarea"
                  ref={textareaRef}
                  value={editText}
                  onChange={(e) => { setEditText(e.target.value); const ta = e.target; ta.style.height = "auto"; ta.style.height = ta.scrollHeight + "px"; }}
                  onFocus={(e) => { const ta = e.target; ta.style.height = "auto"; ta.style.height = ta.scrollHeight + "px"; }}
                  sx={{
                    flex: 1, minHeight: 120,
                    border: `1px solid ${COLOR.border}`, borderRadius: RADIUS.sm,
                    p: 1, fontSize: TYPE.secondary.fontSize, color: COLOR.text2,
                    lineHeight: 1.5, resize: "vertical", fontFamily: "inherit",
                    outline: "none", overflow: "hidden",
                    "&:focus": { borderColor: COLOR.primary },
                  }}
                />
                {isVoiceSupported() && (
                  <Box
                    onClick={() => setShowVoice(!showVoice)}
                    sx={{
                      width: 32, height: 32, borderRadius: "50%",
                      display: "flex", alignItems: "center", justifyContent: "center",
                      cursor: "pointer", flexShrink: 0, mt: 0.5,
                      bgcolor: showVoice ? COLOR.primaryLight : COLOR.surface,
                      "&:active": { opacity: 0.6 },
                    }}
                  >
                    <MicIcon sx={{ fontSize: 18, color: showVoice ? COLOR.primary : COLOR.text4 }} />
                  </Box>
                )}
              </Box>
              {showVoice && (
                <Box sx={{ mt: 1 }}>
                  <VoiceInput
                    onResult={(text) => { setEditText((prev) => prev ? prev + text : text); setShowVoice(false); }}
                    onCancel={() => setShowVoice(false)}
                  />
                </Box>
              )}
            </Box>
          ) : (
            <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text2, lineHeight: 1.5, whiteSpace: "pre-line" }}>
              {item.draft_text}
            </Typography>
          )}

          {item.cited_rules?.length > 0 && !editing && (
            <Box sx={{ mt: 1, display: "flex", flexWrap: "wrap", gap: 0.5 }}>
              {item.cited_rules.map((rule) => (
                <Box
                  key={rule.id}
                  component="span"
                  onClick={() => navigate(`/doctor/settings/knowledge/${rule.id}`)}
                  sx={{
                    fontSize: 11, color: COLOR.primary, bgcolor: COLOR.successLight,
                    px: 1, py: 0.5, borderRadius: RADIUS.sm,
                    cursor: "pointer", "&:hover": { bgcolor: COLOR.successLight },
                  }}
                >
                  引用: {rule.title}
                </Box>
              ))}
            </Box>
          )}
        </Box>
      )}

      {/* Action row */}
      <Box sx={{ display: "flex", justifyContent: "flex-end", gap: 2 }}>
        {editing ? (
          <>
            <Typography onClick={handleCancel}
              sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text4, cursor: "pointer", userSelect: "none", "&:active": { opacity: 0.5 } }}>
              取消
            </Typography>
            <Typography onClick={!saving ? handleSave : undefined}
              sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.primary, cursor: saving ? "default" : "pointer", userSelect: "none", opacity: saving ? 0.5 : 1, "&:active": saving ? {} : { opacity: 0.5 } }}>
              {saving ? "保存中..." : "发送 ›"}
            </Typography>
          </>
        ) : (
          <>
            <Typography onClick={handleStartEdit}
              sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.accent, cursor: "pointer", userSelect: "none", "&:active": { opacity: 0.5 } }}>
              {item.draft_text ? "✎ 修改" : "✎ 回复"}
            </Typography>
            {item.draft_text && (
              <Typography onClick={() => onSend(item)}
                sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.primary, cursor: "pointer", userSelect: "none", "&:active": { opacity: 0.5 } }}>
                发送 ›
              </Typography>
            )}
          </>
        )}
      </Box>
    </Box>
  );
}
