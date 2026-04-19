/**
 * @route /doctor/patients/new
 *
 * v2 InterviewPage — chat-based medical record intake.
 * Uses antd-mobile + raw HTML. No MUI.
 *
 * Phase 1 gate: proves antd-mobile + keyboard handler work in WeChat WebView.
 */
import { useEffect, useRef, useState } from "react";
import {
  NavBar,
  Button,
  Dialog,
  Toast,
  SpinLoading,
  Card,
  List,
  Popup,
  Tag,
} from "antd-mobile";
import { LeftOutline, QuestionCircleOutline, AddCircleOutline, CheckOutline, CloseOutline } from "antd-mobile-icons";
import { useApi } from "../../../api/ApiContext";
import { useAppNavigate } from "../../../hooks/useAppNavigate";
import { isInMiniapp } from "../../../utils/miniappBridge";
import { nowTs } from "../../../utils/time";
import { dp } from "../../../utils/doctorBasePath";
import ChatComposer from "../../ChatComposer";
import ChatBubble from "../../ChatBubble";
import { keyboardAwareStyle, useScrollOnKeyboard } from "../../keyboard";
import { APP, FONT, RADIUS } from "../../theme";

// ── Field label map ────────────────────────────────────────────────
const FIELD_LABELS = {
  department: "科室",
  chief_complaint: "主诉",
  present_illness: "现病史",
  past_history: "既往史",
  allergy_history: "过敏史",
  personal_history: "个人史",
  marital_reproductive: "婚育史",
  family_history: "家族史",
  physical_exam: "体格检查",
  specialist_exam: "专科检查",
  auxiliary_exam: "辅助检查",
  diagnosis: "初步诊断",
  treatment_plan: "治疗方案",
  orders_followup: "医嘱随访",
};

