/**
 * ReplyCard -- unified reply card component for all reply-related UI.
 *
 * Three modes:
 *   "pending"   — full card with patient header, AI draft, edit/send, citations, no-draft notice
 *                 Used in ReviewQueuePage (回复 tab) and TaskPage.
 *   "completed" — compact completed-reply row with avatar, message previews, chevron
 *                 Used in ReviewQueuePage (完成 tab) for reply-type items.
 *   "inline"    — same as pending but without patient name header (already shown in context)
 *                 Used in PatientDetail's PatientChatPage.
 *
 * Props:
 *   item         — { patient_name, patient_message, draft_text, cited_rules, status, id, patient_id, badge, time }
 *   mode         — "pending" | "completed" | "inline"
 *   doctorId     — string
 *   onSent       — called after send/reply completes; receives (item) or (item.id)
 *   onTeachPrompt— called when edit triggers teaching; receives (edit_id)
 *   onClick      — (completed mode only) row click handler
 */
import { useState, useRef } from "react";
import { Box, Typography } from "@mui/material";
import MicNoneOutlinedIcon from "@mui/icons-material/MicNoneOutlined";
import ChevronRightOutlinedIcon from "@mui/icons-material/ChevronRightOutlined";
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

/* ── Shared sub-components ────────────────────────────────────────── */

function PatientMessageBubble({ message, sx }) {
  if (!message) return null;
  return (
    <Box sx={{
      bgcolor: COLOR.surface,
      borderRadius: RADIUS.md,
      px: 1.5, py: 1, mb: 1,
      fontSize: TYPE.secondary.fontSize,
      color: COLOR.text2,
      lineHeight: 1.5,
      ...sx,
    }}>
      {message}
    </Box>
  );
}

function CitationTags({ rules, navigate }) {
  if (!rules?.length) return null;
  return (
    <Box sx={{ mt: 1, display: "flex", flexWrap: "wrap", gap: 0.5 }}>
      {rules.map((rule) => (
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
  );
}

function NoDraftNotice({ editing, editText, setEditText, textareaRef, compact }) {
  return (
    <Box sx={{
      bgcolor: "#fff8e1",
      border: "0.5px solid #ffcc02",
      borderRadius: RADIUS.md,
      px: 1.5, py: 1,
      ...(compact ? {} : { mb: 1 }),
    }}>
      <Typography sx={{ fontSize: TYPE.micro.fontSize, color: "#b28704", fontWeight: 500, mb: editing ? 0.5 : (compact ? 0 : 0.5) }}>
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
        <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text4, mt: compact ? 0.3 : 0 }}>
          请手动回复此消息，或添加相关知识条目后重新生成
        </Typography>
      )}
    </Box>
  );
}

function DraftCard({ item, editing, editText, setEditText, textareaRef, showVoice, setShowVoice, navigate, compact }) {
  if (!item.draft_text) return null;
  return (
    <Box sx={{
      bgcolor: COLOR.white,
      border: `0.5px solid ${COLOR.border}`,
      borderRadius: RADIUS.md,
      px: 1.5, py: 1,
      ...(compact ? {} : { mb: 1 }),
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
                flex: 1, minHeight: compact ? 100 : 120,
                border: `1px solid ${COLOR.border}`, borderRadius: RADIUS.sm,
                p: 1, fontSize: TYPE.secondary.fontSize, color: COLOR.text2,
                lineHeight: 1.5, resize: "vertical", fontFamily: "inherit",
                outline: "none", overflow: "hidden",
                "&:focus": { borderColor: COLOR.primary },
                ...(compact ? { width: "100%" } : {}),
              }}
            />
            {!compact && isVoiceSupported() && (
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
                <MicNoneOutlinedIcon sx={{ fontSize: 18, color: showVoice ? COLOR.primary : COLOR.text4 }} />
              </Box>
            )}
          </Box>
          {!compact && showVoice && (
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

      {!editing && <CitationTags rules={item.cited_rules} navigate={navigate} />}
    </Box>
  );
}

/* ── CompletedReplyRow (mode="completed") ─────────────────────────── */

function CompletedReplyRow({ item, onClick }) {
  return (
    <Box
      onClick={onClick}
      sx={{
        px: 1.5, py: 1, bgcolor: COLOR.white,
        borderBottom: `0.5px solid ${COLOR.borderLight}`,
        cursor: onClick ? "pointer" : "default",
        "&:active": onClick ? { bgcolor: COLOR.surface } : {},
        "&:last-child": { borderBottom: "none" },
      }}
    >
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 1 }}>
        <NameAvatar name={item.patient_name} size={32} />
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography sx={{ fontSize: TYPE.action.fontSize, fontWeight: 500 }}>
            {item.patient_name}
          </Typography>
          <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.primary, mt: 0.1 }}>
            已回复
          </Typography>
        </Box>
        <ChevronRightOutlinedIcon sx={{ fontSize: 16, color: COLOR.text4, flexShrink: 0 }} />
      </Box>
      {item.patient_message && (
        <Box sx={{ bgcolor: COLOR.surface, borderRadius: RADIUS.md, px: 1.2, py: 0.6, mb: 0.4, ml: 5.5, fontSize: TYPE.secondary.fontSize, color: COLOR.text3 }}>
          患者: {item.patient_message.length > 50 ? item.patient_message.slice(0, 50) + "..." : item.patient_message}
        </Box>
      )}
      {item.draft_text && (
        <Box sx={{ bgcolor: "#f0faf0", borderRadius: RADIUS.md, px: 1.2, py: 0.6, ml: 5.5, fontSize: TYPE.secondary.fontSize, color: COLOR.text2 }}>
          医生: {item.draft_text.length > 50 ? item.draft_text.slice(0, 50) + "..." : item.draft_text}
        </Box>
      )}
    </Box>
  );
}

