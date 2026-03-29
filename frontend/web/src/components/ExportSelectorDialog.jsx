/**
 * ExportSelectorDialog: bottom-sheet dialog for choosing which sections
 * to include in the patient PDF export.
 */
import { useState } from "react";
import { Box, Typography } from "@mui/material";
import { TYPE, ICON, COLOR, RADIUS } from "../theme";
import SheetDialog from "./SheetDialog";
import DialogFooter from "./DialogFooter";

const SECTIONS = [
  { key: "basicInfo",    apiKey: "basic",         label: "基本信息",   defaultChecked: true,  disabled: true },
  { key: "diagnosis",    apiKey: "diagnosis",      label: "诊断信息",   defaultChecked: true,  disabled: false },
  { key: "visits",       apiKey: "visits",         label: "就诊记录",   defaultChecked: true,  disabled: false, hasRange: true },
  { key: "prescriptions", apiKey: "prescriptions", label: "处方记录",  defaultChecked: true,  disabled: false },
  { key: "labReports",   apiKey: "lab_reports",    label: "检验报告",   defaultChecked: false, disabled: false },
  { key: "allergies",    apiKey: "allergies",      label: "过敏信息",   defaultChecked: true,  disabled: false },
];

const VISIT_RANGE_OPTS = [
  { value: "5",   label: "最近5次" },
  { value: "10",  label: "最近10次" },
  { value: "all", label: "全部" },
];

function buildInitialSections() {
  const obj = {};
  SECTIONS.forEach((s) => { obj[s.key] = s.defaultChecked; });
  return obj;
}

function CheckCircle({ checked, disabled }) {
  return (
    <Box
      sx={{
        width: 22,
        height: 22,
        borderRadius: "50%",
        border: checked ? "none" : `1.5px solid ${COLOR.text4}`,
        bgcolor: checked ? COLOR.primary : "transparent",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        flexShrink: 0,
        opacity: disabled ? 0.5 : 1,
        transition: "background-color 0.15s",
      }}
    >
      {checked && (
        <svg width="13" height="10" viewBox="0 0 13 10" fill="none">
          <path d="M1.5 5L5 8.5L11.5 1.5" stroke={COLOR.white} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      )}
    </Box>
  );
}

export default function ExportSelectorDialog({ open, onClose, patientId, patientName, onExport }) {
  const [sections, setSections] = useState(buildInitialSections);
  const [visitRange, setVisitRange] = useState("5");

  function toggleSection(key) {
    const def = SECTIONS.find((s) => s.key === key);
    if (def?.disabled) return;
    setSections((prev) => ({ ...prev, [key]: !prev[key] }));
  }

  function handleGenerate() {
    const selectedSections = SECTIONS
      .filter((s) => sections[s.key])
      .map((s) => s.apiKey);
    const range = sections.visits ? visitRange : undefined;
    if (onExport) onExport({ sections: selectedSections, visitRange: range });
  }

  return (
    <SheetDialog
      open={open}
      onClose={onClose}
      title="导出PDF — 选择内容"
      subtitle={patientName ? `患者：${patientName}` : undefined}
      desktopMinWidth={360}
      desktopMaxWidth={420}
      footer={<DialogFooter onCancel={onClose} onConfirm={handleGenerate} confirmLabel="生成PDF" />}
    >
      {SECTIONS.map((sec, idx) => (
        <Box key={sec.key}>
          {idx > 0 && <Box sx={{ height: "0.5px", bgcolor: COLOR.borderLight }} />}
          <Box
            onClick={() => toggleSection(sec.key)}
            sx={{
              display: "flex",
              alignItems: "center",
              gap: 1,
              py: 1.5,
              cursor: sec.disabled ? "default" : "pointer",
              "&:active": sec.disabled ? {} : { opacity: 0.6 },
            }}
          >
            <CheckCircle checked={sections[sec.key]} disabled={sec.disabled} />
            <Typography sx={{ fontSize: TYPE.action.fontSize, color: COLOR.text2, flex: 1 }}>
              {sec.label}
            </Typography>
            {sec.disabled && (
              <Typography sx={{ fontSize: TYPE.micro.fontSize, color: COLOR.text4 }}>必选</Typography>
            )}
          </Box>

          {sec.hasRange && sections[sec.key] && (
            <Box sx={{ display: "flex", gap: 1, pb: 1, pl: 4 }}>
              {VISIT_RANGE_OPTS.map((opt) => (
                <Box
                  key={opt.value}
                  onClick={() => setVisitRange(opt.value)}
                  sx={{
                    px: 1.5,
                    py: 0.5,
                    borderRadius: RADIUS.sm,
                    cursor: "pointer",
                    fontSize: TYPE.caption.fontSize,
                    bgcolor: visitRange === opt.value ? COLOR.primary : COLOR.borderLight,
                    color: visitRange === opt.value ? COLOR.white : COLOR.text3,
                    fontWeight: visitRange === opt.value ? 600 : 400,
                    "&:active": { opacity: 0.7 },
                  }}
                >
                  {opt.label}
                </Box>
              ))}
            </Box>
          )}
        </Box>
      ))}
    </SheetDialog>
  );
}
