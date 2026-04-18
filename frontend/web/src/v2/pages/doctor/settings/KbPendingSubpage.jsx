/**
 * KbPendingSubpage v2 — review AI-discovered factual-edit rules.
 * antd-mobile only, no MUI.
 */
import { useState } from "react";
import { NavBar, Button, Tag, SpinLoading, Dialog, ErrorBlock } from "antd-mobile";
import { useNavigate } from "react-router-dom";
import { useKbPending, useAcceptKbPending, useRejectKbPending } from "../../../../lib/doctorQueries";
import { dp } from "../../../../utils/doctorBasePath";
import { APP } from "../../../theme";

const CATEGORY_LABELS = {
  diagnosis: "诊断",
  medication: "用药",
  followup: "随访",
  custom: "通用",
};

export default function KbPendingSubpage() {
  const { data, isLoading } = useKbPending();
  const acceptMutation = useAcceptKbPending();
  const rejectMutation = useRejectKbPending();
  const navigate = useNavigate();
  const [actingId, setActingId] = useState(null);

  function openSource(link) {
    if (!link) return;
    if (link.entity_type === "diagnosis" && link.record_id) {
      navigate(`${dp("review")}/${link.record_id}`);
    } else if (link.entity_type === "draft_reply" && link.patient_id) {
      const qs = new URLSearchParams({ view: "chat" });
      if (link.draft_id) qs.set("highlight_draft_id", String(link.draft_id));
      navigate(`${dp("patients")}/${link.patient_id}?${qs.toString()}`);
    }
  }

  function handleReject(item) {
    Dialog.confirm({
      title: "确认排除这条规则？",
      content: "排除后 90 天内不会再次提示相同模式。",
      cancelText: "取消",
      confirmText: "确认排除",
      onConfirm: () => {
        setActingId(item.id);
        rejectMutation.mutate(item.id, { onSettled: () => setActingId(null) });
      },
    });
  }

  const items = data?.items || [];
  const anyActing = actingId !== null;

  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column", background: APP.surfaceAlt }}>
      <NavBar onBack={() => navigate(-1)} style={{ "--border-bottom": `0.5px solid ${APP.border}`, background: APP.surface }}>
        待采纳的临床规则
      </NavBar>

      <div style={{ flex: 1, overflowY: "auto", padding: "12px 16px" }}>
        {isLoading ? (
          <div style={{ display: "flex", justifyContent: "center", padding: 40 }}>
            <SpinLoading />
          </div>
        ) : items.length === 0 ? (
          <ErrorBlock status="empty" title="暂无待采纳的临床规则" description="" />
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {items.map((item) => {
              const categoryLabel = CATEGORY_LABELS[item.category] || item.category;
              const isThisActing = actingId === item.id;
              const link = item.source_link;
              const clickable = !!(link && (link.record_id || link.patient_id));

              return (
                <div key={item.id} style={{
                  background: APP.surface, borderRadius: 8,
                  border: `0.5px solid ${APP.border}`, padding: 12,
                }}>
                  {/* Category + confidence */}
                  <div style={{ display: "flex", gap: 6, marginBottom: 6 }}>
                    <Tag>{categoryLabel}</Tag>
                    <Tag fill="outline">置信度：{item.confidence}</Tag>
                  </div>

                  {/* Proposed rule */}
                  <p style={{ fontSize: "var(--adm-font-size-main)", color: APP.text1, fontWeight: 500, margin: "0 0 4px" }}>
                    {item.proposed_rule}
                  </p>

                  {/* Evidence */}
                  {item.evidence_summary && (
                    <p
                      onClick={clickable ? () => openSource(link) : undefined}
                      style={{
                        fontSize: "var(--adm-font-size-sm)", margin: "0 0 10px",
                        color: clickable ? "#07C160" : APP.text4,
                        cursor: clickable ? "pointer" : "default",
                        textDecoration: clickable ? "underline" : "none",
                      }}
                    >
                      依据：{item.evidence_summary}
                      {clickable && (
                        <span style={{ marginLeft: 4, color: APP.text4 }}>
                          · 查看{link.entity_type === "diagnosis" ? "诊断" : "回复"}
                        </span>
                      )}
                    </p>
                  )}

                  {/* Actions */}
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                    <Button
                      fill="outline" size="small" block
                      disabled={anyActing}
                      loading={isThisActing && rejectMutation.isPending}
                      onClick={() => handleReject(item)}
                    >
                      排除
                    </Button>
                    <Button
                      color="primary" size="small" block
                      disabled={anyActing}
                      loading={isThisActing && acceptMutation.isPending}
                      onClick={() => {
                        setActingId(item.id);
                        acceptMutation.mutate(item.id, { onSettled: () => setActingId(null) });
                      }}
                    >
                      保存为规则
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