/* ── PendingReplyCard (mode="pending" | "inline") ─────────────────── */

function PendingReplyCard({ item, mode, onSent, onTeachPrompt }) {
  const [editing, setEditing] = useState(false);
  const [editText, setEditText] = useState(item.draft_text || "");
  const textareaRef = useRef(null);
  const [saving, setSaving] = useState(false);
  const [showVoice, setShowVoice] = useState(false);
  const api = useApi();
  const navigate = useAppNavigate();

  const isInline = mode === "inline";
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
      if (isInline) {
        // Inline mode: use editDraft then allow direct send
        await (api.editDraft || (() => Promise.resolve({})))(item.id, null, editText);
        item.draft_text = editText;
        setEditing(false);
      } else if (item.status === "no_draft") {
        // No-draft: send as direct reply
        await (api.replyToPatient || (() => Promise.resolve({})))(item.patient_id, editText);
        if (onSent) onSent(item);
      } else {
        const result = await (api.editDraft || (() => Promise.resolve({})))(item.id, null, editText);
        item.draft_text = editText;
        setEditing(false);
        if (result?.teach_prompt && result?.edit_id && onTeachPrompt) {
          onTeachPrompt(result.edit_id);
        }
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

  const handleSend = async () => {
    setSaving(true);
    try {
      await (api.sendDraft || (() => Promise.resolve()))(item.id, null);
      if (onSent) onSent(isInline ? item.id : item);
    } catch {
      // silently fail
    } finally {
      setSaving(false);
    }
  };

  const isNoDraft = !item.draft_text && item.status === "no_draft";

  // ── Inline mode ──
  if (isInline) {
    // No-draft: simplified display
    if (isNoDraft) {
      return (
        <Box sx={{ mx: 2, mb: 1 }}>
          <PatientMessageBubble message={item.patient_message} sx={{ mb: 1, py: 1 }} />
          <NoDraftNotice editing={false} compact />
        </Box>
      );
    }

    return (
      <Box sx={{ mx: 2, mb: 1 }}>
        <PatientMessageBubble message={item.patient_message} sx={{ mb: 1, py: 1 }} />

        <DraftCard
          item={item}
          editing={editing}
          editText={editText}
          setEditText={setEditText}
          textareaRef={textareaRef}
          showVoice={showVoice}
          setShowVoice={setShowVoice}
          navigate={navigate}
          compact
        />

        {/* Action row */}
        <Box sx={{ display: "flex", justifyContent: "flex-end", gap: 2, mt: 1 }}>
          {editing ? (
            <>
              <Typography onClick={handleCancel}
                sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text4, cursor: "pointer", userSelect: "none", "&:active": { opacity: 0.5 } }}>
                取消
              </Typography>
              <Typography onClick={!saving ? handleSave : undefined}
                sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.primary, cursor: saving ? "default" : "pointer", userSelect: "none", opacity: saving ? 0.5 : 1, "&:active": saving ? {} : { opacity: 0.5 } }}>
                {saving ? "保存中..." : "保存"}
              </Typography>
            </>
          ) : (
            <>
              <Typography onClick={handleStartEdit}
                sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.accent, cursor: "pointer", userSelect: "none", "&:active": { opacity: 0.5 } }}>
                修改
              </Typography>
              <Typography onClick={!saving ? handleSend : undefined}
                sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.primary, cursor: saving ? "default" : "pointer", userSelect: "none", opacity: saving ? 0.5 : 1, "&:active": saving ? {} : { opacity: 0.5 } }}>
                {saving ? "发送中..." : "发送 \u203a"}
              </Typography>
            </>
          )}
        </Box>
      </Box>
    );
  }

  // ── Pending mode (full card with header) ──
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
      <PatientMessageBubble message={item.patient_message} />

      {/* No-draft notice */}
      {isNoDraft && (
        <NoDraftNotice
          editing={editing}
          editText={editText}
          setEditText={setEditText}
          textareaRef={textareaRef}
        />
      )}

      {/* AI draft card */}
      <DraftCard
        item={item}
        editing={editing}
        editText={editText}
        setEditText={setEditText}
        textareaRef={textareaRef}
        showVoice={showVoice}
        setShowVoice={setShowVoice}
        navigate={navigate}
      />

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
              {saving ? "保存中..." : "发送 \u203a"}
            </Typography>
          </>
        ) : (
          <>
            <Typography onClick={handleStartEdit}
              sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.accent, cursor: "pointer", userSelect: "none", "&:active": { opacity: 0.5 } }}>
              {item.draft_text ? "\u270e 修改" : "\u270e 回复"}
            </Typography>
            {item.draft_text && (
              <Typography onClick={() => onSent?.(item)}
                sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.primary, cursor: "pointer", userSelect: "none", "&:active": { opacity: 0.5 } }}>
                {"发送 \u203a"}
              </Typography>
            )}
          </>
        )}
      </Box>
    </Box>
  );
}

