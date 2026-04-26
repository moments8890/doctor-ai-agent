/**
 * @route /doctor/settings/templates
 *
 * TemplateSubpage v2 — report template management.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { NavBar, Button, Dialog, SpinLoading, Toast } from "antd-mobile";
import { FileOutline } from "antd-mobile-icons";
import UploadFileOutlinedIcon from "@mui/icons-material/UploadFileOutlined";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import { useNavigate } from "react-router-dom";
import { useApi } from "../../../../api/ApiContext";
import { useDoctorStore } from "../../../../store/doctorStore";
import { APP, FONT, RADIUS, ICON } from "../../../theme";
import { pageContainer, navBarStyle, scrollable } from "../../../layouts";
import SubpageBackHome from "../../../components/SubpageBackHome";

const STANDARD_TEMPLATE_FIELDS = [
  { key: "department", label: "科别", desc: "就诊科室名称" },
  { key: "chief_complaint", label: "主诉", desc: "患者就诊的主要症状及持续时间" },
  { key: "present_illness", label: "现病史", desc: "症状起病、发展、演变的详细过程" },
  { key: "past_history", label: "既往史", desc: "既往疾病、手术、外伤、输血史等" },
  { key: "allergy_history", label: "过敏史", desc: "药物及其他过敏情况" },
  { key: "personal_history", label: "个人史", desc: "吸烟、饮酒、职业暴露等" },
  { key: "marital_reproductive", label: "婚育史", desc: "婚姻、生育情况" },
  { key: "family_history", label: "家族史", desc: "家族遗传病及相关疾病史" },
  { key: "physical_exam", label: "体格检查", desc: "生命体征及系统体格检查结果" },
  { key: "specialist_exam", label: "专科检查", desc: "专科相关的体格检查结果" },
  { key: "auxiliary_exam", label: "辅助检查", desc: "实验室检查、影像学检查结果" },
  { key: "diagnosis", label: "初步诊断", desc: "根据病史和检查做出的初步判断" },
  { key: "treatment_plan", label: "治疗方案", desc: "药物治疗、手术方案、康复计划等" },
  { key: "orders_followup", label: "医嘱及随访", desc: "出院/门诊医嘱、复查安排、注意事项" },
];

function SectionHeader({ title }) {
  return (
    <div
      style={{
        padding: "0 20px",
        margin: "16px 0 8px",
        fontSize: FONT.base,
        color: APP.text3,
        fontWeight: 500,
      }}
    >
      {title}
    </div>
  );
}

function Card({ children }) {
  return (
    <div
      style={{
        background: APP.surface,
        margin: "0 12px",
        borderRadius: RADIUS.lg,
        overflow: "hidden",
      }}
    >
      {children}
    </div>
  );
}

function Row({ Icon, iconColor, iconBg, title, subtitle, onClick, extra, isFirst, disabled }) {
  return (
    <div
      onClick={!disabled && onClick ? onClick : undefined}
      style={{
        display: "flex",
        alignItems: "center",
        gap: 12,
        padding: "14px 16px",
        cursor: !disabled && onClick ? "pointer" : "default",
        borderTop: isFirst ? "none" : `0.5px solid ${APP.borderLight}`,
        opacity: disabled ? 0.5 : 1,
      }}
    >
      {Icon && (
        <div
          style={{
            width: 36,
            height: 36,
            borderRadius: RADIUS.md,
            background: iconBg,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            flexShrink: 0,
          }}
        >
          <Icon sx={{ fontSize: ICON.sm, color: iconColor }} />
        </div>
      )}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: FONT.base, fontWeight: 600, color: APP.text1 }}>
          {title}
        </div>
        {subtitle && (
          <div style={{ fontSize: FONT.sm, color: APP.text4, marginTop: 2 }}>
            {subtitle}
          </div>
        )}
      </div>
      {extra}
    </div>
  );
}

function useTemplateState(doctorId) {
  const { getTemplateStatus, uploadTemplate, deleteTemplate } = useApi();
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const fileRef = useRef(null);

  const loadStatus = useCallback(() => {
    setLoading(true);
    getTemplateStatus(doctorId)
      .then(setStatus)
      .catch(() => setStatus(null))
      .finally(() => setLoading(false));
  }, [doctorId]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { loadStatus(); }, [loadStatus]);

  async function handleUpload(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      await uploadTemplate(doctorId, file);
      Toast.show({ content: `模板已上传（${file.name}）`, position: "bottom" });
      loadStatus();
    } catch (err) {
      Toast.show({ content: err.message || "上传失败", position: "bottom" });
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  async function handleDelete() {
    setDeleting(true);
    try {
      await deleteTemplate(doctorId);
      Toast.show({ content: "模板已删除，将使用默认格式", position: "bottom" });
      loadStatus();
    } catch (err) {
      Toast.show({ content: err.message || "删除失败", position: "bottom" });
    } finally {
      setDeleting(false);
    }
  }

  return { status, loading, uploading, deleting, fileRef, handleUpload, handleDelete };
}

export default function TemplateSubpage() {
  const navigate = useNavigate();
  const { doctorId } = useDoctorStore();
  const { status, loading, uploading, deleting, fileRef, handleUpload, handleDelete } = useTemplateState(doctorId);

  function showDefaultPreview() {
    Dialog.show({
      title: "门诊病历标准格式",
      content: (
        <div style={{ maxHeight: "50vh", overflowY: "auto" }}>
          <div style={{ fontSize: FONT.xs, color: APP.text4, marginBottom: 8 }}>
            卫医政发〔2010〕11号《病历书写基本规范》
          </div>
          {STANDARD_TEMPLATE_FIELDS.map((f, i) => (
            <div key={f.key} style={{
              padding: "8px 0",
              borderTop: i > 0 ? `0.5px solid ${APP.borderLight}` : "none",
            }}>
              <div style={{ fontSize: FONT.base, color: APP.text1, fontWeight: 500 }}>
                {i + 1}. {f.label}
              </div>
              <div style={{ fontSize: FONT.xs, color: APP.text4, marginTop: 2 }}>
                {f.desc}
              </div>
            </div>
          ))}
        </div>
      ),
      closeOnMaskClick: true,
      confirmText: "知道了",
    });
  }

  function confirmDelete() {
    Dialog.confirm({
      title: "删除模板",
      content: "删除后将恢复国家卫生部 2010 年标准格式。",
      cancelText: "保留",
      confirmText: "确认删除",
      onConfirm: handleDelete,
    });
  }

  const customized = !!status?.has_template;

  return (
    <div style={pageContainer}>
      <NavBar backArrow={<SubpageBackHome />} onBack={() => navigate(-1)} style={navBarStyle}>
        报告模板
      </NavBar>

      <div style={{ ...scrollable, paddingTop: 4, paddingBottom: 24 }}>
        {/* Current template */}
        <SectionHeader title="当前模板" />
        <Card>
          <Row
            Icon={FileOutline}
            iconColor={APP.primary}
            iconBg={APP.primaryLight}
            title="门诊病历报告模板"
            subtitle={
              loading ? "加载中…" : customized
                ? `已上传自定义模板（${status.char_count?.toLocaleString()} 字符）`
                : "使用国家卫生部 2010 年标准格式"
            }
            onClick={!customized ? showDefaultPreview : undefined}
            isFirst
            extra={
              customized ? (
                <div style={{
                  padding: "3px 8px",
                  borderRadius: RADIUS.sm,
                  background: APP.primaryLight,
                  fontSize: FONT.xs,
                  color: APP.primary,
                  fontWeight: 600,
                }}>
                  已自定义
                </div>
              ) : (
                !loading && <ChevronRightIcon sx={{ fontSize: ICON.sm, color: APP.text4 }} />
              )
            }
          />
        </Card>

        {/* Actions */}
        <SectionHeader title="操作" />
        <Card>
          <Row
            Icon={UploadFileOutlinedIcon}
            iconColor={APP.primary}
            iconBg={APP.primaryLight}
            title={uploading ? "上传中…" : customized ? "替换模板文件" : "上传模板文件"}
            subtitle="PDF / DOCX / DOC / TXT / JPG / PNG，最大 1 MB"
            onClick={() => !uploading && fileRef.current?.click()}
            isFirst
            disabled={uploading}
            extra={uploading ? <SpinLoading color="primary" style={{ "--size": "18px" }} /> : null}
          />
          {customized && (
            <Row
              Icon={DeleteOutlineIcon}
              iconColor={APP.danger}
              iconBg={APP.dangerLight}
              title={deleting ? "删除中…" : "删除模板，恢复默认"}
              subtitle="删除后使用卫生部标准格式"
              onClick={!deleting ? confirmDelete : undefined}
              disabled={deleting}
              extra={deleting ? <SpinLoading color="danger" style={{ "--size": "18px" }} /> : null}
            />
          )}
        </Card>

        {/* Footer hint */}
        <div
          style={{
            padding: "12px 20px 0",
            fontSize: FONT.sm,
            color: APP.text4,
            lineHeight: 1.6,
          }}
        >
          上传后，AI 生成门诊病历报告时将参照您的格式。
        </div>

        <input
          ref={fileRef}
          type="file"
          hidden
          accept=".pdf,.docx,.doc,.txt,image/jpeg,image/png,image/webp"
          onChange={handleUpload}
        />
      </div>
    </div>
  );
}
