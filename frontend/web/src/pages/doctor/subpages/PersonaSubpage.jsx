/**
 * PersonaSubpage -- per-field rule management for doctor AI persona.
 *
 * Shows 5 field sections (reply_style, closing, structure, avoid, edits)
 * with individual rules that can be added, edited, or deleted.
 *
 * @see /doctor/settings/persona
 */
import { useState } from "react";
import { Box, IconButton, TextField, Typography } from "@mui/material";
import AddCircleOutlineIcon from "@mui/icons-material/AddCircleOutline";
import EditOutlinedIcon from "@mui/icons-material/EditOutlined";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import TuneOutlinedIcon from "@mui/icons-material/TuneOutlined";
import { TYPE, COLOR, RADIUS, ICON } from "../../../theme";
import PageSkeleton from "../../../components/PageSkeleton";
import AppButton from "../../../components/AppButton";
import SectionLabel from "../../../components/SectionLabel";
import SectionLoading from "../../../components/SectionLoading";
import SheetDialog from "../../../components/SheetDialog";
import DialogFooter from "../../../components/DialogFooter";
import ConfirmDialog from "../../../components/ConfirmDialog";
import StatColumn from "../../../components/StatColumn";
import { useQueryClient } from "@tanstack/react-query";
import { QK } from "../../../lib/queryKeys";
import { useApi } from "../../../api/ApiContext";
import { usePersona, usePersonaPending } from "../../../lib/doctorQueries";
import { useAppNavigate } from "../../../hooks/useAppNavigate";
import { dp } from "../../../utils/doctorBasePath";

/* ── Field config ── */

const FIELD_CONFIG = [
  { key: "reply_style", label: "回复风格", hint: "例：口语化回复，像微信聊天" },
  { key: "closing", label: "常用结尾语", hint: "例：有问题随时联系我" },
  { key: "structure", label: "回复结构", hint: "例：先给结论再简短解释" },
  { key: "avoid", label: "回避内容", hint: "例：不主动展开罕见风险" },
  { key: "edits", label: "常见修改", hint: "例：把建议改成直接指令" },
];

const SOURCE_LABELS = {
  manual: "手动",
  doctor: "手动",
  onboarding: "引导",
  edit: "学习",
  teach: "示例",
  migrated: "迁移",
};

/* ── Main ── */

