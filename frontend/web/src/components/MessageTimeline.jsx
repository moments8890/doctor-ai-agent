/**
 * MessageTimeline — compact patient/AI/reply timeline used in patient detail.
 *
 * Shows the latest 3 timeline items by default. When a pending draft exists,
 * it counts as one of those visible items so the inline reply always stays in view.
 */
import { useEffect, useRef, useState } from "react";
import { Box, Typography } from "@mui/material";
import { TYPE, COLOR, RADIUS } from "../theme";

const SOURCE_CONFIG = {
  patient: { label: "患者", color: COLOR.recordBlue },
  ai: { label: "AI", color: COLOR.text4 },
  doctor: { label: "医生", color: COLOR.primary },
};

const TIMELINE_SEPARATOR_WIDTH = 28;
const CONNECTOR_WIDTH = 2;
const DOT_SIZE = 12;

function formatTime(dateStr) {
  if (!dateStr) return "";
  try {
    return new Date(dateStr).toLocaleString("zh-CN", {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return "";
  }
}

function resizeTextarea(node) {
  if (!node) return;
  node.style.height = "auto";
  node.style.height = `${node.scrollHeight}px`;
}

function TimelineSeparator({ color, outlined = false, showConnector, connectorColor = COLOR.border }) {
  return (
    <Box
      sx={{
        width: `${TIMELINE_SEPARATOR_WIDTH}px`,
        flexShrink: 0,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        alignSelf: "stretch",
        pt: 0.5,
        mr: 1.5,
      }}
    >
      <Box
        sx={{
          width: `${DOT_SIZE}px`,
          height: `${DOT_SIZE}px`,
          borderRadius: "50%",
          boxSizing: "border-box",
          bgcolor: outlined ? COLOR.white : color,
          border: `2px solid ${color}`,
        }}
      />
      {showConnector && (
        <Box
          sx={{
            width: `${CONNECTOR_WIDTH}px`,
            flex: 1,
            minHeight: 16,
            mt: 0.5,
            borderRadius: `${CONNECTOR_WIDTH}px`,
            bgcolor: connectorColor,
          }}
        />
      )}
    </Box>
  );
}

function TimelineRow({
  color,
  children,
  connectorColor = COLOR.border,
  outlined = false,
  showConnector = false,
}) {
  return (
    <Box sx={{ display: "flex", alignItems: "stretch" }}>
      <TimelineSeparator
        color={color}
        outlined={outlined}
        showConnector={showConnector}
        connectorColor={connectorColor}
      />
      <Box sx={{ flex: 1, minWidth: 0, pb: showConnector ? 1.75 : 0.25 }}>
        {children}
      </Box>
    </Box>
  );
}

function TimelineNode({ message, showConnector }) {
  const cfg = SOURCE_CONFIG[message.source] || SOURCE_CONFIG.ai;
  const isAiDisclosure = (message.content || "").includes("AI辅助生成");

  return (
    <TimelineRow color={cfg.color} showConnector={showConnector}>
      <Box sx={{ pt: 0.5 }}>
        <Box sx={{ display: "flex", alignItems: "baseline", gap: 1, flexWrap: "wrap" }}>
          <Typography sx={{ fontSize: TYPE.caption.fontSize, color: cfg.color, fontWeight: 600 }}>
            {cfg.label}
          </Typography>
          <Typography sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.text4 }}>
            {formatTime(message.created_at)}
          </Typography>
        </Box>
        <Typography
          sx={{
            fontSize: TYPE.body.fontSize,
            fontWeight: TYPE.body.fontWeight,
            color: isAiDisclosure ? COLOR.text4 : (message.source === "ai" ? COLOR.text3 : COLOR.text1),
            fontStyle: isAiDisclosure ? "italic" : "normal",
            lineHeight: 1.6,
            mt: 0.5,
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
          }}
        >
          {message.content}
        </Typography>
      </Box>
    </TimelineRow>
  );
}

