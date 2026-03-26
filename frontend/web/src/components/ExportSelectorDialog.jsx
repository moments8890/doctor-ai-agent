/**
 * ExportSelectorDialog: bottom-sheet dialog for choosing which sections
 * to include in the patient PDF export.
 */
import { useState } from "react";
import { Box, Dialog, Typography } from "@mui/material";
import useMediaQuery from "@mui/material/useMediaQuery";
import { useTheme } from "@mui/material/styles";
import { TYPE, ICON } from "../theme";

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
        border: checked ? "none" : "1.5px solid #ccc",
        bgcolor: checked ? "#07C160" : "transparent",
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
          <path d="M1.5 5L5 8.5L11.5 1.5" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      )}
    </Box>
  );
}

export default function ExportSelectorDialog({ open, onClose, patientId, patientName, onExport }) {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down("sm"));
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
    <Dialog
      open={open}
      onClose={onClose}
      PaperProps={{
        sx: isMobile
          ? {
              position: "fixed",
              bottom: 0,
              left: 0,
              right: 0,
              m: 0,
              borderRadius: "12px 12px 0 0",
              width: "100%",
              maxHeight: "80vh",
            }
          : { borderRadius: 2, minWidth: 360, maxWidth: 420 },
      }}
      sx={isMobile ? { "& .MuiDialog-container": { alignItems: "flex-end" } } : {}}
    >
      <Box sx={{ p: 0 }}>
        {/* Handle bar */}
        {isMobile && (
          <Box sx={{ display: "flex", justifyContent: "center", pt: 1.2, pb: 0.5 }}>
            <Box sx={{ width: 36, height: 4, borderRadius: 2, bgcolor: "#d9d9d9" }} />
          </Box>
        )}

        {/* Title */}
        <Box sx={{ px: 2.5, pt: isMobile ? 1 : 2.5, pb: 1.5 }}>
          <Typography sx={{ fontWeight: 600, fontSize: TYPE.title.fontSize, textAlign: "center" }}>
            导出PDF — 选择内容
          </Typography>
          {patientName && (
            <Typography sx={{ fontSize: TYPE.caption.fontSize, color: "#999", textAlign: "center", mt: 0.3 }}>
              患者：{patientName}
            </Typography>
          )}
        </Box>

        {/* Section list */}
        <Box sx={{ px: 2.5 }}>
          {SECTIONS.map((sec, idx) => (
            <Box key={sec.key}>
              {idx > 0 && <Box sx={{ height: "0.5px", bgcolor: "#f0f0f0" }} />}
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
                <Typography sx={{ fontSize: TYPE.action.fontSize, color: "#333", flex: 1 }}>
                  {sec.label}
                </Typography>
                {sec.disabled && (
                  <Typography sx={{ fontSize: TYPE.micro.fontSize, color: "#bbb" }}>必选</Typography>
                )}
              </Box>

              {/* Visit range pills */}
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
                        bgcolor: visitRange === opt.value ? "#07C160" : "#f0f0f0",
                        color: visitRange === opt.value ? "#fff" : "#666",
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
        </Box>

        {/* Generate button */}
        <Box sx={{ px: 2.5, pt: 2, pb: isMobile ? 3.5 : 2.5 }}>
          <Box
            onClick={handleGenerate}
            sx={{
              textAlign: "center",
              height: 44,
              lineHeight: "44px",
              borderRadius: "4px",
              fontSize: TYPE.action.fontSize,
              fontWeight: 600,
              cursor: "pointer",
              bgcolor: "#07C160",
              color: "#fff",
              "&:active": { opacity: 0.7 },
            }}
          >
            生成PDF
          </Box>
        </Box>
      </Box>
    </Dialog>
  );
}
