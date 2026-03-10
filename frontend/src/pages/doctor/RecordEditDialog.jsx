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
import { updateRecord } from "../../api";
import { RECORD_FIELDS } from "./constants";

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
  return (
    <>
      <DialogContent dividers>
        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
        <Stack spacing={2}>
          {RECORD_FIELDS.map(({ key, label }) => (
            <TextField key={key} label={label} multiline={key === "content"}
              minRows={key === "content" ? 5 : 1} maxRows={key === "content" ? 16 : 1}
              size="small" fullWidth value={form[key] || ""}
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
      init.tags = Array.isArray(record.tags) ? [...record.tags] : [];
      setForm(init); setError("");
    }
  }, [record]);

  async function handleSave() {
    setSaving(true); setError("");
    try { const saved = await updateRecord(doctorId, record.id, { ...form, tags: form.tags }); onSaved(saved); onClose(); }
    catch (e) { setError(e.message || "保存失败"); } finally { setSaving(false); }
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
