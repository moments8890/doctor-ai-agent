/**
 * KbPendingSubpage — review AI-discovered factual-edit rules, accept to write to KB.
 * Each item shows the proposed rule, category, confidence, and evidence summary.
 * Doctor can 保存为规则 (accept) or 排除 (reject, with confirmation).
 */
import { useState } from "react";
import { Box, Chip, Typography } from "@mui/material";
import { TYPE, COLOR, RADIUS } from "../../../theme";
import PageSkeleton from "../../../components/PageSkeleton";
import SectionLoading from "../../../components/SectionLoading";
import EmptyState from "../../../components/EmptyState";
import AppButton from "../../../components/AppButton";
import ConfirmDialog from "../../../components/ConfirmDialog";
import { useKbPending, useAcceptKbPending, useRejectKbPending } from "../../../lib/doctorQueries";
import { useAppNavigate } from "../../../hooks/useAppNavigate";
import { dp } from "../../../utils/doctorBasePath";

const CATEGORY_LABELS = {
  diagnosis: "诊断",
  medication: "用药",
  followup: "随访",
  custom: "通用",
};

export default function KbPendingSubpage({ onBack }) {
  const { data, isLoading } = useKbPending();
  const acceptMutation = useAcceptKbPending();
  const rejectMutation = useRejectKbPending();
  const navigate = useAppNavigate();
  const [actingId, setActingId] = useState(null);
  const [confirmReject, setConfirmReject] = useState(null);

  function openSource(link) {
    if (!link) return;
    if (link.entity_type === "diagnosis" && link.record_id) {
      navigate(`${dp("review")}/${link.record_id}`);
    } else if (link.entity_type === "draft_reply" && link.patient_id) {
      const suffix = link.draft_id ? `?highlight_draft_id=${link.draft_id}` : "";
      navigate(`${dp("patients")}/${link.patient_id}${suffix}`);
    }
  }

  const items = data?.items || [];

  const listContent = isLoading ? (
    <SectionLoading />
  ) : items.length === 0 ? (
    <EmptyState message="暂无待采纳的临床规则" />
  ) : (
    <Box sx={{ px: 2, py: 1.5, display: "flex", flexDirection: "column", gap: 1.5 }}>
      {items.map((item) => {
        const categoryLabel = CATEGORY_LABELS[item.category] || item.category;
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
            {/* Category + confidence */}
            <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 0.75 }}>
              <Chip
                label={categoryLabel}
                size="small"
                sx={{ fontSize: TYPE.caption.fontSize, bgcolor: COLOR.surfaceAlt, color: COLOR.text2 }}
              />
              <Chip
                label={`置信度：${item.confidence}`}
                size="small"
                variant="outlined"
                sx={{ fontSize: TYPE.caption.fontSize }}
              />
            </Box>

            {/* Proposed rule */}
            <Typography sx={{ fontSize: TYPE.body.fontSize, color: COLOR.text1, fontWeight: 500, mb: 0.5 }}>
              {item.proposed_rule}
            </Typography>

            {/* Evidence summary — clickable when source_link resolves */}
            {item.evidence_summary && (
              (() => {
                const link = item.source_link;
                const clickable = !!(link && (link.record_id || link.patient_id));
                return (
                  <Typography
                    onClick={clickable ? () => openSource(link) : undefined}
                    sx={{
                      fontSize: TYPE.secondary.fontSize,
                      color: clickable ? COLOR.primary : COLOR.text4,
                      mb: 1.25,
                      cursor: clickable ? "pointer" : "default",
                      textDecoration: clickable ? "underline" : "none",
                      textDecorationColor: clickable ? COLOR.borderLight : "transparent",
                      "&:active": clickable ? { opacity: 0.6 } : {},
                    }}
                  >
                    依据：{item.evidence_summary}
                    {clickable && (
                      <Box component="span" sx={{ ml: 0.5, color: COLOR.text4 }}>
                        · 查看{link.entity_type === "diagnosis" ? "诊断" : "回复"}
                      </Box>
                    )}
                  </Typography>
                );
              })()
            )}

            {/* Action buttons */}
            <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 1 }}>
              <AppButton
                variant="secondary"
                size="sm"
                fullWidth
                disabled={anyActing}
                loading={isThisActing && rejectMutation.isPending}
                onClick={() => setConfirmReject(item)}
              >
                排除
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
                保存为规则
              </AppButton>
            </Box>
          </Box>
        );
      })}
    </Box>
  );

  return (
    <>
      <PageSkeleton
        title="待采纳的临床规则"
        onBack={onBack}
        listPane={listContent}
      />
      <ConfirmDialog
        open={!!confirmReject}
        title="确认排除这条规则？"
        message="排除后 90 天内不会再次提示相同模式。"
        cancelLabel="取消"
        confirmLabel="确认排除"
        confirmTone="danger"
        onCancel={() => setConfirmReject(null)}
        onConfirm={() => {
          const item = confirmReject;
          setConfirmReject(null);
          setActingId(item.id);
          rejectMutation.mutate(item.id, { onSettled: () => setActingId(null) });
        }}
      />
    </>
  );
}
