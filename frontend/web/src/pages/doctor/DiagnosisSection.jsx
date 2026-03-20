/**
 * DiagnosisSection — displays AI diagnosis results for a patient record.
 *
 * Sections (in order):
 *  1. 您的类似病例 (case_references) — prominent, light-green background
 *  2. 危险信号 (red_flags) — orange/red warning banner
 *  3. 鉴别诊断 (ai_output.differentials) — with ✓ ✗ confirm/reject buttons
 *  4. 检查建议 (ai_output.workup) — with ✓ ✗ confirm/reject buttons
 *  5. 治疗方向 (ai_output.treatment) — with ✓ ✗ confirm/reject buttons
 *  6. 免责声明 — static disclaimer text
 *
 * Props:
 *  - diagnosis: API response object (ai_output, doctor_decisions, red_flags,
 *               case_references, status)
 *  - onDecide(type, index, decision): callback for confirm/reject actions
 */
import { Box, Stack, Typography } from "@mui/material";

/* ─── Helpers ─────────────────────────────────────────────────────────────── */

/**
 * Returns the decision string ("confirmed" | "rejected" | undefined) for a
 * given item type and index from the doctor_decisions map.
 */
function getDecision(doctorDecisions, type, index) {
  if (!doctorDecisions || !doctorDecisions[type]) return undefined;
  return doctorDecisions[type][String(index)];
}

/* ─── Sub-components ──────────────────────────────────────────────────────── */

function SectionHeader({ children }) {
  return (
    <Typography sx={{ fontSize: 14, fontWeight: 600, color: "#333", mb: 1 }}>
      {children}
    </Typography>
  );
}

/**
 * ConfidenceBadge — shows 低 / 中 / 高 with matching colour.
 */
function ConfidenceBadge({ confidence }) {
  const colorMap = { 高: "#07C160", 中: "#ff9500", 低: "#999" };
  const color = colorMap[confidence] ?? "#999";
  return (
    <Box
      component="span"
      sx={{
        display: "inline-block",
        px: 0.8,
        py: 0.1,
        borderRadius: "4px",
        border: `1px solid ${color}`,
        color,
        fontSize: 11,
        fontWeight: 600,
        lineHeight: 1.6,
        ml: 0.8,
        flexShrink: 0,
      }}
    >
      {confidence}
    </Box>
  );
}

/**
 * UrgencyBadge — urgency label for workup items.
 */
function UrgencyBadge({ urgency }) {
  const colorMap = { 急诊: "#FA5151", 紧急: "#e65100", 常规: "#07C160" };
  const color = colorMap[urgency] ?? "#999";
  return (
    <Box
      component="span"
      sx={{
        display: "inline-block",
        px: 0.8,
        py: 0.1,
        borderRadius: "4px",
        border: `1px solid ${color}`,
        color,
        fontSize: 11,
        fontWeight: 600,
        lineHeight: 1.6,
        ml: 0.8,
        flexShrink: 0,
      }}
    >
      {urgency}
    </Box>
  );
}

/**
 * InterventionBadge — intervention type for treatment items.
 */
function InterventionBadge({ intervention }) {
  const colorMap = {
    手术: "#FA5151",
    转诊: "#e65100",
    药物: "#07C160",
    观察: "#999",
  };
  const color = colorMap[intervention] ?? "#666";
  return (
    <Box
      component="span"
      sx={{
        display: "inline-block",
        px: 0.8,
        py: 0.1,
        borderRadius: "4px",
        border: `1px solid ${color}`,
        color,
        fontSize: 11,
        fontWeight: 600,
        lineHeight: 1.6,
        ml: 0.8,
        flexShrink: 0,
      }}
    >
      {intervention}
    </Box>
  );
}

/**
 * DecideButtons — ✓ ✗ confirm/reject button pair.
 * Visual state is derived from the current decision value.
 */
