/**
 * PendingReviewSubpage — review and act on AI-discovered persona suggestions.
 * Each item shows the proposed rule, field label, evidence summary, and confidence.
 * Doctor can 确认 (accept) or 忽略 (reject).
 */
import { Box, Chip, Typography } from "@mui/material";
import { TYPE, COLOR, RADIUS } from "../../../theme";
import PageSkeleton from "../../../components/PageSkeleton";
import SectionLoading from "../../../components/SectionLoading";
import EmptyState from "../../../components/EmptyState";
import AppButton from "../../../components/AppButton";
import { usePersonaPending, useAcceptPendingItem, useRejectPendingItem } from "../../../lib/doctorQueries";

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

  const items = data?.items || [];

  return (
    <PageSkeleton
      title="AI发现"
      onBack={onBack}
      mobileView={isMobile}
    >
      {isLoading ? (
        <SectionLoading />
      ) : items.length === 0 ? (
        <EmptyState message="暂无待确认的发现" />
      ) : (
        <Box sx={{ px: 2, py: 1.5, display: "flex", flexDirection: "column", gap: 1.5 }}>
          {items.map((item) => {
            const conf = CONFIDENCE_LABELS[item.confidence] || CONFIDENCE_LABELS.medium;
            const fieldLabel = FIELD_LABELS[item.field] || item.field;
            const isActing = acceptMutation.isPending || rejectMutation.isPending;
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
                    disabled={isActing}
                    loading={rejectMutation.isPending}
                    onClick={() => rejectMutation.mutate(item.id)}
                  >
                    忽略
                  </AppButton>
                  <AppButton
                    variant="primary"
                    size="sm"
                    fullWidth
                    disabled={isActing}
                    loading={acceptMutation.isPending}
                    onClick={() => acceptMutation.mutate(item.id)}
                  >
                    确认
                  </AppButton>
                </Box>
              </Box>
            );
          })}
        </Box>
      )}
    </PageSkeleton>
  );
}