/* ── DiagnosisCard (mode="diagnosis") ────────────────────────────── */

function DiagnosisReviewCard({ item, onClick }) {
  const navigate = useAppNavigate();
  const hasCitation = !!item.rule_cited;
  const urgencyLabel = item.urgency === "urgent" ? "紧急" : "待处理";
  const urgencyColor = item.urgency === "urgent" ? COLOR.danger : COLOR.warning;

  return (
    <Box sx={{
      px: 2, py: 1.5,
      borderBottom: `0.5px solid ${COLOR.borderLight}`,
      bgcolor: COLOR.white,
      "&:last-child": { borderBottom: "none" },
    }}>
      {/* Header — same layout as pending reply */}
      <Box
        onClick={onClick}
        sx={{ display: "flex", alignItems: "center", gap: 1, mb: 1, cursor: "pointer" }}
      >
        <NameAvatar name={item.patient_name || "?"} size={36} />
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
            <Typography sx={{ fontSize: TYPE.action.fontSize, fontWeight: 500, color: COLOR.text1 }}>
              {item.patient_name}
            </Typography>
            <Box component="span" sx={{
              fontSize: 10, fontWeight: 600, borderRadius: RADIUS.sm,
              px: 0.6, py: 0.1, bgcolor: urgencyColor, color: "#fff", lineHeight: 1.5,
            }}>
              {urgencyLabel}
            </Box>
          </Box>
          <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4, mt: 0.1 }}>
            {item.time}
          </Typography>
        </Box>
        <ChevronRightOutlinedIcon sx={{ fontSize: 18, color: COLOR.text4, flexShrink: 0 }} />
      </Box>

      {/* Diagnosis preview — same bubble style as patient message */}
      <Box onClick={onClick} sx={{
        px: 1.5, py: 1, bgcolor: COLOR.surface, borderRadius: RADIUS.md,
        cursor: "pointer", mb: 1,
      }}>
        <Typography sx={{ fontSize: TYPE.secondary.fontSize, fontWeight: 400, color: COLOR.text1, mb: 0.5 }}>
          {item.section_label || item.section}：{item.content}
        </Typography>
        <Typography sx={{
          fontSize: TYPE.caption.fontSize, color: COLOR.text3, lineHeight: 1.4,
          overflow: "hidden", textOverflow: "ellipsis",
          display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical",
        }}>
          {item.detail}
        </Typography>
      </Box>

      {/* Citation — same tag style as reply citations */}
      {hasCitation ? (
        <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.5 }}>
          <Box component="span" onClick={() => navigate("/doctor/settings/knowledge")} sx={{
            fontSize: 11, color: COLOR.primary, bgcolor: COLOR.successLight,
            px: 1, py: 0.5, borderRadius: RADIUS.sm,
            cursor: "pointer", "&:hover": { bgcolor: COLOR.successLight },
          }}>
            引用: {item.rule_cited}
          </Box>
        </Box>
      ) : (
        <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text4 }}>
          未引用个人规则
        </Typography>
      )}
    </Box>
  );
}

/* ── Main export ──────────────────────────────────────────────────── */

export default function ReplyCard({ item, mode = "pending", doctorId, onSent, onTeachPrompt, onClick }) {
  if (mode === "completed") {
    return <CompletedReplyRow item={item} onClick={onClick} />;
  }
  if (mode === "diagnosis") {
    return <DiagnosisReviewCard item={item} onClick={onClick} />;
  }
  return (
    <PendingReplyCard
      item={item}
      mode={mode}
      onSent={onSent}
      onTeachPrompt={onTeachPrompt}
    />
  );
}
