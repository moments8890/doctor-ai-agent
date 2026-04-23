/**
 * @route /doctor/settings/knowledge/:id
 *
 * KnowledgeDetailSubpage v2 — view/edit a single knowledge item.
 * antd-mobile only, no MUI.
 */
import { useCallback, useEffect, useState } from "react";
import { NavBar, Button, TextArea, Dialog, Toast, Tag, Grid } from "antd-mobile";
import { DeleteOutline } from "antd-mobile-icons";
import { useNavigate, useParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { QK } from "../../../../lib/queryKeys";
import { useApi } from "../../../../api/ApiContext";
import { useDoctorStore } from "../../../../store/doctorStore";
import { recordView } from "../../../../hooks/useLastViewed";
import { useRuleHealth, useKnowledgeUsage } from "../../../../lib/doctorQueries";
import { APP, FONT, RADIUS, CATEGORY_COLORS as THEME_CATEGORY_COLORS } from "../../../theme";
import { pageContainer, navBarStyle, scrollable } from "../../../layouts";
import { LoadingCenter, ActionFooter } from "../../../components";

function formatDate(dateStr) {
  if (!dateStr) return "";
  const d = new Date(dateStr);
  if (isNaN(d)) return dateStr;
  return `${d.getMonth() + 1}月${d.getDate()}日`;
}

const CATEGORY_COLORS = {
  ...THEME_CATEGORY_COLORS,
  persona: { bg: "#f5f0ff", text: "#9b59b6" },
};

function getCategoryStyle(category) {
  const c = CATEGORY_COLORS[category];
  if (c) return { bg: c.bg, color: c.text || c.color };
  return { bg: APP.surfaceAlt, color: APP.text4 };
}

export default function KnowledgeDetailSubpage({ itemId: propItemId }) {
  const navigate = useNavigate();
  const params = useParams();
  const itemId = propItemId ? parseInt(propItemId) : parseInt(params.id);
  const api = useApi();
  const queryClient = useQueryClient();
  const { doctorId } = useDoctorStore();

  const { data: ruleHealth } = useRuleHealth(itemId);
  const { data: usageData } = useKnowledgeUsage(itemId);

  const [item, setItem] = useState(null);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(false);
  const [editText, setEditText] = useState("");
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const load = useCallback(() => {
    if (!doctorId || !itemId) return;
    setLoading(true);
    const fetchItem = async () => {
      if (api.getKnowledgeBatch) {
        const data = await api.getKnowledgeBatch(doctorId, [itemId]);
        const items = data?.items || [];
        return items[0] || null;
      }
      const allData = await api.getKnowledgeItems(doctorId);
      const listData = Array.isArray(allData) ? allData : (allData?.items || []);
      return listData.find((i) => i.id === itemId) || null;
    };

    fetchItem()
      .then((result) => {
        setItem(result);
        if (result) {
          const raw = result.text || result.content || "";
          const firstLine = raw.split("\n")[0] || "";
          const title = (result.title || firstLine || "知识条目").slice(0, 40);
          recordView({
            type: "knowledge",
            id: result.id,
            title,
            category: result.category || null,
            updatedAt: result.updated_at || result.created_at || null,
          });
        }
      })
      .catch(() => setItem(null))
      .finally(() => setLoading(false));
  }, [doctorId, itemId]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { load(); }, [load]);

  async function handleDelete() {
    Dialog.confirm({
      title: "确认删除",
      content: "删除后该知识将不再影响 AI 行为，确定要删除吗？",
      confirmText: "删除",
      cancelText: "保留",
      onConfirm: async () => {
        setDeleting(true);
        try {
          await api.deleteKnowledgeItem(doctorId, itemId);
          queryClient.invalidateQueries({ queryKey: QK.knowledge(doctorId) });
          Toast.show({ content: "已删除", position: "bottom" });
          navigate(-1);
        } catch {
          Toast.show({ content: "删除失败", position: "bottom" });
        } finally {
          setDeleting(false);
        }
      },
    });
  }

  async function handleSaveEdit() {
    const trimmed = editText.trim();
    if (!trimmed || !api.updateKnowledgeItem) return;
    setSaving(true);
    try {
      await api.updateKnowledgeItem(doctorId, itemId, trimmed);
      queryClient.invalidateQueries({ queryKey: QK.knowledge(doctorId) });
      Toast.show({ content: "已保存", position: "bottom" });
      setEditing(false);
      load();
    } catch {
      Toast.show({ content: "保存失败，请重试", position: "bottom" });
    } finally {
      setSaving(false);
    }
  }

  const text = item?.text || item?.content || "";
  const rawTitle = item?.title || text.split("\n").filter((l) => l.trim())[0] || "知识条目";
  const title = rawTitle.length > 25 ? rawTitle.slice(0, 22) + "…" : rawTitle;
  const bodyText = text.startsWith(rawTitle) ? text.slice(rawTitle.length).replace(/^[：:\s]+/, "") : text;
  const catStyle = item?.category ? getCategoryStyle(item.category) : null;

  // Edit mode
  if (editing) {
    return (
      <div style={pageContainer}>
        <NavBar
          onBack={() => setEditing(false)}
          right={
            <Button size="small" color="primary" loading={saving} onClick={handleSaveEdit}>
              保存
            </Button>
          }
          style={navBarStyle}
        >
          编辑知识
        </NavBar>

        <div style={{ ...scrollable, padding: "16px" }}>
          <TextArea
            value={editText}
            onChange={setEditText}
            autoSize={{ minRows: 10, maxRows: 20 }}
            maxLength={3000}
            showCount
            style={{
              "--font-size": FONT.base,
              backgroundColor: APP.surface,
              borderRadius: RADIUS.md,
              padding: "12px",
              border: `0.5px solid ${APP.border}`,
            }}
          />
        </div>

        <ActionFooter>
          <Button fill="outline" block onClick={() => setEditing(false)} disabled={saving}>
            取消
          </Button>
          <Button color="primary" block loading={saving} disabled={!editText.trim()} onClick={handleSaveEdit}>
            保存
          </Button>
        </ActionFooter>
      </div>
    );
  }

  return (
    <div style={pageContainer}>
      <NavBar
        onBack={() => navigate(-1)}
        right={
          item?.category !== "persona" ? (
            <Button
              size="small"
              fill="none"
              color="danger"
              loading={deleting}
              onClick={handleDelete}
            >
              <DeleteOutline />
            </Button>
          ) : null
        }
        style={navBarStyle}
      >
        知识详情
      </NavBar>

      <div style={scrollable}>
        {loading && <LoadingCenter />}

        {!loading && !item && (
          <div style={{ textAlign: "center", paddingTop: 64, color: APP.text4, fontSize: FONT.base }}>
            未找到该知识条目
          </div>
        )}

        {!loading && item && (
          <>
            {/* AI 使用情况 card */}
            <div
              style={{
                backgroundColor: APP.surface,
                margin: "12px 12px 0",
                borderRadius: RADIUS.lg,
                padding: "16px 16px 14px",
              }}
            >
              <div style={{ fontSize: FONT.base, fontWeight: 600, color: APP.text1, marginBottom: 12 }}>
                AI 使用情况
              </div>

              {/* Stats grid — 5 columns */}
              <Grid columns={5} gap={0} style={{ marginBottom: 12 }}>
                {[
                  {
                    label: "总引用",
                    value: ruleHealth?.cited_count ?? "—",
                    color: APP.text1,
                  },
                  {
                    label: "近30天",
                    value: ruleHealth?.last_30_days?.cited_count ?? "—",
                    color: APP.text1,
                  },
                  {
                    label: "被接受",
                    value: ruleHealth?.accepted_count ?? "—",
                    color: APP.success,
                  },
                  {
                    label: "被修改",
                    value: ruleHealth?.edited_count ?? "—",
                    color: APP.warning,
                  },
                  {
                    label: "被拒绝",
                    value: ruleHealth?.rejected_count ?? "—",
                    color: APP.danger,
                  },
                ].map(({ label, value, color }) => (
                  <Grid.Item key={label}>
                    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 2 }}>
                      <span style={{ fontSize: 22, fontWeight: 700, color, lineHeight: 1.2 }}>
                        {value}
                      </span>
                      <span style={{ fontSize: FONT.xs, color: APP.text4 }}>{label}</span>
                    </div>
                  </Grid.Item>
                ))}
              </Grid>

              {/* Recent patient chips */}
              {(() => {
                const recentUsage = usageData?.usage ?? [];
                if (recentUsage.length === 0) {
                  return (
                    <div style={{ fontSize: FONT.sm, color: APP.text4 }}>暂无引用记录</div>
                  );
                }
                return (
                  <div
                    style={{
                      display: "flex",
                      gap: 8,
                      overflowX: "auto",
                      paddingBottom: 2,
                      WebkitOverflowScrolling: "touch",
                    }}
                  >
                    {recentUsage.slice(0, 5).map((usage, idx) => (
                      <div
                        key={idx}
                        onClick={() => navigate(`/doctor/patients/${usage.patient_id}`)}
                        style={{
                          flexShrink: 0,
                          display: "inline-flex",
                          alignItems: "center",
                          padding: "4px 10px",
                          borderRadius: RADIUS.pill,
                          backgroundColor: APP.surfaceAlt,
                          fontSize: FONT.sm,
                          color: APP.text2,
                          cursor: "pointer",
                          border: `0.5px solid ${APP.border}`,
                          minHeight: 28,
                        }}
                      >
                        {usage.patient_name || "患者"}
                        {usage.used_at
                          ? ` · ${formatDate(usage.used_at)}`
                          : ""}
                      </div>
                    ))}
                  </div>
                );
              })()}
            </div>

            {/* Content card */}
            <div
              style={{
                backgroundColor: APP.surface,
                margin: "12px 12px 0",
                borderRadius: RADIUS.lg,
                padding: "16px",
              }}
            >
              <div style={{ fontSize: FONT.lg, fontWeight: 600, color: APP.text1, marginBottom: 8 }}>
                {title}
              </div>
              <div
                style={{
                  fontSize: FONT.base,
                  color: APP.text2,
                  lineHeight: 1.7,
                  whiteSpace: "pre-wrap",
                  wordBreak: "break-word",
                  marginBottom: 12,
                }}
              >
                {bodyText || text}
              </div>

              {/* Meta row */}
              <div style={{ display: "flex", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
                {item.category && catStyle && (
                  <Tag
                    style={{
                      "--background-color": catStyle.bg,
                      "--text-color": catStyle.color,
                      "--border-color": catStyle.bg,
                    }}
                  >
                    {item.category}
                  </Tag>
                )}
                {item.created_at && (
                  <span style={{ fontSize: FONT.sm, color: APP.text4 }}>
                    {formatDate(item.created_at)}
                  </span>
                )}
                {item.reference_count > 0 && (
                  <span style={{ fontSize: FONT.sm, color: APP.text4 }}>
                    引用 {item.reference_count} 次
                  </span>
                )}
              </div>

              {/* Source URL */}
              {item.source_url && (
                <div style={{ marginTop: 8, fontSize: FONT.sm, color: APP.text4, wordBreak: "break-all" }}>
                  来源:{" "}
                  <a
                    href={item.source_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{ color: APP.text4, textDecoration: "underline" }}
                  >
                    {item.source_url.length > 40
                      ? item.source_url.slice(0, 40) + "…"
                      : item.source_url}
                    {" "}↗
                  </a>
                </div>
              )}
            </div>

            <div style={{ height: 24 }} />
          </>
        )}
      </div>

      {/* Bottom action bar */}
      {!loading && item && (
        <ActionFooter>
          {item.category !== "persona" && (
            <Button
              fill="outline"
              color="danger"
              loading={deleting}
              onClick={handleDelete}
            >
              删除
            </Button>
          )}
          <Button
            color="primary"
            block
            onClick={() => { setEditText(text); setEditing(true); }}
          >
            编辑
          </Button>
        </ActionFooter>
      )}
    </div>
  );
}
