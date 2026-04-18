/**
 * @route /doctor/settings/knowledge/:id
 *
 * KnowledgeDetailSubpage v2 — view/edit a single knowledge item.
 * antd-mobile only, no MUI.
 */
import { useCallback, useEffect, useState } from "react";
import { NavBar, Button, TextArea, SpinLoading, Dialog, Toast, Tag } from "antd-mobile";
import { DeleteOutline } from "antd-mobile-icons";
import { useNavigate, useParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { QK } from "../../../../lib/queryKeys";
import { useApi } from "../../../../api/ApiContext";
import { useDoctorStore } from "../../../../store/doctorStore";
import { APP } from "../../../theme";

function formatDate(dateStr) {
  if (!dateStr) return "";
  const d = new Date(dateStr);
  if (isNaN(d)) return dateStr;
  return `${d.getMonth() + 1}月${d.getDate()}日`;
}

const CATEGORY_COLORS = {
  custom:     { bg: "#e7f8ee", color: "#07C160" },
  diagnosis:  { bg: "#e8f4fd", color: "#576B95" },
  followup:   { bg: "#fff8e0", color: "#B8860B" },
  medication: { bg: "#fff0f0", color: "#FA5151" },
  persona:    { bg: "#f5f0ff", color: "#9b59b6" },
};

function getCategoryStyle(category) {
  return CATEGORY_COLORS[category] || { bg: APP.surfaceAlt, color: APP.text4 };
}

export default function KnowledgeDetailSubpage() {
  const navigate = useNavigate();
  const { id } = useParams();
  const itemId = parseInt(id);
  const api = useApi();
  const queryClient = useQueryClient();
  const { doctorId } = useDoctorStore();

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
      .then((result) => setItem(result))
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
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          height: "100%",
          backgroundColor: APP.surfaceAlt,
          overflow: "hidden",
        }}
      >
        <NavBar
          onBack={() => setEditing(false)}
          right={
            <Button size="small" color="primary" loading={saving} onClick={handleSaveEdit}>
              保存
            </Button>
          }
          style={{
            "--height": "44px",
            "--border-bottom": `0.5px solid ${APP.border}`,
            backgroundColor: APP.surface,
            flexShrink: 0,
          }}
        >
          编辑知识
        </NavBar>

        <div style={{ flex: 1, overflowY: "auto", padding: "16px" }}>
          <TextArea
            value={editText}
            onChange={setEditText}
            autoSize={{ minRows: 10, maxRows: 20 }}
            maxLength={3000}
            showCount
            style={{
              "--font-size": "14px",
              backgroundColor: APP.surface,
              borderRadius: 8,
              padding: "12px",
              border: `0.5px solid ${APP.border}`,
            }}
          />
        </div>

        <div
          style={{
            padding: "12px 16px",
            paddingBottom: "calc(12px + env(safe-area-inset-bottom, 0px))",
            backgroundColor: APP.surface,
            borderTop: `0.5px solid ${APP.border}`,
            display: "flex",
            gap: 8,
            flexShrink: 0,
          }}
        >
          <Button fill="outline" block onClick={() => setEditing(false)} disabled={saving}>
            取消
          </Button>
          <Button color="primary" block loading={saving} disabled={!editText.trim()} onClick={handleSaveEdit}>
            保存
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100%",
        backgroundColor: APP.surfaceAlt,
        overflow: "hidden",
      }}
    >
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
        style={{
          "--height": "44px",
          "--border-bottom": `0.5px solid ${APP.border}`,
          backgroundColor: APP.surface,
          flexShrink: 0,
        }}
      >
        知识详情
      </NavBar>

      <div style={{ flex: 1, overflowY: "auto" }}>
        {loading && (
          <div style={{ display: "flex", justifyContent: "center", paddingTop: 48 }}>
            <SpinLoading color="primary" />
          </div>
        )}

        {!loading && !item && (
          <div style={{ textAlign: "center", paddingTop: 64, color: APP.text4, fontSize: 14 }}>
            未找到该知识条目
          </div>
        )}

        {!loading && item && (
          <>
            {/* Content card */}
            <div
              style={{
                backgroundColor: APP.surface,
                borderBottom: `0.5px solid ${APP.border}`,
                padding: "16px",
              }}
            >
              <div style={{ fontSize: 17, fontWeight: 600, color: APP.text1, marginBottom: 8 }}>
                {title}
              </div>
              <div
                style={{
                  fontSize: 14,
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
                  <span style={{ fontSize: 12, color: APP.text4 }}>
                    {formatDate(item.created_at)}
                  </span>
                )}
                {item.reference_count > 0 && (
                  <span style={{ fontSize: 12, color: APP.text4 }}>
                    引用 {item.reference_count} 次
                  </span>
                )}
              </div>

              {/* Source URL */}
              {item.source_url && (
                <div style={{ marginTop: 8, fontSize: 12, color: APP.text4, wordBreak: "break-all" }}>
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
        <div
          style={{
            padding: "12px 16px",
            paddingBottom: "calc(12px + env(safe-area-inset-bottom, 0px))",
            backgroundColor: APP.surface,
            borderTop: `0.5px solid ${APP.border}`,
            display: "flex",
            gap: 8,
            flexShrink: 0,
          }}
        >
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
        </div>
      )}
    </div>
  );
}
