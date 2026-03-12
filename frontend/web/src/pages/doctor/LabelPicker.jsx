/**
 * 患者标签选择器：支持浮层选择已有标签，或新建并指定颜色后直接关联患者。
 */
import { useState } from "react";
import {
  Alert, Box, Button, CircularProgress, Divider, Paper, Stack, TextField, Typography,
} from "@mui/material";
import { createLabel, assignLabelToPatient } from "../../api";
import { LABEL_PRESET_COLORS } from "./constants";

function LabelRow({ label, isAssigned, onAssign }) {
  return (
    <Box onClick={() => onAssign(label)}
      sx={{
        display: "flex", alignItems: "center", gap: 1, px: 1, py: 1,
        borderRadius: 1, cursor: "pointer", minHeight: 40,
        bgcolor: isAssigned ? "#f0fdf4" : "transparent",
        "&:hover": { bgcolor: "#f1f5f9" },
      }}>
      <Box sx={{ width: 12, height: 12, borderRadius: "50%", bgcolor: label.color || "#94a3b8", flexShrink: 0 }} />
      <Typography variant="caption">{label.name}</Typography>
      {isAssigned && (
        <Typography variant="caption" color="success.main" sx={{ ml: "auto" }}>✓</Typography>
      )}
    </Box>
  );
}

function ColorPicker({ value, onChange }) {
  return (
    <Stack direction="row" spacing={0.5} sx={{ mb: 1 }}>
      {LABEL_PRESET_COLORS.map((c) => (
        <Box key={c} onClick={() => onChange(c)}
          sx={{
            width: 20, height: 20, borderRadius: "50%", bgcolor: c, cursor: "pointer",
            border: value === c ? "2px solid #1e293b" : "2px solid transparent",
          }} />
      ))}
    </Stack>
  );
}

async function createAndAssign({ doctorId, patientId, newLabelName, newLabelColor, setCreatingLabel, setCreateError, onLabelsChange, setNewLabelName, onClose }) {
  if (!newLabelName.trim()) return;
  setCreatingLabel(true);
  setCreateError("");
  try {
    const created = await createLabel({ doctorId, name: newLabelName.trim(), color: newLabelColor });
    await assignLabelToPatient({ doctorId, patientId, labelId: created.id });
    onLabelsChange((prev) => [...prev, { id: created.id, name: created.name, color: created.color }]);
    setNewLabelName("");
    onClose();
  } catch (e) {
    setCreateError(e.message || "标签创建失败");
  } finally {
    setCreatingLabel(false);
  }
}

function LabelPickerBody({ allLabels, patientLabels, labelError, createError, newLabelName, setNewLabelName, newLabelColor, setNewLabelColor, creatingLabel, onAssign, onClose, onCreateAndAssign }) {
  return (
    <Paper elevation={4} sx={{ position: "absolute", top: "110%", left: 0, zIndex: 1300, p: 2, minWidth: 240, borderRadius: 2 }}>
      <Typography variant="caption" sx={{ fontWeight: 700, display: "block", mb: 1 }}>选择标签</Typography>
      {(labelError || createError) && (
        <Alert severity="error" sx={{ mb: 1, py: 0 }}>{labelError || createError}</Alert>
      )}
      <Stack spacing={0.5} sx={{ mb: 1.5, maxHeight: "50vh", overflowY: "auto" }}>
        {allLabels.length === 0 && <Typography variant="caption" color="text.secondary">暂无标签</Typography>}
        {allLabels.map((l) => (
          <LabelRow key={l.id} label={l} isAssigned={patientLabels.some((pl) => pl.id === l.id)} onAssign={onAssign} />
        ))}
      </Stack>
      <Divider sx={{ mb: 1 }} />
      <Typography variant="caption" sx={{ fontWeight: 700, display: "block", mb: 0.5 }}>新建标签</Typography>
      <TextField size="small" fullWidth placeholder="标签名称" value={newLabelName}
        onChange={(e) => setNewLabelName(e.target.value)} sx={{ mb: 0.8 }} />
      <ColorPicker value={newLabelColor} onChange={setNewLabelColor} />
      <Stack direction="row" spacing={1}>
        <Button size="small" variant="contained" disabled={!newLabelName.trim() || creatingLabel} onClick={onCreateAndAssign} sx={{ flex: 1 }}>
          {creatingLabel ? <CircularProgress size={14} /> : "创建并添加"}
        </Button>
        <Button size="small" color="inherit" onClick={onClose}>关闭</Button>
      </Stack>
    </Paper>
  );
}

export default function LabelPicker({ doctorId, patientId, allLabels, patientLabels, labelError, onAssign, onClose, onLabelsChange }) {
  const [creatingLabel, setCreatingLabel] = useState(false);
  const [newLabelName, setNewLabelName] = useState("");
  const [newLabelColor, setNewLabelColor] = useState(LABEL_PRESET_COLORS[0]);
  const [createError, setCreateError] = useState("");
  const handleCreateAndAssign = () => !creatingLabel && createAndAssign({
    doctorId, patientId, newLabelName, newLabelColor,
    setCreatingLabel, setCreateError, onLabelsChange, setNewLabelName, onClose,
  });
  return (
    <LabelPickerBody allLabels={allLabels} patientLabels={patientLabels} labelError={labelError}
      createError={createError} newLabelName={newLabelName} setNewLabelName={setNewLabelName}
      newLabelColor={newLabelColor} setNewLabelColor={setNewLabelColor} creatingLabel={creatingLabel}
      onAssign={onAssign} onClose={onClose} onCreateAndAssign={handleCreateAndAssign} />
  );
}