function DecideButtons({ decision, onConfirm, onReject }) {
  const isConfirmed = decision === "confirmed";
  const isRejected = decision === "rejected";

  return (
    <Stack direction="row" spacing={0.5} sx={{ flexShrink: 0, ml: 1 }}>
      <Box
        onClick={onConfirm}
        sx={{
          width: 28,
          height: 28,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          borderRadius: "50%",
          bgcolor: isConfirmed ? "#07C160" : "#f0f0f0",
          color: isConfirmed ? "#fff" : "#666",
          fontSize: 14,
          fontWeight: 700,
          cursor: "pointer",
          transition: "all 0.15s",
          "&:active": { opacity: 0.7 },
        }}
      >
        ✓
      </Box>
      <Box
        onClick={onReject}
        sx={{
          width: 28,
          height: 28,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          borderRadius: "50%",
          bgcolor: isRejected ? "#FA5151" : "#f0f0f0",
          color: isRejected ? "#fff" : "#666",
          fontSize: 14,
          fontWeight: 700,
          cursor: "pointer",
          transition: "all 0.15s",
          "&:active": { opacity: 0.7 },
        }}
      >
        ✗
      </Box>
    </Stack>
  );
}

/**
 * Wrapper card for a reviewable item row.
 * Applies green left border when confirmed, red strikethrough when rejected.
 */
function ItemCard({ decision, children }) {
  const isConfirmed = decision === "confirmed";
  const isRejected = decision === "rejected";

  return (
    <Box
      sx={{
        mb: 1,
        p: "10px 12px",
        bgcolor: "#f7f7f7",
        borderRadius: "6px",
        borderLeft: isConfirmed
          ? "3px solid #07C160"
          : isRejected
          ? "3px solid #FA5151"
          : "3px solid transparent",
        opacity: isRejected ? 0.6 : 1,
        textDecoration: isRejected ? "line-through" : "none",
      }}
    >
      {children}
    </Box>
  );
}

/* ─── Section 1: 您的类似病例 ─────────────────────────────────────────────── */

function CaseReferencesSection({ caseReferences }) {
  if (!caseReferences || caseReferences.length === 0) return null;

  return (
    <Box sx={{ bgcolor: "#fff", borderRadius: 2, p: 2.5, mb: 1 }}>
      <SectionHeader>📋 您的类似病例</SectionHeader>
      <Stack spacing={1}>
        {caseReferences.map((ref, i) => (
          <Box
            key={i}
            sx={{
              p: "10px 12px",
              bgcolor: "#f0f7f0",
              borderRadius: "6px",
              borderLeft: "3px solid #07C160",
            }}
          >
            {/* Similarity + chief complaint → diagnosis */}
            <Stack direction="row" alignItems="center" flexWrap="wrap" gap={0.5}>
              <Box
                sx={{
                  display: "inline-block",
                  px: 0.8,
                  py: 0.1,
                  borderRadius: "4px",
                  bgcolor: "#07C160",
                  color: "#fff",
                  fontSize: 11,
                  fontWeight: 700,
                  lineHeight: 1.6,
                  flexShrink: 0,
                }}
              >
                相似度 {typeof ref.similarity === "number"
                  ? `${Math.round(ref.similarity * 100)}%`
                  : ref.similarity}
              </Box>
              <Typography
                component="span"
                sx={{ fontSize: 13, fontWeight: 600, color: "#333" }}
              >
                {ref.chief_complaint}
              </Typography>
              {ref.final_diagnosis && (
                <>
                  <Typography
                    component="span"
                    sx={{ fontSize: 13, color: "#999" }}
                  >
                    →
                  </Typography>
                  <Typography
                    component="span"
                    sx={{ fontSize: 13, fontWeight: 600, color: "#07C160" }}
                  >
                    {ref.final_diagnosis}
                  </Typography>
                </>
              )}
            </Stack>

            {/* Treatment + outcome */}
            <Stack direction="row" spacing={2} sx={{ mt: 0.6 }} flexWrap="wrap">
              {ref.treatment && (
                <Typography sx={{ fontSize: 12, color: "#555" }}>
                  治疗: {ref.treatment}
                </Typography>
              )}
              {ref.outcome && (
                <Typography sx={{ fontSize: 12, color: "#555" }}>
                  转归: {ref.outcome}
                </Typography>
              )}
            </Stack>
          </Box>
        ))}
      </Stack>
    </Box>
  );
}

