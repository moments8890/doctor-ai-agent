/**
 * ExportSelectorDialog: bottom-sheet dialog for choosing which sections
 * to include in the patient PDF export.
 */
import { useState } from "react";
import { Box, Typography } from "@mui/material";
import { TYPE, ICON, COLOR } from "../theme";
import AppButton from "./AppButton";
import SheetDialog from "./SheetDialog";

const SECTIONS = [
  { key: "basicInfo",    label: "基本信息",   defaultChecked: true,  disabled: true },
  { key: "diagnosis",    label: "诊断信息",   defaultChecked: true,  disabled: false },
  { key: "visits",       label: "就诊记录",   defaultChecked: true,  disabled: false, hasRange: true },
  { key: "prescriptions", label: "处方记录",  defaultChecked: true,  disabled: false },
  { key: "labReports",   label: "检验报告",   defaultChecked: false, disabled: false },
  { key: "allergies",    label: "过敏信息",   defaultChecked: true,  disabled: false },
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
    if (onExport) onExport({ ...sections, visitRange });
  }

  return (
    <SheetDialog
      open={open}
      onClose={onClose}
      title="导出PDF — 选择内容"
      subtitle={patientName ? `患者：${patientName}` : undefined}
      desktopMinWidth={360}
      desktopMaxWidth={420}
      footer={
        <Box sx={{ display: "grid", gap: 0.5, gridTemplateColumns: "repeat(2, minmax(0, 1fr))" }}>
          <AppButton variant="secondary" size="md" fullWidth onClick={onClose}>
            取消
          </AppButton>
          <AppButton variant="primary" size="md" fullWidth onClick={handleGenerate}>
            生成PDF
          </AppButton>
        </Box>
      }
    >
      {SECTIONS.map((sec, idx) => (
        <Box key={sec.key}>
          {idx > 0 && <Box sx={{ height: "0.5px", bgcolor: COLOR.borderLight }} />}
          <Box
            onClick={() => toggleSection(sec.key)}
            sx={{
              display: "flex",
              alignItems: "center",
              gap: 1.2,
              py: 1.4,
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
            <Box sx={{ display: "flex", gap: 0.8, pb: 1.2, pl: 4.2 }}>
              {VISIT_RANGE_OPTS.map((opt) => (
                <Box
                  key={opt.value}
                  onClick={() => setVisitRange(opt.value)}
                  sx={{
                    px: 1.4,
                    py: 0.35,
                    borderRadius: "4px",
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
