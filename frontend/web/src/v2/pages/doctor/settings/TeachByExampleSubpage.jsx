/**
 * @route /doctor/settings/teach
 *
 * TeachByExampleSubpage v2 — paste a sample response, AI extracts style rules.
 * antd-mobile only, no MUI.
 */
import { useState } from "react";
import { NavBar, TextArea, Button, Toast } from "antd-mobile";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { QK } from "../../../../lib/queryKeys";
import { useApi } from "../../../../api/ApiContext";
import { useDoctorStore } from "../../../../store/doctorStore";
import { APP } from "../../../theme";

const FIELD_LABELS = {
  reply_style: "回复风格",
  closing: "常用结尾语",
  structure: "回复结构",
  avoid: "回避内容",
  edits: "常见修改",
};

export default function TeachByExampleSubpage() {
  const navigate = useNavigate();
  const api = useApi();
  const queryClient = useQueryClient();
  const { doctorId } = useDoctorStore();

  const [text, setText] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [extracted, setExtracted] = useState(null); // null = not submitted yet

  async function handleSubmit() {
    if (!text.trim()) return;
    setLoading(true);
    setError(null);
    setExtracted(null);
    try {
      const result = await api.teachByExample(doctorId, text.trim());
      setExtracted(result.extracted || []);
      if (result.count > 0) {
        queryClient.invalidateQueries({
          queryKey: QK.personaPending(doctorId),
        });
      }
    } catch {
      setError("分析失败，请重试");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100%",
        backgroundColor: APP.surfaceAlt,
        overflow: "hidden",
      }}
    >
      <NavBar
        onBack={() => navigate(-1)}
        style={{
          "--height": "44px",
          "--border-bottom": `0.5px solid ${APP.border}`,
          backgroundColor: APP.surface,
          flexShrink: 0,
        }}
      >
        教AI新偏好
      </NavBar>

      <div style={{ flex: 1, overflowY: "auto", padding: "16px" }}>
        {/* Helper text */}
        <p
          style={{
            fontSize: 13,
            color: APP.text4,
            lineHeight: 1.6,
            margin: "0 0 16px",
          }}
        >
          粘贴一段你满意的回复，AI会自动分析其中的风格偏好，添加到待确认队列。
        </p>

        {/* TextArea */}
        <TextArea
          placeholder="粘贴一段你满意的回复示例…"
          value={text}
          onChange={setText}
          autoSize={{ minRows: 6, maxRows: 12 }}
          maxLength={2000}
          showCount
          disabled={loading}
          style={{
            "--font-size": "14px",
            "--placeholder-color": APP.text4,
            backgroundColor: APP.surface,
            borderRadius: 8,
            padding: "12px",
            border: `0.5px solid ${APP.border}`,
            marginBottom: 16,
          }}
        />

        {/* Submit button */}
        <Button
          block
          color="primary"
          loading={loading}
          disabled={!text.trim() || loading}
          onClick={handleSubmit}
        >
          {loading ? "分析中…" : "开始分析"}
        </Button>

        {/* Error */}
        {error && (
          <p style={{ color: "#FA5151", fontSize: 14, marginTop: 12 }}>
            {error}
          </p>
        )}

        {/* Results */}
        {extracted !== null && (
          <div style={{ marginTop: 20 }}>
            {extracted.length === 0 ? (
              <div
                style={{
                  textAlign: "center",
                  color: APP.text4,
                  fontSize: 14,
                  padding: "16px 0",
                }}
              >
                未发现明显的风格偏好，请尝试粘贴更完整的回复
              </div>
            ) : (
              <>
                <p
                  style={{
                    fontSize: 13,
                    color: APP.text4,
                    marginBottom: 12,
                  }}
                >
                  发现 {extracted.length} 条偏好，已添加到待确认队列：
                </p>
                <div
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    gap: 10,
                  }}
                >
                  {extracted.map((r, i) => (
                    <div
                      key={i}
                      style={{
                        display: "flex",
                        gap: 10,
                        alignItems: "flex-start",
                        backgroundColor: APP.surface,
                        borderRadius: 8,
                        padding: "10px 14px",
                        border: `0.5px solid ${APP.border}`,
                      }}
                    >
                      <span
                        style={{
                          fontSize: 16,
                          color: "#07C160",
                          flexShrink: 0,
                          lineHeight: 1.4,
                        }}
                      >
                        ✓
                      </span>
                      <div>
                        <div
                          style={{
                            fontSize: 11,
                            color: APP.text4,
                            marginBottom: 2,
                          }}
                        >
                          {FIELD_LABELS[r.field] || r.field}
                        </div>
                        <div style={{ fontSize: 14, color: APP.text1 }}>
                          {r.text}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>
        )}

        <div style={{ height: 32 }} />
      </div>
    </div>
  );
}