export default function PersonaSubpage({ doctorId, onBack, isMobile }) {
  const api = useApi();
  const queryClient = useQueryClient();
  const navigate = useAppNavigate();
  const { data: persona, isLoading: loading } = usePersona();
  const { data: pendingData } = usePersonaPending();
  const pendingCount = pendingData?.count || 0;

  const fields = persona?.fields || {};

  // Add dialog
  const [addOpen, setAddOpen] = useState(false);
  const [addField, setAddField] = useState(null);
  const [addText, setAddText] = useState("");
  const [addSaving, setAddSaving] = useState(false);

  // Edit dialog
  const [editOpen, setEditOpen] = useState(false);
  const [editField, setEditField] = useState(null);
  const [editRuleId, setEditRuleId] = useState(null);
  const [editText, setEditText] = useState("");
  const [editSaving, setEditSaving] = useState(false);

  // Delete confirm
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleteField, setDeleteField] = useState(null);
  const [deleteRuleId, setDeleteRuleId] = useState(null);

  function invalidate() {
    queryClient.invalidateQueries({ queryKey: QK.persona(doctorId) });
  }

  function openAdd(fieldKey) {
    setAddField(fieldKey);
    setAddText("");
    setAddOpen(true);
  }

  async function handleAdd() {
    const trimmed = addText.trim();
    if (!trimmed || !addField) return;
    setAddSaving(true);
    try {
      await api.addPersonaRule(doctorId, addField, trimmed);
      invalidate();
      setAddOpen(false);
    } catch {
      // stay open on error
    } finally {
      setAddSaving(false);
    }
  }

  function openEdit(fieldKey, rule) {
    setEditField(fieldKey);
    setEditRuleId(rule.id);
    setEditText(rule.text);
    setEditOpen(true);
  }

  async function handleEdit() {
    const trimmed = editText.trim();
    if (!trimmed || !editField || !editRuleId) return;
    setEditSaving(true);
    try {
      await api.updatePersonaRule(doctorId, editField, editRuleId, trimmed);
      invalidate();
      setEditOpen(false);
    } catch {
      // stay open on error
    } finally {
      setEditSaving(false);
    }
  }

  function openDelete(fieldKey, ruleId) {
    setDeleteField(fieldKey);
    setDeleteRuleId(ruleId);
    setDeleteOpen(true);
  }

  async function handleDelete() {
    if (!deleteField || !deleteRuleId) return;
    setDeleteOpen(false);
    try {
      await api.deletePersonaRule(doctorId, deleteField, deleteRuleId);
      invalidate();
    } catch {
      // silent
    }
  }

  // Compute stats
  const totalRules = FIELD_CONFIG.reduce(
    (sum, f) => sum + (fields[f.key]?.length || 0),
    0,
  );
  const editsLearned = (fields.edits || []).filter(
    (r) => r.source === "edit",
  ).length;

  const addFieldConfig = FIELD_CONFIG.find((f) => f.key === addField);

  const listContent = (
    <Box sx={{ flex: 1, overflowY: "auto" }}>
      {pendingCount > 0 && (
        <Box
          onClick={() => navigate(dp("settings/persona/pending"))}
          sx={{
            mx: 2, mt: 1.5,
            bgcolor: COLOR.warningLight,
            px: 1.5, py: 1.25,
            borderRadius: RADIUS.md,
            border: `0.5px solid ${COLOR.amberBorder}`,
            display: "flex", justifyContent: "space-between", alignItems: "center",
            cursor: "pointer",
          }}
        >
          <Typography sx={{ fontSize: TYPE.body.fontSize, fontWeight: 500, color: COLOR.amberText }}>
            AI发现 {pendingCount} 条待确认
          </Typography>
          <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.amberText }}>
            查看 ›
          </Typography>
        </Box>
      )}

      {!loading && !persona?.onboarded && totalRules === 0 && (
        <Box sx={{ mx: 2, mt: 1.5, mb: 0.5 }}>
          <Box sx={{
            bgcolor: COLOR.primaryLight,
            borderRadius: RADIUS.md,
            border: `0.5px solid ${COLOR.primaryBorder}`,
            p: 1.5,
          }}>
            <Typography sx={{ fontSize: TYPE.body.fontSize, fontWeight: 600, color: COLOR.primaryText, mb: 0.5 }}>
              还没有人设
            </Typography>
            <Typography sx={{ fontSize: TYPE.secondary.fontSize, color: COLOR.text3, mb: 1.25 }}>
              用3个场景快速配置你的AI回复风格
            </Typography>
            <AppButton
              variant="primary"
              size="sm"
              onClick={() => navigate(dp("settings/persona/onboarding"))}
            >
              开始初始化
            </AppButton>
          </Box>
        </Box>
      )}

      {loading && <SectionLoading rows={5} />}

      {!loading && (
        <>
          {FIELD_CONFIG.map((fc) => {
            const rules = fields[fc.key] || [];
            return (
              <Box key={fc.key}>
                {/* Field header */}
                <Box
                  sx={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    px: 2,
                    pt: 2,
                    pb: 0.5,
                  }}
                >
                  <Typography
                    sx={{
                      fontSize: TYPE.heading.fontSize,
                      fontWeight: TYPE.heading.fontWeight,
                      color: COLOR.text1,
                    }}
                  >
                    {fc.label}
                  </Typography>
                  <IconButton
                    size="small"
                    onClick={() => openAdd(fc.key)}
                    sx={{ color: COLOR.primary }}
                  >
                    <AddCircleOutlineIcon sx={{ fontSize: ICON.md }} />
                  </IconButton>
                </Box>

                {/* Rules list */}
                <Box
                  sx={{
                    bgcolor: COLOR.white,
                    borderTop: `0.5px solid ${COLOR.border}`,
                    borderBottom: `0.5px solid ${COLOR.border}`,
                  }}
                >
                  {rules.length === 0 && (
                    <Box sx={{ px: 2, py: 2 }}>
                      <Typography
                        sx={{
                          fontSize: TYPE.secondary.fontSize,
                          color: COLOR.text4,
                          fontStyle: "italic",
                        }}
                      >
                        {fc.hint}
                      </Typography>
                    </Box>
                  )}

                  {rules.map((rule, idx) => (
                    <Box
                      key={rule.id}
                      sx={{
                        display: "flex",
                        alignItems: "flex-start",
                        gap: 1,
                        px: 2,
                        py: 1.5,
                        borderBottom:
                          idx < rules.length - 1
                            ? `0.5px solid ${COLOR.borderLight}`
                            : "none",
                      }}
                    >
                      {/* Rule text + meta */}
                      <Box sx={{ flex: 1, minWidth: 0 }}>
                        <Typography
                          sx={{
                            fontSize: TYPE.body.fontSize,
                            color: COLOR.text1,
                            wordBreak: "break-word",
                          }}
                        >
                          {rule.text}
                        </Typography>
                        <Box
                          sx={{
                            display: "flex",
                            alignItems: "center",
                            gap: 1,
                            mt: 0.5,
                          }}
                        >
                          <Box
                            sx={{
                              fontSize: TYPE.micro.fontSize,
                              fontWeight: 500,
                              color: COLOR.accent,
                              bgcolor: COLOR.accentLight,
                              px: 0.75,
                              py: 0.25,
                              borderRadius: RADIUS.sm,
                            }}
                          >
                            {SOURCE_LABELS[rule.source] || rule.source || "手动"}
                          </Box>
                          {(rule.usage_count ?? 0) > 0 && (
                            <Typography
                              sx={{
                                fontSize: TYPE.caption.fontSize,
                                color: COLOR.text4,
                              }}
                            >
                              使用 {rule.usage_count} 次
                            </Typography>
                          )}
                        </Box>
                      </Box>

                      {/* Actions */}
                      <Box
                        sx={{
                          display: "flex",
                          alignItems: "center",
                          gap: 0.5,
                          flexShrink: 0,
                          pt: 0.25,
                        }}
                      >
                        <IconButton
                          size="small"
                          onClick={() => openEdit(fc.key, rule)}
                          sx={{ color: COLOR.text4 }}
                        >
                          <EditOutlinedIcon sx={{ fontSize: ICON.sm }} />
                        </IconButton>
                        <IconButton
                          size="small"
                          onClick={() => openDelete(fc.key, rule.id)}
                          sx={{ color: COLOR.text4 }}
                        >
                          <DeleteOutlineIcon sx={{ fontSize: ICON.sm }} />
                        </IconButton>
                      </Box>
                    </Box>
                  ))}
                </Box>
              </Box>
            );
          })}

          {/* Stats row */}
          <SectionLabel sx={{ pt: 2 }}>统计</SectionLabel>
          <Box
            sx={{
              bgcolor: COLOR.white,
              borderTop: `0.5px solid ${COLOR.border}`,
              borderBottom: `0.5px solid ${COLOR.border}`,
              display: "flex",
              py: 2,
            }}
          >
            <StatColumn value={totalRules} label="规则总数" />
            <StatColumn value={editsLearned} label="学习获得" />
          </Box>

          <Box sx={{ height: 40 }} />
        </>
      )}
    </Box>
  );

  return (
    <>
      <PageSkeleton
        title="AI 人设"
        onBack={onBack}
        mobileView={isMobile}
        listPane={listContent}
      />

      {/* Add rule dialog */}
      <SheetDialog
        open={addOpen}
        onClose={() => setAddOpen(false)}
        title={`添加${addFieldConfig?.label || "规则"}`}
        desktopMaxWidth={420}
        footer={
          <DialogFooter
            onCancel={() => setAddOpen(false)}
            onConfirm={handleAdd}
            confirmLabel="添加"
            confirmDisabled={!addText.trim() || addSaving}
            confirmLoading={addSaving}
            confirmLoadingLabel="添加中…"
          />
        }
      >
        <TextField
          fullWidth
          multiline
          minRows={3}
          maxRows={6}
          size="small"
          placeholder={addFieldConfig?.hint || ""}
          value={addText}
          onChange={(e) => setAddText(e.target.value)}
          autoFocus
          sx={{ "& .MuiOutlinedInput-root": { borderRadius: RADIUS.md } }}
        />
      </SheetDialog>

      {/* Edit rule dialog */}
      <SheetDialog
        open={editOpen}
        onClose={() => setEditOpen(false)}
        title="编辑规则"
        desktopMaxWidth={420}
        footer={
          <DialogFooter
            onCancel={() => setEditOpen(false)}
            onConfirm={handleEdit}
            confirmLabel="保存"
            confirmDisabled={!editText.trim() || editSaving}
            confirmLoading={editSaving}
            confirmLoadingLabel="保存中…"
          />
        }
      >
        <TextField
          fullWidth
          multiline
          minRows={3}
          maxRows={6}
          size="small"
          value={editText}
          onChange={(e) => setEditText(e.target.value)}
          autoFocus
          sx={{ "& .MuiOutlinedInput-root": { borderRadius: RADIUS.md } }}
        />
      </SheetDialog>

      {/* Delete confirmation */}
      <ConfirmDialog
        open={deleteOpen}
        onClose={() => setDeleteOpen(false)}
        onCancel={() => setDeleteOpen(false)}
        onConfirm={handleDelete}
        title="确认删除"
        message="删除后该规则将不再影响 AI 行为，确定要删除吗？"
        cancelLabel="保留"
        confirmLabel="删除"
        confirmTone="danger"
      />
    </>
  );
}
