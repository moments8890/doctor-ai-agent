/**
 * @route /doctor/settings/knowledge/:id
 *
 * KnowledgeDetailSubpage v2 — view/edit a single knowledge item.
 * antd-mobile only, no MUI.
 */
import { useCallback, useEffect, useState } from "react";
import { NavBar, Button, TextArea, Dialog, Toast, Tag, Switch } from "antd-mobile";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import EditOutlinedIcon from "@mui/icons-material/EditOutlined";
import { useNavigate, useParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { QK } from "../../../../lib/queryKeys";
import { useApi } from "../../../../api/ApiContext";
import { useDoctorStore } from "../../../../store/doctorStore";
import { recordView } from "../../../../hooks/useLastViewed";
import { useRuleHealth, useKnowledgeUsage } from "../../../../lib/doctorQueries";
import { APP, FONT, RADIUS, CATEGORY_COLOR } from "../../../theme";
import { pageContainer, navBarStyle, scrollable } from "../../../layouts";
import { LoadingCenter, ActionFooter } from "../../../components";
import SubpageBackHome from "../../../components/SubpageBackHome";

function formatDate(dateStr) {
  if (!dateStr) return "";
  const d = new Date(dateStr);
  if (isNaN(d)) return dateStr;
  return `${d.getMonth() + 1}月${d.getDate()}日`;
}

// "今天 / N 天前 / N 周前 / N 个月前 更新" — for the rule title meta row.
// Doctors care whether a rule is stale; relative time is easier to scan than a date.
function timeAgo(dateStr) {
  if (!dateStr) return null;
  const d = new Date(dateStr);
  if (isNaN(d)) return null;
  const days = Math.floor((Date.now() - d.getTime()) / 86_400_000);
  if (days < 1) return "今天更新";
  if (days < 7) return `${days} 天前更新`;
  if (days < 30) return `${Math.floor(days / 7)} 周前更新`;
  const months = Math.floor(days / 30);
  if (months < 12) return `${months} 个月前更新`;
  return `${Math.floor(months / 12)} 年前更新`;
}

function getCategoryStyle(category) {
  const c = CATEGORY_COLOR[category];
  if (c) return { bg: c.bg, color: c.fg };
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
  // Optimistic local state for the patient_safe toggle so the Switch
  // reflects the click immediately even before the PATCH round-trips.
  const [patientSafe, setPatientSafe] = useState(false);
  const [patientSafeSaving, setPatientSafeSaving] = useState(false);

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
          setPatientSafe(!!result.patient_safe);
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

  async function handleTogglePatientSafe(next) {
    if (!api.setKnowledgeItemPatientSafe) return;
    const previous = patientSafe;
    setPatientSafe(next);  // optimistic
    setPatientSafeSaving(true);
    try {
      await api.setKnowledgeItemPatientSafe(doctorId, itemId, next);
      queryClient.invalidateQueries({ queryKey: QK.knowledge(doctorId) });
      Toast.show({
        content: next ? "已开启对患者可见" : "已关闭对患者可见",
        position: "bottom",
      });
    } catch {
      setPatientSafe(previous);  // revert
      Toast.show({ content: "保存失败，请重试", position: "bottom" });
    } finally {
      setPatientSafeSaving(false);
    }
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
        <NavBar backArrow={<SubpageBackHome />}
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
      <NavBar backArrow={<SubpageBackHome />} onBack={() => navigate(-1)} style={navBarStyle}>
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
              {/* Single-line usage summary — doctors just want "is this being used" */}
              {(() => {
                const total = ruleHealth?.cited_count ?? 0;
                const last30 = ruleHealth?.last_30_days?.cited_count ?? 0;
                const summary = total === 0
                  ? "AI 暂未引用过该知识"
                  : last30 > 0
                  ? `过去 30 天被 AI 引用 ${last30} 次 · 累计 ${total} 次`
                  : `累计被 AI 引用 ${total} 次`;
                return (
                  <div style={{ fontSize: FONT.sm, color: APP.text2, marginBottom: 10, lineHeight: 1.5 }}>
                    {summary}
                  </div>
                );
              })()}

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
                          minHeight: 32,
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

            {/* Patient-safe toggle (Phase 0.5) — gates whether the AI may
                use this rule when replying directly to a patient. Has no
                effect until the doctor also marks curation onboarding done
                on the KB list page. */}
            <div
              style={{
                backgroundColor: APP.surface,
                margin: "12px 12px 0",
                borderRadius: RADIUS.lg,
                padding: "14px 16px",
                display: "flex",
                alignItems: "flex-start",
                gap: 12,
              }}
            >
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: FONT.base, fontWeight: 600, color: APP.text1 }}>
                  对患者可见
                </div>
                <div style={{ fontSize: FONT.sm, color: APP.text4, marginTop: 4, lineHeight: 1.5 }}>
                  勾选后，遇到匹配问题鲸鱼会直接回复患者；否则只生成草稿给您审核。
                </div>
              </div>
              <Switch
                checked={patientSafe}
                onChange={handleTogglePatientSafe}
                loading={patientSafeSaving}
                style={{ "--checked-color": APP.primary }}
              />
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
              <div style={{ fontSize: FONT.lg, fontWeight: 600, color: APP.text1, marginBottom: 4 }}>
                {title}
              </div>
              {(() => {
                const ago = timeAgo(item.updated_at || item.created_at);
                return ago ? (
                  <div style={{ fontSize: FONT.xs, color: APP.text4, marginBottom: 10 }}>
                    {ago}
                  </div>
                ) : null;
              })()}
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

      {/* Bottom action bar — 30/70 split, 48px touch target, leading icons */}
      {!loading && item && (
        <ActionFooter>
          {item.category !== "persona" && (
            <Button
              fill="outline"
              color="danger"
              loading={deleting}
              onClick={handleDelete}
              style={{ minHeight: 48, minWidth: 120, whiteSpace: "nowrap" }}
            >
              <DeleteOutlineIcon sx={{ marginRight: "6px", verticalAlign: "middle", fontSize: 18 }} />
              <span style={{ verticalAlign: "middle" }}>删除</span>
            </Button>
          )}
          <Button
            color="primary"
            block
            onClick={() => { setEditText(text); setEditing(true); }}
            style={{ minHeight: 48, whiteSpace: "nowrap" }}
          >
            <EditOutlinedIcon sx={{ marginRight: "6px", verticalAlign: "middle", fontSize: 18 }} />
            <span style={{ verticalAlign: "middle" }}>编辑</span>
          </Button>
        </ActionFooter>
      )}
    </div>
  );
}
