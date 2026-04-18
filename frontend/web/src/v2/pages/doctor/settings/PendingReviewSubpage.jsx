/**
 * @route /doctor/settings/pending-review
 *
 * PendingReviewSubpage v2 — review AI-discovered persona suggestions.
 * antd-mobile only, no MUI.
 */
import { useState } from "react";
import { NavBar, Button, Tag, SpinLoading, ErrorBlock } from "antd-mobile";
import { useNavigate } from "react-router-dom";
import { usePersonaPending, useAcceptPendingItem, useRejectPendingItem } from "../../../../lib/doctorQueries";
import { APP, FONT, RADIUS } from "../../../theme";

const FIELD_LABELS = {
  reply_style: "回复风格",
  closing: "常用结尾语",
  structure: "回复结构",
  avoid: "回避内容",
  edits: "常见修改",
};

const CONFIDENCE_COLORS = {
  high: APP.primary,
  medium: APP.warning,
  low: APP.text4,
};

const CONFIDENCE_LABELS = {
  high: "确信",
  medium: "可能",
  low: "猜测",
};

export default function PendingReviewSubpage() {
  const navigate = useNavigate();
  const { data, isLoading } = usePersonaPending();
  const acceptMutation = useAcceptPendingItem();
  const rejectMutation = useRejectPendingItem();
  const [actingId, setActingId] = useState(null);

  const items = data?.items || [];
  const anyActing = actingId !== null;

  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column", background: APP.surfaceAlt }}>
      <NavBar
        onBack={() => navigate(-1)}
        style={{
          "--height": "44px",
          "--border-bottom": `0.5px solid ${APP.border}`,
          backgroundColor: APP.surface,
          flexShrink: 0,
        }}
      >
        AI发现
      </NavBar>

      <div style={{ flex: 1, overflowY: "auto", padding: "12px 16px" }}>
        {isLoading ? (
          <div style={{ display: "flex", justifyContent: "center", padding: 40 }}>
            <SpinLoading color="primary" />
          </div>
        ) : items.length === 0 ? (
          <ErrorBlock status="empty" title="暂无待确认的发现" description="" />
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {items.map((item) => {
              const fieldLabel = FIELD_LABELS[item.field] || item.field;
              const confColor = CONFIDENCE_COLORS[item.confidence] || CONFIDENCE_COLORS.medium;
              const confLabel = CONFIDENCE_LABELS[item.confidence] || item.confidence;
              const isThisActing = actingId === item.id;

              return (
                <div
                  key={item.id}
                  style={{
                    background: APP.surface,
                    borderRadius: RADIUS.md,
                    border: `0.5px solid ${APP.border}`,
                    padding: 12,
                  }}
                >
                  {/* Field + confidence */}
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
                    <Tag
                      style={{
                        "--background-color": APP.surfaceAlt,
                        "--border-color": APP.border,
                        "--text-color": APP.text2,
                        fontSize: "var(--adm-font-size-xs)",
                      }}
                    >
                      {fieldLabel}
                    </Tag>
                    <span style={{ fontSize: "var(--adm-font-size-xs)", color: confColor }}>
                      {confLabel}
                    </span>
                  </div>

                  {/* Proposed rule */}
                  <p style={{
                    fontSize: "var(--adm-font-size-main)",
                    color: APP.text1,
                    fontWeight: 500,
                    margin: "0 0 6px",
                    lineHeight: 1.5,
                  }}>
                    {item.proposed_rule}
                  </p>

                  {/* Evidence */}
                  {item.evidence_summary && (
                    <p style={{
                      fontSize: "var(--adm-font-size-sm)",
                      color: APP.text4,
                      margin: "0 0 12px",
                      lineHeight: 1.5,
                    }}>
                      {item.evidence_summary}
                    </p>
                  )}

                  {/* Actions */}
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                    <Button
                      fill="outline"
                      size="small"
                      block
                      disabled={anyActing}
                      loading={isThisActing && rejectMutation.isPending}
                      onClick={() => {
                        setActingId(item.id);
                        rejectMutation.mutate(item.id, { onSettled: () => setActingId(null) });
                      }}
                    >
                      忽略
                    </Button>
                    <Button
                      color="primary"
                      size="small"
                      block
                      disabled={anyActing}
                      loading={isThisActing && acceptMutation.isPending}
                      onClick={() => {
                        setActingId(item.id);
                        acceptMutation.mutate(item.id, { onSettled: () => setActingId(null) });
                      }}
                    >
                      确认
                    </Button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
