/**
 * RecordDetail — full detail view for a single patient record.
 *
 * Extracted from PatientPage.jsx. Fetches record detail via API using
 * recordId prop, then renders:
 *  - Summary section (diagnosis status, medications, follow-up, lifestyle)
 *  - Expandable structured fields (14 SOAP fields)
 *  - Raw content fallback when no structured data
 *
 * Props:
 *  - recordId: string | number — the record to fetch
 *  - token: string — patient auth token
 *  - onBack: () => void — navigate back to records list
 */

import { useEffect, useState } from "react";
import { Box, CircularProgress, Typography } from "@mui/material";
import { usePatientApi } from "../../../api/PatientApiContext";
import SubpageHeader from "../../../components/SubpageHeader";
import SectionLabel from "../../../components/SectionLabel";
import StatusBadge from "../../../components/StatusBadge";
import SectionLoading from "../../../components/SectionLoading";
import { TYPE, COLOR, RADIUS } from "../../../theme";
import {
  RECORD_TYPE_LABEL,
  FIELD_LABELS,
  FIELD_ORDER,
  DIAGNOSIS_STATUS_LABELS,
  formatDate,
} from "../constants";

const DIAG_STATUS_COLORS = {
  pending: COLOR.warning,
  completed: COLOR.accent,
  confirmed: COLOR.success,
  failed: COLOR.danger,
};

export default function RecordDetail({ recordId, token, onBack }) {
  const { getPatientRecordDetail } = usePatientApi();
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(true);
  const [showFullRecord, setShowFullRecord] = useState(true);

  useEffect(() => {
    if (!recordId || !token) { setLoading(false); return; }
    setLoading(true);
    getPatientRecordDetail(token, recordId)
      .then(data => setDetail(data))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [recordId, token, getPatientRecordDetail]);

  const structured = detail?.structured || {};
  const typeLabel = RECORD_TYPE_LABEL[detail?.record_type] || detail?.record_type || "";
  const diagStatus = detail?.diagnosis_status;
  const treatmentPlan = detail?.treatment_plan;
  const hasSummary = diagStatus || treatmentPlan;

  return (
    <Box sx={{ flex: 1, display: "flex", flexDirection: "column" }}>
      <SubpageHeader title={typeLabel} onBack={onBack} />
      <Box sx={{ flex: 1, overflowY: "auto", bgcolor: COLOR.surfaceAlt, px: 1.5, py: 1 }}>

        {/* Loading spinner */}
        {loading && (
          <SectionLoading />
        )}

        {/* -- Action summary sections -- */}
        {!loading && hasSummary && (
          <>
            {/* Diagnosis */}
            {diagStatus && (
              <>
                <SectionLabel>诊断</SectionLabel>
                <Box sx={{ bgcolor: COLOR.white, borderRadius: RADIUS.sm, px: 1.5, py: 1 }}>
                  <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                    {(diagStatus === "confirmed" || diagStatus === "completed") && structured?.diagnosis ? (
                      <Typography sx={{ ...TYPE.body, color: COLOR.text1, flex: 1 }}>
                        {structured.diagnosis}
                      </Typography>
                    ) : (
                      <Typography sx={{ ...TYPE.body, color: COLOR.text3, flex: 1 }}>
                        {DIAGNOSIS_STATUS_LABELS[diagStatus] || diagStatus}
                      </Typography>
                    )}
                    <StatusBadge
                      label={DIAGNOSIS_STATUS_LABELS[diagStatus] || diagStatus}
                      colorMap={DIAG_STATUS_COLORS}
                      fallbackColor={COLOR.text4}
                    />
                  </Box>
                </Box>
              </>
            )}

            {/* Medications */}
            {treatmentPlan?.medications?.length > 0 && (
              <>
                <SectionLabel>用药方案</SectionLabel>
                <Box sx={{ bgcolor: COLOR.white, borderRadius: RADIUS.sm, px: 1.5 }}>
                  {treatmentPlan.medications.map((med, i) => (
                    <Box key={i} sx={{
                      display: "flex", justifyContent: "space-between", alignItems: "center",
                      py: 1,
                      ...(i < treatmentPlan.medications.length - 1 && { borderBottom: `0.5px solid ${COLOR.borderLight}` }),
                    }}>
                      <Typography sx={{ ...TYPE.body, color: COLOR.text1 }}>
                        {med.name || med.drug_class || med}
                      </Typography>
                      {med.dosage && (
                        <Typography sx={{ ...TYPE.secondary, color: COLOR.text3, flexShrink: 0, ml: 1 }}>
                          {med.dosage}
                        </Typography>
                      )}
                    </Box>
                  ))}
                </Box>
              </>
            )}

            {/* Follow-up */}
            {treatmentPlan?.follow_up && (
              <>
                <SectionLabel>随访计划</SectionLabel>
                <Box sx={{ bgcolor: COLOR.white, borderRadius: RADIUS.sm, px: 1.5, py: 1 }}>
                  <Typography sx={{ ...TYPE.body, color: COLOR.text1, lineHeight: 1.6 }}>
                    {treatmentPlan.follow_up}
                  </Typography>
                </Box>
              </>
            )}

            {/* Lifestyle */}
            {treatmentPlan?.lifestyle && (
              <>
                <SectionLabel>生活建议</SectionLabel>
                <Box sx={{ bgcolor: COLOR.white, borderRadius: RADIUS.sm, px: 1.5, py: 1 }}>
                  <Typography sx={{ ...TYPE.body, color: COLOR.text1, lineHeight: 1.6 }}>
                    {treatmentPlan.lifestyle}
                  </Typography>
                </Box>
              </>
            )}

            {/* Expand/collapse toggle */}
            <Box
              onClick={() => setShowFullRecord(prev => !prev)}
              sx={{ display: "flex", justifyContent: "center", py: 1.5, cursor: "pointer", userSelect: "none" }}
            >
              <Typography sx={{ ...TYPE.secondary, color: COLOR.primary, fontWeight: 500 }}>
                {showFullRecord ? "收起 ▴" : "查看完整病历 ▾"}
              </Typography>
            </Box>
          </>
        )}

        {/* -- Full structured record -- */}
        {!loading && (!hasSummary || showFullRecord) && (
          <Box sx={{ bgcolor: COLOR.white, borderRadius: RADIUS.sm, px: 1.5, py: 0.5 }}>
            {FIELD_ORDER.map((key) => {
              const val = structured[key];
              if (!val) return null;
              return (
                <Box key={key} sx={{ py: 0.5, borderBottom: `0.5px solid ${COLOR.borderLight}`, display: "flex", alignItems: "baseline", gap: 0.5 }}>
                  <Typography sx={{ ...TYPE.secondary, color: COLOR.text4, flexShrink: 0 }}>{FIELD_LABELS[key] || key}：</Typography>
                  <Typography sx={{ ...TYPE.body, color: COLOR.text1, lineHeight: 1.6, flex: 1 }}>{val}</Typography>
                </Box>
              );
            })}
            {/* Raw content fallback if no structured */}
            {!Object.values(structured).some(Boolean) && detail?.content && (
              <Typography sx={{ ...TYPE.body, color: COLOR.text2, lineHeight: 1.8, whiteSpace: "pre-wrap", py: 1 }}>
                {detail.content}
              </Typography>
            )}
          </Box>
        )}

        {!loading && detail && (
          <Typography sx={{ ...TYPE.caption, color: COLOR.text4, mt: 2, textAlign: "center", pb: 1 }}>
            {formatDate(detail.created_at)}
          </Typography>
        )}
      </Box>
    </Box>
  );
}
