/**
 * 病历编辑对话框：支持修改病历内容、类型和标签，并提交保存。
 */
import { useEffect, useState } from "react";
import {
  Alert, Box, Button, Chip, Dialog, DialogActions, DialogContent,
  DialogTitle, Stack, TextField, Typography,
} from "@mui/material";
import useMediaQuery from "@mui/material/useMediaQuery";
import { useTheme } from "@mui/material/styles";
import { updateRecord } from "../api";
import { RECORD_FIELDS, RECORD_STRUCTURED_FIELDS } from "../pages/doctor/constants";

function TagsEditor({ tags, onChange }) {
  return (
    <Box>
      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>
        标签
      </Typography>
      <Stack direction="row" flexWrap="wrap" spacing={0.5} sx={{ mb: 0.5 }}>
        {(tags || []).map((tag, i) => (
          <Chip key={i} label={tag} size="small"
            onDelete={() => onChange(tags.filter((_, j) => j !== i))} />
        ))}
      </Stack>
      <TextField
        size="small"
        placeholder="输入标签后按 Enter 添加"
        onKeyDown={(e) => {
          if (e.key === "Enter" && e.target.value.trim()) {
            e.preventDefault();
            onChange([...(tags || []), e.target.value.trim()]);
            e.target.value = "";
          }
        }}
      />
    </Box>
  );
}

function RecordEditForm({ form, setForm, error, saving, onClose, onSave }) {
  // Structured fields from record.structured (NHC per-field)
  const structured = form._structured || {};
  const hasStructured = Object.values(structured).some((v) => v);

  function setStructuredField(key, value) {
    setForm((f) => ({ ...f, _structured: { ...(f._structured || {}), [key]: value } }));
  }

  return (
    <>
      <DialogContent dividers>
        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
        <Stack spacing={2}>
          {/* Per-field NHC editing (if structured data exists) */}
          {hasStructured && RECORD_STRUCTURED_FIELDS.map(({ key, label }) => {
            const val = structured[key] || "";
            if (!val && !["chief_complaint", "diagnosis", "treatment_plan"].includes(key)) return null;
            return (
              <TextField key={key} label={label} multiline minRows={1} maxRows={8}
                size="small" fullWidth value={val}
                onChange={(e) => setStructuredField(key, e.target.value)} />
            );
          })}
          {/* Fallback: raw content blob (if no structured data) */}
          {!hasStructured && (
            <TextField label="临床笔记" multiline minRows={5} maxRows={16}
              size="small" fullWidth value={form.content || ""}
              onChange={(e) => setForm((f) => ({ ...f, content: e.target.value }))} />
          )}
          {/* Record type + tags */}
          {RECORD_FIELDS.map(({ key, label }) => (
            <TextField key={key} label={label} size="small" fullWidth value={form[key] || ""}
              onChange={(e) => setForm((f) => ({ ...f, [key]: e.target.value }))} />
          ))}
          <TagsEditor tags={form.tags} onChange={(tags) => setForm((f) => ({ ...f, tags }))} />
        </Stack>
      </DialogContent>
      <DialogActions sx={{ gap: 1, px: 2, pb: 2 }}>
        <Button onClick={onClose} disabled={saving}>取消</Button>
        <Button variant="contained" onClick={onSave} disabled={saving}>{saving ? "保存中…" : "保存"}</Button>
      </DialogActions>
    </>
  );
}

export default function RecordEditDialog({ record, doctorId, open, onClose, onSaved }) {
  const [form, setForm] = useState({});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down("sm"));

  useEffect(() => {
    if (record) {
      const init = {};
      RECORD_FIELDS.forEach(({ key }) => { init[key] = record[key] || ""; });
      init.content = record.content || "";
      init.tags = Array.isArray(record.tags) ? [...record.tags] : [];
      // Populate structured fields from record.structured (API returns NHC fields here)
      const s = record.structured || {};
      init._structured = {};
      RECORD_STRUCTURED_FIELDS.forEach(({ key }) => { init._structured[key] = s[key] || record[key] || ""; });
      setForm(init); setError("");
    }
  }, [record]);

  async function handleSave() {
    setSaving(true); setError("");
    try {
      // Build payload: structured fields go as top-level keys, content rebuilt from fields
      const payload = { record_type: form.record_type, tags: form.tags };
      const s = form._structured || {};
      const hasStructured = Object.values(s).some((v) => v);
      if (hasStructured) {
        // Send each NHC field as a top-level key for the backend to update individual columns
        RECORD_STRUCTURED_FIELDS.forEach(({ key }) => { if (s[key]) payload[key] = s[key]; });
      } else {
        payload.content = form.content;
      }
      const saved = await updateRecord(doctorId, record.id, payload);
      onSaved(saved);
      onClose();
    } catch (e) { setError(e.message || "保存失败"); } finally { setSaving(false); }
  }

  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth fullScreen={isMobile}>
      <DialogTitle sx={{ fontWeight: 700 }}>
        编辑病历{" "}<Typography component="span" variant="body2" color="text.secondary">#{record?.id}</Typography>
      </DialogTitle>
      <RecordEditForm form={form} setForm={setForm} error={error} saving={saving} onClose={onClose} onSave={handleSave} />
    </Dialog>
  );
}
