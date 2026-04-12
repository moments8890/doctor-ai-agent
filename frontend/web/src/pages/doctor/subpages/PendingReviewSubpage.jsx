/**
 * PendingReviewSubpage — review and act on AI-discovered persona suggestions.
 * Each item shows the proposed rule, field label, evidence summary, and confidence.
 * Doctor can 确认 (accept) or 忽略 (reject).
 */
import { useState } from "react";
import { Box, Chip, Typography } from "@mui/material";
import { TYPE, COLOR, RADIUS } from "../../../theme";
import PageSkeleton from "../../../components/PageSkeleton";
import HelpTip from "../../../components/HelpTip";
import SectionLoading from "../../../components/SectionLoading";
import EmptyState from "../../../components/EmptyState";
import AppButton from "../../../components/AppButton";
import { usePersonaPending, useAcceptPendingItem, useRejectPendingItem } from "../../../lib/doctorQueries";
import { PAGE_HELP } from "../constants";

const FIELD_LABELS = {
  reply_style: "回复风格",
  closing: "常用结尾语",
  structure: "回复结构",
  avoid: "回避内容",
  edits: "常见修改",
};

const CONFIDENCE_LABELS = {
  high: { label: "确信", color: COLOR.success },
  medium: { label: "可能", color: COLOR.warning },
  low: { label: "猜测", color: COLOR.text4 },
};

export default function PendingReviewSubpage({ onBack, isMobile }) {
  const { data, isLoading } = usePersonaPending();
  const acceptMutation = useAcceptPendingItem();
  const rejectMutation = useRejectPendingItem();
  const [actingId, setActingId] = useState(null);

  const items = data?.items || [];

  const listContent = isLoading ? (
    <SectionLoading />
  ) : items.length === 0 ? (
    <EmptyState message="暂无待确认的发现" />
  ) : (
    <Box sx={{ px: 2, py: 1.5, display: "flex", flexDirection: "column", gap: 1.5 }}>
      {items.map((item) => {
        const conf = CONFIDENCE_LABELS[item.confidence] || CONFIDENCE_LABELS.medium;
        const fieldLabel = FIELD_LABELS[item.field] || item.field;
        const isThisActing = actingId === item.id;
        const anyActing = actingId !== null;
        return (
          <Box
            key={item.id}
            sx={{
              bgcolor: COLOR.white,
              borderRadius: RADIUS.md,
              border: `0.5px solid ${COLOR.border}`,
              p: 1.5,
            }}
          >
            {/* Field + confidence */}
            <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 0.75 }}>
              <Chip
                label={fieldLabel}
                size="small"
                sx={{ fontSize: TYPE.caption.fontSize, bgcolor: COLOR.surfaceAlt, color: COLOR.text2 }}
              />
              <Typography sx={{ fontSize: TYPE.caption.fontSize, color: conf.color }}>
                {conf.label}
              </Typography>
            </Box>

            {/* Proposed rule */}
            <Typography sx={{ fontSize: TYPE.body.fontSize, color: COLOR.text1, fontWeight: 500, mb: 0.5 }}>
              {item.proposed_rule}
            </Typography>

            {/* Evidence summary */}
            <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text4, mb: 1.25 }}>
              {item.evidence_summary}
            </Typography>

            {/* Action buttons */}
            <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 1 }}>
              <AppButton
                variant="secondary"
                size="sm"
                fullWidth
                disabled={anyActing}
                loading={isThisActing && rejectMutation.isPending}
                onClick={() => {
                  setActingId(item.id);
                  rejectMutation.mutate(item.id, { onSettled: () => setActingId(null) });
                }}
              >
                忽略
              </AppButton>
              <AppButton
                variant="primary"
                size="sm"
                fullWidth
                disabled={anyActing}
                loading={isThisActing && acceptMutation.isPending}
                onClick={() => {
                  setActingId(item.id);
                  acceptMutation.mutate(item.id, { onSettled: () => setActingId(null) });
                }}
              >
                确认
              </AppButton>
            </Box>
          </Box>
        );
      })}
    </Box>
  );

  return (
    <PageSkeleton
      title="AI发现"
      headerRight={<HelpTip message={PAGE_HELP.pendingReview} />}
      onBack={onBack}
      isMobile={isMobile}
      listPane={listContent}
    />
  );
}