/* ─── Section 2: 危险信号 ──────────────────────────────────────────────────── */

function RedFlagsSection({ redFlags }) {
  if (!redFlags || redFlags.length === 0) return null;

  return (
    <Box
      sx={{
        bgcolor: "#fff3e0",
        borderRadius: 2,
        p: 2.5,
        mb: 1,
        border: "1px solid #ffcc80",
      }}
    >
      <SectionHeader>
        <Box component="span" sx={{ color: "#e65100" }}>
          ⚠️ 危险信号
        </Box>
      </SectionHeader>
      <Stack spacing={0.5}>
        {redFlags.map((flag, i) => (
          <Stack key={i} direction="row" spacing={0.8} alignItems="flex-start">
            <Typography sx={{ fontSize: 13, color: "#e65100", flexShrink: 0 }}>
              •
            </Typography>
            <Typography sx={{ fontSize: 13, color: "#e65100", lineHeight: 1.6 }}>
              {flag}
            </Typography>
          </Stack>
        ))}
      </Stack>
    </Box>
  );
}

/* ─── Section 3: 鉴别诊断 ──────────────────────────────────────────────────── */

function DifferentialsSection({ differentials, doctorDecisions, onDecide }) {
  if (!differentials || differentials.length === 0) return null;

  return (
    <Box sx={{ bgcolor: "#fff", borderRadius: 2, p: 2.5, mb: 1 }}>
      <SectionHeader>鉴别诊断</SectionHeader>
      {differentials.map((item, i) => {
        const decision = getDecision(doctorDecisions, "differentials", i);
        return (
          <ItemCard key={i} decision={decision}>
            <Stack direction="row" alignItems="flex-start">
              <Box sx={{ flex: 1, minWidth: 0 }}>
                <Stack direction="row" alignItems="center" flexWrap="wrap">
                  <Typography
                    sx={{ fontSize: 13, fontWeight: 600, color: "#333" }}
                  >
                    {i + 1}. {item.condition}
                  </Typography>
                  {item.confidence && (
                    <ConfidenceBadge confidence={item.confidence} />
                  )}
                </Stack>
                {item.reasoning && (
                  <Typography
                    sx={{ fontSize: 12, color: "#555", mt: 0.4, lineHeight: 1.6 }}
                  >
                    {item.reasoning}
                  </Typography>
                )}
              </Box>
              <DecideButtons
                decision={decision}
                onConfirm={() => onDecide("differentials", i, "confirmed")}
                onReject={() => onDecide("differentials", i, "rejected")}
              />
            </Stack>
          </ItemCard>
        );
      })}
    </Box>
  );
}

/* ─── Section 4: 检查建议 ──────────────────────────────────────────────────── */

function WorkupSection({ workup, doctorDecisions, onDecide }) {
  if (!workup || workup.length === 0) return null;

  return (
    <Box sx={{ bgcolor: "#fff", borderRadius: 2, p: 2.5, mb: 1 }}>
      <SectionHeader>检查建议</SectionHeader>
      {workup.map((item, i) => {
        const decision = getDecision(doctorDecisions, "workup", i);
        return (
          <ItemCard key={i} decision={decision}>
            <Stack direction="row" alignItems="flex-start">
              <Box sx={{ flex: 1, minWidth: 0 }}>
                <Stack direction="row" alignItems="center" flexWrap="wrap">
                  <Typography
                    sx={{ fontSize: 13, fontWeight: 600, color: "#333" }}
                  >
                    {item.test}
                  </Typography>
                  {item.urgency && <UrgencyBadge urgency={item.urgency} />}
                </Stack>
                {item.rationale && (
                  <Typography
                    sx={{ fontSize: 12, color: "#555", mt: 0.4, lineHeight: 1.6 }}
                  >
                    {item.rationale}
                  </Typography>
                )}
              </Box>
              <DecideButtons
                decision={decision}
                onConfirm={() => onDecide("workup", i, "confirmed")}
                onReject={() => onDecide("workup", i, "rejected")}
              />
            </Stack>
          </ItemCard>
        );
      })}
    </Box>
  );
}