// ── Field review card (carry-forward / import) ─────────────────────
function FieldReviewCard({ title, subtitle, items, confirmLabel, dismissLabel, confirmAllLabel, onConfirm, onDismiss, onConfirmAll, editable, disabled }) {
  const [editField, setEditField] = useState(null);
  const [editValue, setEditValue] = useState("");

  function startEdit(item) {
    setEditField(item.field);
    setEditValue(item.value);
  }

  function commitEdit(field) {
    if (editable && editValue.trim()) {
      onConfirm?.(field, editValue.trim());
    }
    setEditField(null);
  }

  return (
    <div style={cardStyles.wrap}>
      <div style={cardStyles.header}>
        <span style={cardStyles.title}>{title}</span>
        <span style={cardStyles.subtitle}>{subtitle}</span>
        {confirmAllLabel && items.length > 1 && (
          <button
            style={cardStyles.allBtn}
            onClick={() => onConfirmAll?.()}
            disabled={disabled}
          >
            {confirmAllLabel}
          </button>
        )}
      </div>
      <div style={cardStyles.list}>
        {items.map((item) => (
          <div key={item.field} style={cardStyles.row}>
            <div style={cardStyles.rowLeft}>
              <span style={cardStyles.label}>{item.label || item.field}</span>
              {editField === item.field ? (
                <textarea
                  style={cardStyles.editArea}
                  value={editValue}
                  autoFocus
                  onChange={(e) => setEditValue(e.target.value)}
                  onBlur={() => commitEdit(item.field)}
                  rows={2}
                />
              ) : (
                <span style={cardStyles.value}>{item.value}</span>
              )}
            </div>
            <div style={cardStyles.rowActions}>
              <button
                style={{ ...cardStyles.actionBtn, color: APP.primary }}
                onClick={() => onConfirm?.(item.field, item.value)}
                disabled={disabled}
              >
                {confirmLabel}
              </button>
              {editable ? (
                <button
                  style={{ ...cardStyles.actionBtn, color: APP.text3 }}
                  onClick={() => startEdit(item)}
                  disabled={disabled}
                >
                  {dismissLabel}
                </button>
              ) : (
                onDismiss && (
                  <button
                    style={{ ...cardStyles.actionBtn, color: APP.text4 }}
                    onClick={() => onDismiss?.(item.field)}
                    disabled={disabled}
                  >
                    {dismissLabel}
                  </button>
                )
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

const cardStyles = {
  wrap: {
    background: APP.surface,
    borderBottom: `1px solid ${APP.border}`,
    flexShrink: 0,
  },
  header: {
    display: "flex",
    alignItems: "center",
    gap: 6,
    padding: "8px 12px 4px",
  },
  title: {
    fontSize: FONT.sm,
    fontWeight: 600,
    color: APP.text2,
  },
  subtitle: {
    fontSize: FONT.sm,
    color: APP.text4,
    flex: 1,
  },
  allBtn: {
    border: "none",
    background: "none",
    color: APP.primary,
    fontSize: FONT.sm,
    cursor: "pointer",
    padding: "2px 4px",
  },
  list: {
    paddingBottom: 6,
  },
  row: {
    display: "flex",
    alignItems: "flex-start",
    gap: 8,
    padding: "5px 12px",
    borderTop: `1px solid ${APP.borderLight}`,
  },
  rowLeft: {
    flex: 1,
    display: "flex",
    flexDirection: "column",
    gap: 2,
  },
  label: {
    fontSize: FONT.xs,
    color: APP.text4,
    fontWeight: 500,
  },
  value: {
    fontSize: FONT.sm,
    color: APP.text1,
    lineHeight: "1.5",
  },
  editArea: {
    width: "100%",
    border: `1px solid ${APP.primary}`,
    borderRadius: RADIUS.sm,
    padding: "4px 6px",
    fontSize: FONT.sm,
    fontFamily: "inherit",
    lineHeight: "1.5",
    resize: "none",
    outline: "none",
    boxSizing: "border-box",
  },
  rowActions: {
    display: "flex",
    flexDirection: "column",
    gap: 4,
    flexShrink: 0,
  },
  actionBtn: {
    border: "none",
    background: "none",
    fontSize: FONT.sm,
    cursor: "pointer",
    padding: "2px 0",
    textAlign: "right",
  },
};

// ── Complete dialog (Popup) ────────────────────────────────────────
function InterviewCompletePopup({ open, fields, fieldCount, onSave, onSaveAndDiagnose, onClose, loading }) {
  const [nameInput, setNameInput] = useState(fields?._patient_name || "");

  useEffect(() => {
    if (open) setNameInput(fields?._patient_name || "");
  }, [open, fields?._patient_name]);

  const filledFields = Object.entries(fields || {})
    .filter(([k, v]) => k !== "_patient_name" && v && String(v).trim())
    .slice(0, 8); // show first 8 to avoid scroll overflow

  return (
    <Popup visible={open} onMaskClick={onClose} bodyStyle={{ borderRadius: "12px 12px 0 0", padding: "20px 16px 8px" }}>
      <div style={popupStyles.wrap}>
        <div style={popupStyles.title}>保存病历</div>
        <div style={popupStyles.subtitle}>
          已填写 {fieldCount?.filled || 0} / {fieldCount?.total || 14} 个字段
        </div>

        {/* Patient name input */}
        <div style={popupStyles.nameRow}>
          <span style={popupStyles.nameLabel}>患者姓名</span>
          <input
            style={popupStyles.nameInput}
            value={nameInput}
            onChange={(e) => setNameInput(e.target.value)}
            placeholder="输入患者姓名（可选）"
          />
        </div>

        {/* Field preview */}
        {filledFields.length > 0 && (
          <div style={popupStyles.fieldList}>
            {filledFields.map(([k, v]) => (
              <div key={k} style={popupStyles.fieldRow}>
                <span style={popupStyles.fieldLabel}>{FIELD_LABELS[k] || k}</span>
                <span style={popupStyles.fieldValue}>{String(v).slice(0, 60)}{String(v).length > 60 ? "…" : ""}</span>
              </div>
            ))}
          </div>
        )}

        {/* Buttons */}
        <div style={popupStyles.btnRow}>
          <Button
            style={popupStyles.cancelBtn}
            onClick={onClose}
            disabled={loading}
          >
            取消
          </Button>
          <Button
            style={popupStyles.saveBtn}
            onClick={() => onSave?.(nameInput || undefined)}
            disabled={loading}
          >
            {loading ? <SpinLoading color="white" style={{ "--size": "18px" }} /> : "仅保存"}
          </Button>
          <Button
            style={popupStyles.diagBtn}
            onClick={() => onSaveAndDiagnose?.(nameInput || undefined)}
            disabled={loading}
          >
            {loading ? <SpinLoading color="white" style={{ "--size": "18px" }} /> : "保存并诊断"}
          </Button>
        </div>
      </div>
    </Popup>
  );
}

const popupStyles = {
  wrap: {
    display: "flex",
    flexDirection: "column",
    gap: 12,
    paddingBottom: 8,
  },
  title: {
    fontSize: FONT.lg,
    fontWeight: 600,
    color: APP.text1,
    textAlign: "center",
  },
  subtitle: {
    fontSize: FONT.sm,
    color: APP.text3,
    textAlign: "center",
  },
  nameRow: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    borderBottom: `1px solid ${APP.border}`,
    paddingBottom: 8,
  },
  nameLabel: {
    fontSize: FONT.main,
    color: APP.text2,
    flexShrink: 0,
    width: 56,
  },
  nameInput: {
    flex: 1,
    border: `1px solid ${APP.border}`,
    borderRadius: RADIUS.sm,
    padding: "6px 10px",
    fontSize: FONT.main,
    fontFamily: "inherit",
    outline: "none",
    color: APP.text1,
  },
  fieldList: {
    maxHeight: 160,
    overflowY: "auto",
    borderRadius: RADIUS.sm,
    background: APP.surfaceAlt,
    padding: "6px 10px",
    display: "flex",
    flexDirection: "column",
    gap: 6,
  },
  fieldRow: {
    display: "flex",
    gap: 8,
    alignItems: "flex-start",
  },
  fieldLabel: {
    fontSize: FONT.sm,
    color: APP.text4,
    width: 60,
    flexShrink: 0,
    paddingTop: 1,
  },
  fieldValue: {
    fontSize: FONT.sm,
    color: APP.text1,
    flex: 1,
    lineHeight: "1.5",
  },
  btnRow: {
    display: "flex",
    gap: 8,
    paddingTop: 4,
  },
  cancelBtn: {
    flex: 1,
    "--background-color": APP.surfaceAlt,
    "--border-color": APP.border,
    "--text-color": APP.text2,
    height: 40,
    borderRadius: RADIUS.md,
  },
  saveBtn: {
    flex: 1,
    "--background-color": APP.primary,
    "--border-color": APP.primary,
    "--text-color": APP.white,
    height: 40,
    borderRadius: RADIUS.md,
  },
  diagBtn: {
    flex: 1,
    "--background-color": APP.primary,
    "--border-color": APP.primary,
    "--text-color": APP.white,
    height: 40,
    borderRadius: RADIUS.md,
  },
};

// ── Main page ──────────────────────────────────────────────────────

export default function InterviewPage({
  doctorId,
  sessionId: resumeSessionId,
  patientContext,
  prePopulated,
  onComplete,
  onCancel,
}) {
  const navigate = useAppNavigate();
  const {
    doctorInterviewTurn,
    doctorInterviewConfirm,
    doctorInterviewCancel,
    doctorInterviewGetSession,
    confirmCarryForward,
    triggerDiagnosis,
    updateInterviewField,
    ocrImage,
  } = useApi();

  const patientName = patientContext?.name;
  const importFieldCount = prePopulated
    ? Object.values(prePopulated).filter((v) => v && v.trim()).length
    : 0;

  const welcomeMsg =
    importFieldCount > 0
      ? `已从导入内容中识别 ${importFieldCount} 个字段，请确认或编辑。\n缺少的字段可以在下方对话中补充。`
      : patientName
      ? `正在为 ${patientName} 建立门诊记录。\n请输入症状、检查结果等信息，我会帮您结构化记录。`
      : "病历采集模式已开启。\n请输入患者信息（姓名、性别、年龄、症状等），我会帮您结构化记录。";

  // ── State ──────────────────────────────────────────────────────
  const [messages, setMessages] = useState([
    { role: "assistant", content: welcomeMsg, ts: nowTs() },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [suggestions, setSuggestions] = useState([]);
  const [selectedSuggestions, setSelectedSuggestions] = useState([]);
  const [carryForward, setCarryForward] = useState([]);
  const [importItems, setImportItems] = useState(() => {
    if (!prePopulated || Object.keys(prePopulated).length === 0) return [];
    return Object.entries(prePopulated)
      .filter(([, v]) => v && v.trim())
      .map(([field, value]) => ({
        field,
        label: FIELD_LABELS[field] || field,
        value,
      }));
  });
  const [session, setSession] = useState({
    sessionId: resumeSessionId || null,
    progress: { filled: 0, total: 7 },
    status: "interviewing",
    patientId: patientContext?.id || null,
    collected: {},
  });
  const [showCompletePopup, setShowCompletePopup] = useState(false);

  const bottomRef = useRef(null);
  const cameraInputRef = useRef(null);
  const fileInputRef = useRef(null);

  // ── Keyboard + scroll ──────────────────────────────────────────
  useScrollOnKeyboard(bottomRef);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // ── Welcome message update when patientContext arrives late ────
  useEffect(() => {
    if (
      patientContext?.name &&
      messages.length === 1 &&
      messages[0].role === "assistant"
    ) {
      setMessages([
        {
          role: "assistant",
          content: `正在为 ${patientContext.name} 建立门诊记录。\n请输入症状、检查结果等信息，我会帮您结构化记录。`,
          ts: nowTs(),
        },
      ]);
      setSession((prev) => ({ ...prev, patientId: patientContext.id }));
    }
  }, [patientContext?.name]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Resume existing session ────────────────────────────────────
  useEffect(() => {
    if (!resumeSessionId) return;
    (async () => {
      try {
        const data = await doctorInterviewGetSession(resumeSessionId, doctorId);
        setSession({
          sessionId: data.session_id,
          progress: data.progress,
          status: data.status,
          patientId: data.patient_id,
          collected: data.collected || {},
        });
        if (data.conversation && data.conversation.length > 0) {
          setMessages(
            data.conversation.map((turn) => ({
              role: turn.role,
              content: turn.content,
              ts: turn.timestamp
                ? new Date(turn.timestamp).toLocaleTimeString("zh-CN", {
                    hour: "2-digit",
                    minute: "2-digit",
                  })
                : nowTs(),
            }))
          );
        } else if (data.reply) {
          setMessages([{ role: "assistant", content: data.reply, ts: nowTs() }]);
        }
        setSuggestions(data.suggestions || []);
      } catch (err) {
        setError(`会话加载失败：${err.message}`);
      }
    })();
  }, [resumeSessionId, doctorId]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Suggestion chips ───────────────────────────────────────────
  function handleToggleSuggestion(text) {
    setSelectedSuggestions((prev) =>
      prev.includes(text) ? prev.filter((s) => s !== text) : [...prev, text]
    );
  }

  // ── Carry-forward handlers ─────────────────────────────────────
  async function handleCarryForwardConfirm(field) {
    if (!session.sessionId) return;
    try {
      const data = await confirmCarryForward(session.sessionId, doctorId, field, "confirm");
      setCarryForward((prev) => prev.filter((item) => item.field !== field));
      setSession((prev) => ({
        ...prev,
        progress: data.progress,
        status: data.status,
        collected: data.collected || prev.collected,
      }));
    } catch (err) {
      setError(err.message);
    }
  }

  function handleCarryForwardDismiss(field) {
    setCarryForward((prev) => prev.filter((item) => item.field !== field));
  }

  async function handleCarryForwardConfirmAll() {
    if (!session.sessionId) return;
    const remaining = [...carryForward];
    for (const item of remaining) {
      try {
        const data = await confirmCarryForward(
          session.sessionId,
          doctorId,
          item.field,
          "confirm"
        );
        setCarryForward((prev) => prev.filter((i) => i.field !== item.field));
        setSession((prev) => ({
          ...prev,
          progress: data.progress,
          status: data.status,
          collected: data.collected || prev.collected,
        }));
      } catch (err) {
        setError(err.message);
        break;
      }
    }
  }

  // ── Import item handlers ───────────────────────────────────────
  function handleImportConfirm(field) {
    setImportItems((prev) => prev.filter((item) => item.field !== field));
  }

  async function handleImportEdit(field, newValue) {
    if (!session.sessionId) return;
    try {
      const data = await updateInterviewField(
        session.sessionId,
        doctorId,
        field,
        newValue
      );
      setSession((prev) => ({
        ...prev,
        progress: data.progress,
        status: data.status,
        collected: data.collected || prev.collected,
      }));
      setImportItems((prev) => prev.filter((item) => item.field !== field));
    } catch (err) {
      setError(err.message);
    }
  }

  function handleImportConfirmAll() {
    setImportItems([]);
  }

  // ── Camera/file OCR ────────────────────────────────────────────
  async function handleCameraFile(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      if (ocrImage) {
        const result = await ocrImage(file);
        if (result?.text) {
          // Populate input with OCR text for user to review before sending
          setInput(result.text);
        }
      }
    } catch {
      /* silent */
    }
    e.target.value = "";
  }

  // ── Send message ───────────────────────────────────────────────
  async function handleSend(text) {
    const parts = [...selectedSuggestions];
    const trimmed = text?.trim() || input.trim();
    if (trimmed) parts.push(trimmed);
    const combined = parts.join("，");
    if (!combined || loading) return;

    setMessages((prev) => [
      ...prev,
      { role: "user", content: combined, ts: nowTs() },
    ]);
    setInput("");
    setSuggestions([]);
    setSelectedSuggestions([]);
    setLoading(true);
    setError(null);

    try {
      const formData = new FormData();
      formData.append("text", combined);
      formData.append("doctor_id", doctorId);
      if (session.sessionId) formData.append("session_id", session.sessionId);
      if (session.patientId)
        formData.append("patient_id", String(session.patientId));

      const data = await doctorInterviewTurn(formData);

      setSession({
        sessionId: data.session_id,
        progress: data.progress,
        status: data.status,
        patientId: data.patient_id,
        collected: data.collected || {},
      });

      if (data.carry_forward && data.carry_forward.length > 0) {
        setCarryForward(data.carry_forward);
      }

      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: data.reply, ts: nowTs() },
      ]);
      setSuggestions(data.suggestions || []);
      setSelectedSuggestions([]);
    } catch (err) {
      setError(err.message);
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: `出错：${err.message}`, ts: nowTs() },
      ]);
    } finally {
      setLoading(false);
    }
  }

  // ── Confirm (save) ─────────────────────────────────────────────
  async function handleConfirm(nameOverride) {
    if (!session.sessionId) return null;
    setLoading(true);
    try {
      const data = await doctorInterviewConfirm(
        session.sessionId,
        doctorId,
        nameOverride
      );
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: data.preview
            ? `病历草稿已生成：\n\n${data.preview}\n\n请在聊天中确认保存。`
            : "病历草稿已生成，请在聊天中确认保存。",
          ts: nowTs(),
        },
      ]);
      setSession((prev) => ({ ...prev, status: "draft_created" }));
      setShowCompletePopup(false);
      onComplete?.(data);
      return data;
    } catch (err) {
      setError(err.message);
      return null;
    } finally {
      setLoading(false);
    }
  }

  async function handleSaveOnly(nameOverride) {
    await handleConfirm(nameOverride);
  }

  async function handleSaveAndDiagnose(nameOverride) {
    const data = await handleConfirm(nameOverride);
    if (!data) return;
    const recordId = data.pending_id;
    if (!recordId) return;
    try {
      await triggerDiagnosis(recordId, doctorId);
    } catch {
      // Best-effort — navigate regardless
    }
    navigate(`${dp("review")}/${recordId}`);
  }

  // ── Cancel / back ──────────────────────────────────────────────
  async function handleCancel() {
    if (session.sessionId) {
      try {
        await doctorInterviewCancel(session.sessionId, doctorId);
      } catch {
        /* ignore */
      }
    }
    onCancel?.();
  }

  function handleBack() {
    const hasWork =
      session.sessionId || messages.length > 1 || input.trim();
    if (!hasWork) {
      handleCancel();
      return;
    }
    Dialog.confirm({
      title: "确认离开？",
      content: "未保存的内容将会丢失",
      cancelText: "取消",
      confirmText: "离开",
      confirmButtonStyle: { color: APP.danger },
      onConfirm: () => handleCancel(),
    });
  }

  // ── Field count for complete dialog ───────────────────────────
  const fieldCount = (() => {
    const fields = session.progress?.fields || {};
    const total = Object.keys(fields).length || 14;
    const filled = Object.values(fields).filter(
      (f) => f.status !== "empty"
    ).length;
    return { filled, total };
  })();

  // ── Render ─────────────────────────────────────────────────────
  return (
    <div style={keyboardAwareStyle}>
      {/* Header */}
      <NavBar
        onBack={handleBack}
        right={
          <QuestionCircleOutline
            style={{ fontSize: 20, color: APP.text3 }}
            onClick={() =>
              Dialog.alert({
                content:
                  "直接描述患者情况，AI会提取结构化字段。输入越详细，病历越完整。",
                confirmText: "知道了",
              })
            }
          />
        }
        style={{
          "--height": "44px",
          "--border-bottom": `0.5px solid ${APP.border}`,
          backgroundColor: APP.surface,
          flexShrink: 0,
        }}
      >
        新建病历
      </NavBar>

      {/* Status bar — shown after session starts */}
      {session.sessionId && session.status !== "draft_created" && (
        <div style={statusStyles.bar}>
          <div style={statusStyles.left}>
            <span
              style={{
                ...statusStyles.name,
                color: session.collected?._patient_name ? APP.text1 : APP.text4,
                fontWeight: session.collected?._patient_name ? 600 : 400,
              }}
            >
              {session.collected?._patient_name || "未命名"}
            </span>
            <span style={statusStyles.dot}>·</span>
            <span
              style={{
                ...statusStyles.count,
                color: session.progress?.can_complete ? APP.primary : APP.text4,
              }}
            >
              必填 {session.progress?.required_count || 0}/
              {session.progress?.required_total || 0}
              {session.progress?.can_complete ? <CheckOutline style={{ fontSize: FONT.sm, marginLeft: 4 }} /> : null}
            </span>
            <span style={statusStyles.other}>
              其他{" "}
              {(session.progress?.filled || 0) -
                (session.progress?.required_count || 0)}
              /
              {(session.progress?.total || 0) -
                (session.progress?.required_total || 0)}
            </span>
          </div>
          <button
            style={{
              ...statusStyles.doneBtn,
              background: session.progress?.can_complete ? APP.primary : "none",
              color: session.progress?.can_complete ? APP.white : APP.text4,
              border: session.progress?.can_complete
                ? "none"
                : `1px solid ${APP.border}`,
            }}
            onClick={() => setShowCompletePopup(true)}
            disabled={loading || !session.progress?.can_complete}
          >
            完成
          </button>
        </div>
      )}

      {/* Import preview card */}
      {importItems.length > 0 && session.status !== "draft_created" && (
        <FieldReviewCard
          title="已从导入提取"
          subtitle={`${importItems.length} 项待确认`}
          items={importItems}
          confirmLabel="确认"
          dismissLabel="编辑"
          confirmAllLabel="全部确认"
          onConfirm={handleImportConfirm}
          onEdit={handleImportEdit}
          onConfirmAll={handleImportConfirmAll}
          editable
          disabled={loading}
        />
      )}

      {/* Carry-forward card */}
      {carryForward.length > 0 && session.status !== "draft_created" && (
        <FieldReviewCard
          title={`上次记录${carryForward[0]?.source_date ? ` (${carryForward[0].source_date})` : ""}`}
          subtitle={`${carryForward.length} 项可沿用`}
          items={carryForward}
          confirmLabel="沿用"
          dismissLabel="忽略"
          confirmAllLabel="全部沿用"
          onConfirm={handleCarryForwardConfirm}
          onDismiss={handleCarryForwardDismiss}
          onConfirmAll={handleCarryForwardConfirmAll}
          disabled={loading}
        />
      )}

      {/* Message list */}
      <div style={msgStyles.list}>
        {messages.map((msg, idx) => (
          <ChatBubble
            key={idx}
            role={msg.role}
            content={msg.content}
            timestamp={msg.ts}
          />
        ))}
        {loading && (
          <div style={msgStyles.loadingRow}>
            <SpinLoading color="primary" style={{ "--size": "16px" }} />
            <span style={msgStyles.loadingText}>处理中…</span>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Draft created banner */}
      {session.status === "draft_created" && (
        <div style={statusStyles.draftBanner}>
          <span style={{ color: APP.primary, fontSize: FONT.sm }}>草稿已生成</span>
        </div>
      )}

      {/* Error */}
      {error && (
        <div style={errStyles.bar}>
          <span style={errStyles.text}>{error}</span>
          <button style={errStyles.close} onClick={() => setError(null)}>
            <CloseOutline style={{ fontSize: FONT.md }} />
          </button>
        </div>
      )}

      {/* Camera/file inputs (hidden) */}
      <input
        ref={cameraInputRef}
        type="file"
        accept="image/*"
        capture="environment"
        style={{ display: "none" }}
        onChange={handleCameraFile}
      />
      <input
        ref={fileInputRef}
        type="file"
        accept="image/*,.pdf,.doc,.docx"
        style={{ display: "none" }}
        onChange={handleCameraFile}
      />

      {/* Chat composer */}
      {session.status !== "draft_created" && (
        <ChatComposer
          value={input}
          onChange={setInput}
          onSend={handleSend}
          disabled={loading}
          placeholder="输入患者信息..."
          doctorId={doctorId}
          suggestions={suggestions}
          selectedSuggestions={selectedSuggestions}
          onToggleSuggestion={handleToggleSuggestion}
        />
      )}

      {/* Interview complete popup */}
      <InterviewCompletePopup
        open={showCompletePopup}
        fields={session.collected}
        fieldCount={fieldCount}
        onSave={handleSaveOnly}
        onSaveAndDiagnose={handleSaveAndDiagnose}
        onClose={() => setShowCompletePopup(false)}
        loading={loading}
      />
    </div>
  );
}

// ── Styles ─────────────────────────────────────────────────────────

const statusStyles = {
  bar: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "6px 12px",
    background: APP.surface,
    borderBottom: `1px solid ${APP.border}`,
    flexShrink: 0,
  },
  left: {
    display: "flex",
    alignItems: "center",
    gap: 6,
  },
  name: {
    fontSize: FONT.sm,
  },
  dot: {
    fontSize: FONT.sm,
    color: APP.text4,
  },
  count: {
    fontSize: FONT.sm,
    fontWeight: 500,
  },
  other: {
    fontSize: FONT.sm,
    color: APP.text4,
  },
  doneBtn: {
    borderRadius: RADIUS.lg,
    padding: "2px 10px",
    fontSize: FONT.sm,
    cursor: "pointer",
    minHeight: 24,
  },
  draftBanner: {
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    padding: "8px 12px",
    background: APP.primaryLight,
    borderTop: `1px solid ${APP.border}`,
    flexShrink: 0,
  },
};

const msgStyles = {
  list: {
    flex: 1,
    overflowY: "auto",
    display: "flex",
    flexDirection: "column",
    gap: 4,
    paddingTop: 12,
    paddingBottom: 8,
    background: APP.surfaceAlt,
  },
  loadingRow: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    padding: "4px 16px",
  },
  loadingText: {
    fontSize: FONT.sm,
    color: APP.text4,
  },
};

const errStyles = {
  bar: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    padding: "8px 12px",
    background: APP.dangerLight,
    borderTop: `1px solid ${APP.dangerLight}`,
    flexShrink: 0,
  },
  text: {
    flex: 1,
    fontSize: FONT.sm,
    color: APP.danger,
  },
  close: {
    border: "none",
    background: "none",
    color: APP.danger,
    fontSize: FONT.lg,
    cursor: "pointer",
    padding: 0,
    lineHeight: 1,
  },
};