function DraftTimelineNode({
  draft,
  onSaveDraftEdit,
  onSendDraft,
  onSendManualReply,
  onCitationClick,
  showConnector,
}) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(draft.text || "");
  const [busy, setBusy] = useState("");
  const textareaRef = useRef(null);
  const isManualReply = draft.status === "no_draft" || !draft.text;
  const citedRules = Array.isArray(draft.citedRules)
    ? draft.citedRules.filter(Boolean)
    : (draft.rule_cited ? [{ title: draft.rule_cited }] : []);

  useEffect(() => {
    setEditing(false);
    setText(draft.text || "");
    setBusy("");
  }, [draft.id, draft.status, draft.text]);

  useEffect(() => {
    if (!editing) return;
    resizeTextarea(textareaRef.current);
  }, [editing, text]);

  async function handleSave() {
    const nextText = text.trim();
    if (!nextText || busy) return;
    setBusy("save");
    try {
      await onSaveDraftEdit?.(nextText, draft);
      setEditing(false);
    } finally {
      setBusy("");
    }
  }

  async function handleSend() {
    const nextText = text.trim();
    if (busy) return;
    if (isManualReply) {
      if (!editing) {
        setEditing(true);
        return;
      }
      if (!nextText) return;
      setBusy("send");
      try {
        await onSendManualReply?.(nextText, draft);
      } finally {
        setBusy("");
      }
      return;
    }

    setBusy("send");
    try {
      await onSendDraft?.(draft);
    } finally {
      setBusy("");
    }
  }

  return (
    <TimelineRow
      color={COLOR.primary}
      outlined
      showConnector={showConnector}
      connectorColor={isManualReply ? "#f0d38a" : "#cfe8d6"}
    >
      <Box sx={{ pt: 0.5 }}>
        <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.primary, fontWeight: 600, mb: 0.5 }}>
          {isManualReply ? "待手动回复" : "AI起草回复 · 待发送"}
        </Typography>

        <Box
          sx={{
            bgcolor: isManualReply ? COLOR.amberLight : "#f5fbf6",
            borderRadius: RADIUS.md,
            px: 1.5,
            py: 1.5,
            border: isManualReply ? "0.5px solid #f0d38a" : "0.5px solid #e4f2e7",
          }}
        >
          {editing ? (
            <Box
              component="textarea"
              ref={textareaRef}
              value={text}
              onChange={(e) => {
                setText(e.target.value);
                resizeTextarea(e.target);
              }}
              onFocus={(e) => {
                resizeTextarea(e.target);
              }}
              placeholder={isManualReply ? "回复患者..." : undefined}
              sx={{
                width: "100%",
                minHeight: 108,
                p: 1,
                border: `1px solid ${COLOR.border}`,
                borderRadius: RADIUS.md,
                boxSizing: "border-box",
                resize: "none",
                bgcolor: COLOR.surface,
                fontSize: TYPE.body.fontSize,
                lineHeight: 1.55,
                color: COLOR.text1,
                fontFamily: "inherit",
                outline: "none",
                overflow: "hidden",
                "&:focus": { borderColor: COLOR.primary },
              }}
            />
          ) : (
            <>
              <Typography
                sx={{
                  fontSize: TYPE.body.fontSize,
                  color: isManualReply ? COLOR.text3 : COLOR.text1,
                  lineHeight: 1.55,
                  whiteSpace: "pre-wrap",
                  wordBreak: "break-word",
                }}
              >
                {isManualReply ? "AI未找到可引用的知识条目，请手动回复患者。" : draft.text}
              </Typography>
            </>
          )}

          {!isManualReply && citedRules.length > 0 && (
            <Box sx={{ mt: 1, display: "flex", flexWrap: "wrap", gap: 0.5 }}>
              {citedRules.map((rule, index) => {
                const isClickable = Boolean(rule?.id && onCitationClick);
                return (
                  <Box
                    key={rule?.id || `${rule?.title || "rule"}-${index}`}
                    component="span"
                    onClick={isClickable ? () => onCitationClick(rule) : undefined}
                    sx={{
                      display: "inline-block",
                      px: 1,
                      py: 0.5,
                      bgcolor: COLOR.successLight,
                      borderRadius: RADIUS.sm,
                      fontSize: TYPE.micro.fontSize,
                      color: COLOR.primary,
                      fontWeight: 500,
                      cursor: isClickable ? "pointer" : "default",
                      "&:hover": isClickable ? { bgcolor: COLOR.successLight } : undefined,
                    }}
                  >
                    引用: {rule?.title || draft.rule_cited}
                  </Box>
                );
              })}
            </Box>
          )}

          <Box sx={{ display: "flex", justifyContent: "flex-end", gap: 2, mt: 1 }}>
            {editing ? (
              <>
                <Typography
                  onClick={busy ? undefined : () => { setEditing(false); setText(draft.text || ""); }}
                  sx={{
                    fontSize: TYPE.body.fontSize,
                    color: COLOR.text4,
                    cursor: busy ? "default" : "pointer",
                    opacity: busy ? 0.5 : 1,
                    userSelect: "none",
                  }}
                >
                  取消
                </Typography>
                <Typography
                  onClick={busy ? undefined : (isManualReply ? handleSend : handleSave)}
                  sx={{
                    fontSize: TYPE.body.fontSize,
                    color: COLOR.primary,
                    cursor: busy ? "default" : "pointer",
                    opacity: busy ? 0.5 : 1,
                    userSelect: "none",
                  }}
                >
                  {busy === "save" ? "保存中..." : busy === "send" ? "发送中..." : (isManualReply ? "发送 ›" : "保存")}
                </Typography>
              </>
            ) : (
              <>
                {!isManualReply && (
                  <Typography
                    onClick={() => setEditing(true)}
                    sx={{
                      fontSize: TYPE.body.fontSize,
                      color: COLOR.text4,
                      cursor: "pointer",
                      userSelect: "none",
                    }}
                  >
                    修改
                  </Typography>
                )}
                <Typography
                  onClick={busy ? undefined : handleSend}
                  sx={{
                    fontSize: TYPE.body.fontSize,
                    color: COLOR.primary,
                    cursor: busy ? "default" : "pointer",
                    opacity: busy ? 0.5 : 1,
                    userSelect: "none",
                  }}
                >
                  {busy === "send" ? "发送中..." : (isManualReply ? "回复" : "发送 ›")}
                </Typography>
              </>
            )}
          </Box>
        </Box>
      </Box>
    </TimelineRow>
  );
}

