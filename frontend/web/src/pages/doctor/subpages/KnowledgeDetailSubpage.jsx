/**
 * KnowledgeDetailSubpage -- detail view for a single knowledge rule.
 *
 * Shows full text, metadata, usage stats, and citation history.
 * Bottom action bar: delete (left, red) / edit (right, green).
 *
 * @see /doctor/settings/knowledge/:id
 */
import { useCallback, useEffect, useState } from "react";
import { Box, Button, TextField, Typography } from "@mui/material";
import AssignmentOutlinedIcon from "@mui/icons-material/AssignmentOutlined";
import ChatOutlinedIcon from "@mui/icons-material/ChatOutlined";
import DescriptionOutlinedIcon from "@mui/icons-material/DescriptionOutlined";
import { TYPE, COLOR, RADIUS } from "../../../theme";
import { dp } from "../../../utils/doctorBasePath";
import PageSkeleton from "../../../components/PageSkeleton";
import SectionLabel from "../../../components/SectionLabel";
import ListCard from "../../../components/ListCard";
import StatColumn from "../../../components/StatColumn";
import ConfirmDialog from "../../../components/ConfirmDialog";
import SheetDialog from "../../../components/SheetDialog";
import DialogFooter from "../../../components/DialogFooter";
import IconBadge from "../../../components/IconBadge";
import { useQueryClient } from "@tanstack/react-query";
import { QK } from "../../../lib/queryKeys";
import { useApi } from "../../../api/ApiContext";
import { useAppNavigate } from "../../../hooks/useAppNavigate";
import { ICON_BADGES } from "../constants";
import { useRuleHealth } from "../../../lib/doctorQueries";

/* ── Source config (shared with KnowledgeSubpage) ── */

const SOURCE_BADGE = {
  doctor:     { badge: ICON_BADGES.kb_doctor, label: "手动添加" },
  agent_auto: { badge: ICON_BADGES.kb_ai,     label: "AI生成" },
};

function getSourceConfig(source) {
  if (!source) return SOURCE_BADGE.doctor;
  if (source.startsWith("upload:")) {
    return { badge: ICON_BADGES.kb_upload, label: source.slice("upload:".length) };
  }
  return SOURCE_BADGE[source] || SOURCE_BADGE.doctor;
}

/* ── Helpers ── */

function formatDate(dateStr) {
  if (!dateStr) return "";
  const d = new Date(dateStr);
  if (isNaN(d)) return dateStr;
  return `${d.getMonth() + 1}月${d.getDate()}日`;
}

const USAGE_TYPE_CONFIG = {
  diagnosis: { icon: <AssignmentOutlinedIcon sx={{ fontSize: 16, color: COLOR.text3 }} />, label: "诊断审核" },
  followup:  { icon: <ChatOutlinedIcon sx={{ fontSize: 16, color: COLOR.text3 }} />, label: "随访回复" },
  draft:     { icon: <ChatOutlinedIcon sx={{ fontSize: 16, color: COLOR.text3 }} />, label: "草稿起草" },
  chat:      { icon: <DescriptionOutlinedIcon sx={{ fontSize: 16, color: COLOR.text3 }} />, label: "对话引用" },
};

function getUsageTypeConfig(type) {
  return USAGE_TYPE_CONFIG[type] || { icon: <DescriptionOutlinedIcon sx={{ fontSize: 16, color: COLOR.text3 }} />, label: type || "引用" };
}


/* ── Main ── */

