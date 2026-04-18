/**
 * ChatBubble — a single chat message bubble for v2 chat pages.
 *
 * - role="user"      → green background (#95EC69), plain text, right-aligned
 * - role="assistant" → white background, react-markdown rendered, left-aligned
 *
 * Bubble corners follow WeChat convention:
 *   user      → rounded everywhere except bottom-right
 *   assistant → rounded everywhere except bottom-left
 */
import ReactMarkdown from "react-markdown";
import { APP } from "./theme";

export default function ChatBubble({ role, content, timestamp }) {
  const isUser = role === "user";

  return (
    <div style={{ ...styles.row, justifyContent: isUser ? "flex-end" : "flex-start" }}>
      {/* AI avatar — left side */}
      {!isUser && (
        <div style={{ ...styles.avatar, background: "#07C160", color: "#fff" }}>
          AI
        </div>
      )}

      <div style={styles.colWrap}>
        <div
          style={{
            ...styles.bubble,
            background: isUser ? APP.wechatGreen : APP.surface,
            borderRadius: isUser
              ? "18px 18px 4px 18px"   // bottom-right square
              : "18px 18px 18px 4px",  // bottom-left square
            alignSelf: isUser ? "flex-end" : "flex-start",
            boxShadow: isUser ? "none" : "0 1px 3px rgba(0,0,0,0.08)",
          }}
        >
          {isUser ? (
            <span style={styles.userText}>{content}</span>
          ) : (
            <div style={styles.markdown}>
              <ReactMarkdown>{content}</ReactMarkdown>
            </div>
          )}
        </div>

        {timestamp && (
          <span
            style={{
              ...styles.ts,
              alignSelf: isUser ? "flex-end" : "flex-start",
            }}
          >
            {timestamp}
          </span>
        )}
      </div>

      {/* User avatar — right side */}
      {isUser && (
        <div style={{ ...styles.avatar, background: APP.accent, color: "#fff" }}>
          我
        </div>
      )}
    </div>
  );
}

const styles = {
  row: {
    display: "flex",
    alignItems: "flex-end",
    gap: 8,
    padding: "4px 12px",
  },
  avatar: {
    flexShrink: 0,
    width: 32,
    height: 32,
    borderRadius: "50%",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontSize: 12,
    fontWeight: 600,
    lineHeight: 1,
  },
  colWrap: {
    display: "flex",
    flexDirection: "column",
    gap: 2,
    maxWidth: "72%",
  },
  bubble: {
    padding: "9px 13px",
    wordBreak: "break-word",
  },
  userText: {
    fontSize: 15,
    color: "#1a1a1a",
    lineHeight: "1.55",
    whiteSpace: "pre-wrap",
  },
  markdown: {
    fontSize: 15,
    color: APP.text1,
    lineHeight: "1.6",
    // Reset react-markdown default margins
  },
  ts: {
    fontSize: 11,
    color: APP.text4,
  },
};