export default function MessageTimeline({
  messages,
  draft,
  maxHeight,
  defaultExpanded = false,
  visibleCount = 3,
  onCitationClick,
  onSaveDraftEdit,
  onSendDraft,
  onSendManualReply,
}) {
  const [showAll, setShowAll] = useState(defaultExpanded);
  const safeMessages = messages || [];
  const totalCount = safeMessages.length + (draft ? 1 : 0);

  if (!totalCount) return null;

  const draftSlot = draft ? 1 : 0;
  const hiddenCount = Math.max(0, totalCount - visibleCount);
  const hasMore = hiddenCount > 0;
  const visibleMessageCount = showAll || !hasMore
    ? safeMessages.length
    : Math.max(0, visibleCount - draftSlot);
  const visibleMessages = showAll || !hasMore
    ? safeMessages
    : safeMessages.slice(-visibleMessageCount);
  const hasItemsBelowToggle = visibleMessages.length > 0 || Boolean(draft);

  return (
    <Box sx={{ maxHeight, overflowY: maxHeight ? "auto" : undefined }}>
      <Box sx={{ pt: 1, pr: 0.5 }}>
        {hasMore && (
          <TimelineRow color={COLOR.text4} outlined showConnector={hasItemsBelowToggle}>
            <Typography
              onClick={() => setShowAll((prev) => !prev)}
              sx={{
                fontSize: TYPE.caption.fontSize,
                color: showAll ? COLOR.text4 : COLOR.primary,
                cursor: "pointer",
                userSelect: "none",
                pt: 0.5,
              }}
            >
              {showAll ? "收起更早消息 ▴" : `查看更早 ${hiddenCount} 条消息 ▾`}
            </Typography>
          </TimelineRow>
        )}

        {visibleMessages.map((message, index) => (
          <TimelineNode
            key={message.id || index}
            message={message}
            showConnector={index < visibleMessages.length - 1 || Boolean(draft)}
          />
        ))}

        {draft && (
          <DraftTimelineNode
            draft={draft}
            showConnector={false}
            onCitationClick={onCitationClick}
            onSaveDraftEdit={onSaveDraftEdit}
            onSendDraft={onSendDraft}
            onSendManualReply={onSendManualReply}
          />
        )}
      </Box>
    </Box>
  );
}