/* ─── Section 5: 治疗方向 ──────────────────────────────────────────────────── */

function TreatmentSection({ treatment, doctorDecisions, onDecide }) {
  if (!treatment || treatment.length === 0) return null;

  return (
    <Box sx={{ bgcolor: "#fff", borderRadius: 2, p: 2.5, mb: 1 }}>
      <SectionHeader>治疗方向</SectionHeader>
      {treatment.map((item, i) => {
        const decision = getDecision(doctorDecisions, "treatment", i);
        return (
          <ItemCard key={i} decision={decision}>
            <Stack direction="row" alignItems="flex-start">
              <Box sx={{ flex: 1, minWidth: 0 }}>
                <Stack direction="row" alignItems="center" flexWrap="wrap">
                  <Typography
                    sx={{ fontSize: 13, fontWeight: 600, color: "#333" }}
                  >
                    {item.drug_class}
                  </Typography>
                  {item.intervention && (
                    <InterventionBadge intervention={item.intervention} />
                  )}
                </Stack>
                {item.description && (
                  <Typography
                    sx={{ fontSize: 12, color: "#555", mt: 0.4, lineHeight: 1.6 }}
                  >
                    {item.description}
                  </Typography>
                )}
              </Box>
              <DecideButtons
                decision={decision}
                onConfirm={() => onDecide("treatment", i, "confirmed")}
                onReject={() => onDecide("treatment", i, "rejected")}
              />
            </Stack>
          </ItemCard>
        );
      })}
    </Box>
  );
}

/* ─── Main export ──────────────────────────────────────────────────────────── */

export default function DiagnosisSection({ diagnosis, onDecide }) {
  if (!diagnosis) return null;

  const aiOutput = diagnosis.ai_output || {};
  const doctorDecisions = diagnosis.doctor_decisions || {};
  const redFlags = diagnosis.red_flags || aiOutput.red_flags || [];
  const caseReferences = diagnosis.case_references || [];

  function handleDecide(type, index, decision) {
    onDecide?.(type, index, decision);
  }

  return (
    <Box>
      {/* Section header card */}
      <Box sx={{ bgcolor: "#fff", borderRadius: 2, p: "12px 16px", mb: 1,
        borderLeft: "3px solid #07C160" }}>
        <Typography sx={{ fontSize: 15, fontWeight: 700, color: "#333" }}>
          ⭐ AI 诊断建议
        </Typography>
      </Box>

      {/* 1. Similar cases — FIRST, prominent */}
      <CaseReferencesSection caseReferences={caseReferences} />

      {/* 2. Red flags — SECOND */}
      <RedFlagsSection redFlags={redFlags} />

      {/* 3. Differentials */}
      <DifferentialsSection
        differentials={aiOutput.differentials}
        doctorDecisions={doctorDecisions}
        onDecide={handleDecide}
      />

      {/* 4. Workup */}
      <WorkupSection
        workup={aiOutput.workup}
        doctorDecisions={doctorDecisions}
        onDecide={handleDecide}
      />

      {/* 5. Treatment */}
      <TreatmentSection
        treatment={aiOutput.treatment}
        doctorDecisions={doctorDecisions}
        onDecide={handleDecide}
      />

      {/* 6. Disclaimer */}
      <Box sx={{ px: 1, pb: 1 }}>
        <Typography sx={{ fontSize: 11, color: "#bbb", textAlign: "center" }}>
          AI建议仅供参考，最终诊断由医生决定
        </Typography>
      </Box>
    </Box>
  );
}
