/**
 * @route /doctor/settings/templates
 *
 * TemplateSubpage v2 — report template management.
 * antd-mobile only, no MUI.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { NavBar, Button, Dialog, SpinLoading, Toast } from "antd-mobile";
import { useNavigate } from "react-router-dom";
import { useApi } from "../../../../api/ApiContext";
import { useDoctorStore } from "../../../../store/doctorStore";
import { APP } from "../../../theme";

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
          <div style={{ fontSize: "var(--adm-font-size-xs)", color: APP.text4, marginBottom: 8 }}>
            卫医政发〔2010〕11号《病历书写基本规范》
          </div>
          {STANDARD_TEMPLATE_FIELDS.map((f, i) => (
            <div key={f.key} style={{
              padding: "8px 0",
              borderTop: i > 0 ? `0.5px solid ${APP.borderLight}` : "none",
            }}>
              <div style={{ fontSize: "var(--adm-font-size-main)", color: APP.text1, fontWeight: 500 }}>
                {i + 1}. {f.label}
              </div>
              <div style={{ fontSize: "var(--adm-font-size-xs)", color: APP.text4, marginTop: 2 }}>
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

  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column", background: APP.surfaceAlt, overflow: "hidden" }}>
      <NavBar
        onBack={() => navigate(-1)}
        style={{
          "--height": "44px",
          "--border-bottom": `0.5px solid ${APP.border}`,
          backgroundColor: APP.surface,
          flexShrink: 0,
        }}
      >
        报告模板
      </NavBar>

      <div style={{ flex: 1, overflowY: "auto" }}>
        {/* Section: 当前模板 */}
        <div style={{ padding: "8px 16px 4px", fontSize: "var(--adm-font-size-xs)", color: APP.text4 }}>
          当前模板
        </div>

        <div style={{ background: APP.surface, margin: "0 0 1px", padding: "14px 16px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            {/* Icon */}
            <div style={{
              width: 44, height: 44, borderRadius: 10,
              background: "#e7f8ee",
              display: "flex", alignItems: "center", justifyContent: "center",
              flexShrink: 0, fontSize: 20,
            }}>
              📄
            </div>

            <div style={{ flex: 1 }}>
              <div style={{ fontSize: "var(--adm-font-size-main)", fontWeight: 500, color: APP.text1 }}>
                门诊病历报告模板
              </div>
              {loading ? (
                <div style={{ fontSize: "var(--adm-font-size-sm)", color: APP.text4, marginTop: 2 }}>
                  加载中…
                </div>
              ) : status?.has_template ? (
                <div style={{ fontSize: "var(--adm-font-size-sm)", color: APP.text4, marginTop: 2 }}>
                  已上传自定义模板（{status.char_count?.toLocaleString()} 字符）
                </div>
              ) : (
                <div
                  onClick={showDefaultPreview}
                  style={{ fontSize: "var(--adm-font-size-sm)", color: "#1B6EF3", marginTop: 2, cursor: "pointer" }}
                >
                  使用国家卫生部 2010 年标准格式 ›
                </div>
              )}
            </div>

            {status?.has_template && (
              <div style={{
                padding: "3px 8px",
                borderRadius: 10,
                background: "#e7f8ee",
                fontSize: "var(--adm-font-size-xs)",
                color: "#07C160",
                fontWeight: 600,
                flexShrink: 0,
              }}>
                已自定义
              </div>
            )}
          </div>
        </div>

        {/* Section: 操作 */}
        <div style={{ padding: "8px 16px 4px", fontSize: "var(--adm-font-size-xs)", color: APP.text4 }}>
          操作
        </div>

        <div style={{ background: APP.surface }}>
          {/* Upload row */}
          <div
            onClick={() => !uploading && fileRef.current?.click()}
            style={{
              display: "flex", alignItems: "center",
              padding: "14px 16px",
              borderBottom: status?.has_template ? `0.5px solid ${APP.borderLight}` : "none",
              cursor: uploading ? "default" : "pointer",
            }}
          >
            {uploading ? (
              <SpinLoading color="primary" style={{ "--size": "18px", marginRight: 12 }} />
            ) : (
              <div style={{ width: 18, marginRight: 12 }} />
            )}
            <span style={{
              flex: 1,
              fontSize: "var(--adm-font-size-main)",
              color: uploading ? APP.text4 : "#07C160",
              fontWeight: 500,
            }}>
              {uploading ? "上传中…" : status?.has_template ? "替换模板文件" : "上传模板文件"}
            </span>
            <span style={{ fontSize: 12, color: APP.text4 }}>›</span>
          </div>

          {/* Delete row */}
          {status?.has_template && (
            <div
              onClick={!deleting ? confirmDelete : undefined}
              style={{
                display: "flex", alignItems: "center",
                padding: "14px 16px",
                cursor: deleting ? "default" : "pointer",
              }}
            >
              {deleting ? (
                <SpinLoading color="danger" style={{ "--size": "18px", marginRight: 12 }} />
              ) : (
                <div style={{ width: 18, marginRight: 12 }} />
              )}
              <span style={{
                flex: 1,
                fontSize: "var(--adm-font-size-main)",
                color: deleting ? APP.text4 : "#FA5151",
              }}>
                {deleting ? "删除中…" : "删除模板，恢复默认"}
              </span>
            </div>
          )}
        </div>

        {/* Hint */}
        <div style={{ padding: "12px 16px", fontSize: "var(--adm-font-size-xs)", color: APP.text4, lineHeight: 1.8 }}>
          支持格式：PDF、DOCX、DOC、TXT、JPG、PNG，最大 1 MB。{"\n"}
          上传后，AI 生成门诊病历报告时将参照您的格式。
        </div>

        <input
          ref={fileRef}
          type="file"
          hidden
          accept=".pdf,.docx,.doc,.txt,image/jpeg,image/png,image/webp"
          onChange={handleUpload}
        />

        <div style={{ height: 32 }} />
      </div>
    </div>
  );
}