export default function KnowledgeDetailSubpage({ doctorId, itemId, onBack, onDelete, isMobile, isPersona: isPersonaProp }) {
  const navigate = useAppNavigate();
  const api = useApi();
  const queryClient = useQueryClient();

  const [item, setItem] = useState(null);
  const [usage, setUsage] = useState([]);
  const [loading, setLoading] = useState(true);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [editText, setEditText] = useState("");
  const isPersona = item?.category === "persona";

  // Persona structured fields
  const PERSONA_FIELDS = [
    { key: "reply_style", label: "回复风格", hint: "例：简短口语化，像微信聊天" },
    { key: "closing", label: "常用结尾语", hint: "例：有不适随时联系" },
    { key: "structure", label: "回复结构", hint: "例：先回答问题，再给建议" },
    { key: "avoid", label: "回避内容", hint: "例：不提药价，不给新诊断" },
    { key: "edits", label: "常见修改", hint: "例：AI太正式时改口语化" },
  ];
  const [personaFields, setPersonaFields] = useState({});

  function parsePersonaText(text) {
    const fields = {};
    for (const f of PERSONA_FIELDS) {
      const re = new RegExp(`${f.label}[：:]\\s*(.*)`, "m");
      const match = (text || "").match(re);
      const val = match ? match[1].trim() : "";
      fields[f.key] = val === "（待学习）" ? "" : val;
    }
    return fields;
  }

  function buildPersonaText(fields) {
    return PERSONA_FIELDS.map(f => {
      const val = (fields[f.key] || "").trim();
      return `${f.label}：${val || "（待学习）"}`;
    }).join("\n");
  }
  const [saving, setSaving] = useState(false);

  const load = useCallback(() => {
    if (!doctorId || (!itemId && !isPersonaProp)) return;
    setLoading(true);

    const fetchItem = async () => {
      // Persona items: always load from the persona field (not by ID match)
      if (isPersonaProp) {
        const allData = await api.getKnowledgeItems(doctorId);
        if (allData?.persona) {
          return { ...allData.persona, text: allData.persona.content, source: "system", category: "persona" };
        }
        return null;
      }
      // Regular items: try batch endpoint
      if (api.getKnowledgeBatch) {
        const data = await api.getKnowledgeBatch(doctorId, [itemId]);
        const items = data?.items || [];
        return items[0] || null;
      }
      // Fallback: filter from full list
      const allData = await api.getKnowledgeItems(doctorId);
      const listData = Array.isArray(allData) ? allData : (allData?.items || []);
      return listData.find((i) => i.id === itemId) || null;
    };

    const fetchUsage = async () => {
      const fn = api.fetchKnowledgeUsageHistory;
      if (!fn) return [];
      const data = await fn(doctorId, itemId);
      return data?.usage || [];
    };

    Promise.allSettled([fetchItem(), fetchUsage()])
      .then(([itemResult, usageResult]) => {
        setItem(itemResult.status === "fulfilled" ? itemResult.value : null);
        setUsage(usageResult.status === "fulfilled" ? usageResult.value : []);
      })
      .finally(() => setLoading(false));
  }, [doctorId, itemId, isPersonaProp]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { load(); }, [load]);

  async function handleDelete() {
    setDeleteOpen(false);
    if (onDelete) {
      await onDelete(itemId);
    }
  }

  function handleEditOpen() {
    if (isPersona) {
      setPersonaFields(parsePersonaText(text));
    }
    setEditText(text);
    setEditOpen(true);
  }

  async function handleSaveEdit() {
    const trimmed = isPersona ? buildPersonaText(personaFields) : editText.trim();
    if (!trimmed || !api.updateKnowledgeItem) return;
    setSaving(true);
    try {
      await api.updateKnowledgeItem(doctorId, itemId, trimmed);
      queryClient.invalidateQueries({ queryKey: QK.knowledge(doctorId) });
      setEditOpen(false);
      load(); // reload item
    } catch (e) {
      // stay in edit dialog on error
    } finally {
      setSaving(false);
    }
  }

  // Derive display values
  const text = item?.text || item?.content || "";
  const rawTitle = item?.title || text.split("\n").filter((l) => l.trim())[0] || "知识条目";
  // Shorten title on frontend if backend didn't — cap at 20 CJK chars
  const title = rawTitle.length > 25 ? rawTitle.slice(0, 20) + "…" : rawTitle;
  // Don't repeat title in body — show body text minus the title portion
  const bodyText = text.startsWith(rawTitle) ? text.slice(rawTitle.length).replace(/^[：:\s]+/, "") : text;
  const cfg = item ? getSourceConfig(item.source) : null;
  const sourceLabel = cfg ? (item.source?.startsWith("upload:") ? `来源：${cfg.label}` : `来源：${cfg.label}`) : "";
  const category = item?.category;
  const { data: health } = useRuleHealth(isPersonaProp ? null : itemId);

  // Find most recent usage date
  const lastUsedDate = usage.length > 0
    ? formatDate(usage[0]?.date || usage[0]?.created_at)
    : null;

  const listContent = (
    <Box sx={{ flex: 1, overflowY: "auto" }}>
      {loading && (
        <Box sx={{ textAlign: "center", py: 4 }}>
          <Typography sx={{ color: COLOR.text4 }}>加载中...</Typography>
        </Box>
      )}

      {!loading && !item && (
        <Box sx={{ textAlign: "center", py: 4 }}>
          <Typography sx={{ color: COLOR.text4 }}>未找到该知识条目</Typography>
        </Box>
      )}

      {!loading && item && (
        <>
          {/* ── Rule content card ── */}
          <Box sx={{ bgcolor: COLOR.white, borderBottom: `0.5px solid ${COLOR.border}` }}>
            {/* Title + source avatar */}
            <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, px: 2, pt: 2, pb: 1 }}>
              {cfg && (
                <IconBadge config={cfg.badge} />
              )}
              <Typography sx={{ fontSize: TYPE.heading.fontSize, fontWeight: TYPE.heading.fontWeight, color: COLOR.text1, flex: 1 }}>
                {title}
              </Typography>
            </Box>

            {/* Full text */}
            <Box sx={{ px: 2, pb: 1.5 }}>
              <Typography sx={{
                fontSize: TYPE.secondary.fontSize, fontWeight: TYPE.secondary.fontWeight,
                color: COLOR.text2, lineHeight: 1.6,
                whiteSpace: "pre-wrap", wordBreak: "break-word",
              }}>
                {bodyText || text}
              </Typography>
            </Box>

            {/* Meta row */}
            <Box sx={{ display: "flex", alignItems: "center", flexWrap: "wrap", gap: 1, px: 2, pb: 0.5 }}>
              <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4 }}>
                {sourceLabel}
              </Typography>
              {category && (
                <Box sx={{
                  fontSize: TYPE.micro.fontSize, fontWeight: 500,
                  color: COLOR.accent, bgcolor: COLOR.accentLight,
                  px: 1, py: 0.5, borderRadius: RADIUS.sm,
                }}>
                  {category}
                </Box>
              )}
              {item.created_at && (
                <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4 }}>
                  {formatDate(item.created_at)}
                </Typography>
              )}
            </Box>
            {lastUsedDate && (
              <Box sx={{ px: 2, pb: 1.5 }}>
                <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4 }}>
                  最近 {lastUsedDate}
                </Typography>
              </Box>
            )}

            {/* Rule health stats — unified StatColumn bar matching KnowledgeSubpage list header */}
            {!isPersonaProp && (
              <Box sx={{ display: "flex", py: 1.5, px: 2, bgcolor: COLOR.white, borderTop: `0.5px solid ${COLOR.borderLight}`, borderBottom: `0.5px solid ${COLOR.borderLight}`, mt: 1 }}>
                <StatColumn
                  value={health?.cited_count ?? 0}
                  label="引用"
                />
                <Box sx={{ width: "0.5px", bgcolor: COLOR.borderLight }} />
                <StatColumn value={health?.accepted_count ?? 0} label="采纳" color={COLOR.primary} />
                <Box sx={{ width: "0.5px", bgcolor: COLOR.borderLight }} />
                <StatColumn value={health?.edited_count ?? 0} label="编辑" color={COLOR.warning} />
                <Box sx={{ width: "0.5px", bgcolor: COLOR.borderLight }} />
                <StatColumn value={health?.rejected_count ?? 0} label="拒绝" color={COLOR.danger} />
              </Box>
            )}

            {/* Source footer: source_url link + file_path button */}
            {(item.source_url || item.file_path) && (
              <Box sx={{ px: 2, pb: 2, display: "flex", alignItems: "center", flexWrap: "wrap", gap: 1 }}>
                {item.source_url && (
                  <Typography variant="caption" sx={{ color: COLOR.text4 }}>
                    {"来源: "}
                    <Box
                      component="a"
                      href={item.source_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      sx={{ color: COLOR.text4, textDecoration: "underline", "&:hover": { color: COLOR.text3 } }}
                    >
                      {item.source_url.length > 40 ? item.source_url.slice(0, 40) + "…" : item.source_url} ↗
                    </Box>
                  </Typography>
                )}
                {item.file_path && (
                  <Button
                    variant="outlined"
                    size="small"
                    sx={{ fontSize: TYPE.caption.fontSize, textTransform: "none", minHeight: 28, py: 0, px: 1.5 }}
                    onClick={() => {
                      const base = import.meta.env.VITE_API_BASE_URL || "";
                      window.open(
                        `${base}/api/manage/knowledge/file/${encodeURIComponent(item.file_path)}?doctor_id=${encodeURIComponent(doctorId)}`,
                        "_blank"
                      );
                    }}
                  >
                    查看原文
                  </Button>
                )}
              </Box>
            )}
          </Box>

          {/* ── Citation history section ── */}
          {usage.length > 0 && (
            <>
              <SectionLabel sx={{ pt: 2 }}>引用记录</SectionLabel>
              <Box sx={{ bgcolor: COLOR.white, borderTop: `0.5px solid ${COLOR.border}`, borderBottom: `0.5px solid ${COLOR.border}` }}>
                {usage.map((u, idx) => {
                  const typeCfg = getUsageTypeConfig(u.type || u.usage_context);
                  const ctx = u.type || u.usage_context;
                  // Pick navigation target by context — diagnosis → review page,
                  // draft/chat → patient page. Only make clickable when we have a target.
                  let onRowClick;
                  if (ctx === "diagnosis" && u.record_id) {
                    onRowClick = () => navigate(`${dp("review")}/${u.record_id}`);
                  } else if (u.patient_id) {
                    onRowClick = () => navigate(`${dp("patients")}/${u.patient_id}`);
                  }
                  return (
                    <ListCard
                      key={u.id || idx}
                      avatar={
                        <Box sx={{
                          width: 36, height: 36, borderRadius: RADIUS.md, flexShrink: 0,
                          bgcolor: COLOR.surfaceAlt,
                          display: "flex", alignItems: "center", justifyContent: "center",
                          fontSize: 16,
                        }}>
                          {typeCfg.icon}
                        </Box>
                      }
                      title={`${u.patient_name || "患者"} \u00B7 ${u.context || typeCfg.label}`}
                      subtitle={u.detail || ""}
                      right={
                        <Typography sx={{ fontSize: TYPE.caption.fontSize, color: COLOR.text4, whiteSpace: "nowrap" }}>
                          {formatDate(u.date || u.created_at)}
                        </Typography>
                      }
                      onClick={onRowClick}
                      chevron={!!onRowClick}
                      sx={idx === usage.length - 1 ? { borderBottom: "none" } : {}}
                    />
                  );
                })}
              </Box>
            </>
          )}

          {usage.length === 0 && !loading && (
            <>
              <SectionLabel sx={{ pt: 2 }}>引用记录</SectionLabel>
              <Box sx={{ bgcolor: COLOR.white, borderTop: `0.5px solid ${COLOR.border}`, borderBottom: `0.5px solid ${COLOR.border}`, py: 3, textAlign: "center" }}>
                <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text4 }}>
                  暂无引用记录
                </Typography>
              </Box>
            </>
          )}

          {/* ── Bottom action bar ── */}
          <Box sx={{
            display: "flex", justifyContent: "space-between", alignItems: "center",
            px: 2, py: 2, mt: 2,
          }}>
            {item?.category !== "persona" ? (
            <Typography
              onClick={() => setDeleteOpen(true)}
              sx={{
                fontSize: TYPE.body.fontSize, color: COLOR.danger,
                cursor: "pointer", fontWeight: 500,
                "&:active": { opacity: 0.6 },
              }}
            >
              删除
            </Typography>
            ) : <Box />}
            <Typography
              onClick={handleEditOpen}
              sx={{
                fontSize: TYPE.body.fontSize, color: COLOR.primary,
                cursor: "pointer", fontWeight: 500,
                "&:active": { opacity: 0.6 },
              }}
            >
              编辑
            </Typography>
          </Box>

          <Box sx={{ height: 40 }} />
        </>
      )}
    </Box>
  );

  return (
    <>
      <PageSkeleton
        title="知识详情"
        onBack={onBack}
        isMobile={isMobile}
        listPane={listContent}
      />
      <SheetDialog
        open={editOpen}
        onClose={() => setEditOpen(false)}
        title={isPersona ? "编辑AI风格" : "编辑知识"}
        desktopMaxWidth={480}
        mobileMaxHeight="90vh"
        footer={
          <DialogFooter
            onCancel={() => setEditOpen(false)}
            onConfirm={handleSaveEdit}
            confirmLabel="保存"
            confirmDisabled={isPersona ? false : (!editText.trim() || saving)}
            confirmLoading={saving}
            confirmLoadingLabel="保存中…"
          />
        }
      >
        {isPersona ? (
          <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
            {PERSONA_FIELDS.map((f) => (
              <Box key={f.key}>
                <Typography sx={{ fontSize: TYPE.secondary.fontSize, fontWeight: 600, color: COLOR.text1, mb: 0.5 }}>
                  {f.label}
                </Typography>
                <TextField
                  fullWidth
                  multiline
                  minRows={2}
                  maxRows={4}
                  size="small"
                  placeholder={f.hint}
                  value={personaFields[f.key] || ""}
                  onChange={(e) => setPersonaFields(prev => ({ ...prev, [f.key]: e.target.value }))}
                  sx={{ "& .MuiOutlinedInput-root": { borderRadius: RADIUS.md } }}
                />
              </Box>
            ))}
          </Box>
        ) : (
          <>
            <TextField
              fullWidth
              multiline
              minRows={8}
              maxRows={16}
              size="small"
              value={editText}
              onChange={(e) => setEditText(e.target.value)}
              sx={{ "& .MuiOutlinedInput-root": { borderRadius: RADIUS.md } }}
            />
            <Typography sx={{ fontSize: TYPE.caption.fontSize, color: editText.length > 3000 ? COLOR.danger : COLOR.text4, mt: 0.5, textAlign: "right" }}>
              {editText.length}/3000
            </Typography>
          </>
        )}
      </SheetDialog>
      <ConfirmDialog
        open={deleteOpen}
        onClose={() => setDeleteOpen(false)}
        onCancel={() => setDeleteOpen(false)}
        onConfirm={handleDelete}
        title="确认删除"
        message="删除后该知识将不再影响 AI 行为，确定要删除吗？"
        cancelLabel="保留"
        confirmLabel="删除"
        confirmTone="danger"
      />
    </>
  );
}
