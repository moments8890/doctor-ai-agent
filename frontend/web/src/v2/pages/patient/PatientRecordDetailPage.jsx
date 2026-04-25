/**
 * @route /patient/records/:id
 * Read-only patient-facing record detail. Doctor card pattern — gray pageContainer
 * with floating white Card sections. Field names match the actual
 * PatientRecordDetailOut payload shape, NOT made-up names.
 */
import { NavBar, Tag } from "antd-mobile";
import { LeftOutline } from "antd-mobile-icons";
import { useNavigate } from "react-router-dom";
import { APP, FONT } from "../../theme";
import { pageContainer, navBarStyle, scrollable } from "../../layouts";
import { Card, LoadingCenter, EmptyState } from "../../components";
import { usePatientRecordDetail } from "../../../lib/patientQueries";

const TYPE_LABEL = {
  visit: "门诊记录",
  dictation: "语音记录",
  import: "导入记录",
  interview_summary: "预问诊",
};

const STATUS_LABEL = {
  completed: { text: "待审核", color: "primary" },
  confirmed: { text: "已确认", color: "success" },
};

function formatDate(iso) {
  if (!iso) return "";
  return new Date(iso).toLocaleDateString("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit" });
}

function Section({ title, children }) {
  return (
    <Card style={{ marginTop: 8 }}>
      <div style={{ padding: "12px 14px" }}>
        <div style={{ fontSize: FONT.sm, fontWeight: 600, color: APP.text4, marginBottom: 6 }}>
          {title}
        </div>
        <div style={{ fontSize: FONT.base, color: APP.text1, whiteSpace: "pre-wrap", lineHeight: 1.6 }}>
          {children}
        </div>
      </div>
    </Card>
  );
}

function SubField({ label, value }) {
  return (
    <div style={{ marginBottom: 6 }}>
      <div style={{ fontSize: FONT.sm, color: APP.text4 }}>{label}</div>
      <div style={{ fontSize: FONT.base, color: APP.text1, whiteSpace: "pre-wrap", lineHeight: 1.5 }}>
        {value}
      </div>
    </div>
  );
}

export default function PatientRecordDetailPage({ recordId }) {
  const navigate = useNavigate();
  const { data: rec, isLoading, isError, refetch } = usePatientRecordDetail(recordId);

  return (
    <div style={pageContainer}>
      <NavBar backArrow={<LeftOutline />} onBack={() => navigate(-1)} style={navBarStyle}>
        病历详情
      </NavBar>
      <div style={scrollable}>
        {isLoading && <LoadingCenter />}
        {isError && (
          <EmptyState
            title="加载失败"
            description="请稍后重试"
            action="重试"
            onAction={refetch}
          />
        )}
        {rec && (
          <>
            {/* Header card — type tag + date + diagnosis status tag (when set) */}
            <Card style={{ marginTop: 8 }}>
              <div style={{ padding: "12px 14px", display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                <Tag color="primary">{TYPE_LABEL[rec.record_type] || rec.record_type}</Tag>
                <span style={{ fontSize: FONT.sm, color: APP.text4 }}>{formatDate(rec.created_at)}</span>
                {rec.diagnosis_status && STATUS_LABEL[rec.diagnosis_status] && (
                  <Tag color={STATUS_LABEL[rec.diagnosis_status].color}>
                    {STATUS_LABEL[rec.diagnosis_status].text}
                  </Tag>
                )}
              </div>
            </Card>

            {/* 主诉 / 现病史 — separate cards, only when non-empty */}
            {rec.structured?.chief_complaint && <Section title="主诉">{rec.structured.chief_complaint}</Section>}
            {rec.structured?.present_illness && <Section title="现病史">{rec.structured.present_illness}</Section>}

            {/* History combined card — 既往史 / 过敏史 / 个人史 / 家族史 — omit entirely if all empty */}
            {(rec.structured?.past_history || rec.structured?.allergy_history ||
              rec.structured?.personal_history || rec.structured?.family_history) && (
              <Card style={{ marginTop: 8 }}>
                <div style={{ padding: "12px 14px" }}>
                  {rec.structured.past_history && <SubField label="既往史" value={rec.structured.past_history} />}
                  {rec.structured.allergy_history && <SubField label="过敏史" value={rec.structured.allergy_history} />}
                  {rec.structured.personal_history && <SubField label="个人史" value={rec.structured.personal_history} />}
                  {rec.structured.family_history && <SubField label="家族史" value={rec.structured.family_history} />}
                </div>
              </Card>
            )}

            {/* Treatment plan card — only when present */}
            {rec.treatment_plan && (
              <Card style={{ marginTop: 8 }}>
                <div style={{ padding: "12px 14px" }}>
                  <div style={{ fontSize: FONT.sm, fontWeight: 600, color: APP.text4, marginBottom: 8 }}>
                    诊断与用药
                  </div>
                  {Array.isArray(rec.treatment_plan.medications) && rec.treatment_plan.medications.length > 0 && (
                    <div style={{ marginBottom: 8 }}>
                      {rec.treatment_plan.medications.map((m, i) => (
                        <div key={i} style={{ fontSize: FONT.base, color: APP.text1, marginBottom: 4 }}>
                          • {m.name || ""}{m.dose ? ` · ${m.dose}` : ""}{m.frequency ? ` · ${m.frequency}` : ""}
                        </div>
                      ))}
                    </div>
                  )}
                  {rec.treatment_plan.follow_up && (
                    <SubField label="随访建议" value={rec.treatment_plan.follow_up} />
                  )}
                  {rec.treatment_plan.lifestyle && (
                    <SubField label="生活方式" value={rec.treatment_plan.lifestyle} />
                  )}
                </div>
              </Card>
            )}

            <div style={{ height: 32 }} />
          </>
        )}
      </div>
    </div>
  );
}
