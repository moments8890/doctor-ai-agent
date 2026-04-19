/**
 * NameAvatar — circular initial-letter avatar.
 *
 * Uses antd-mobile `Avatar` with a `fallback` prop. antd-mobile's Avatar only
 * renders an <img> from `src`; text has to ride in via `fallback`, which is
 * shown whenever no src is provided.
 *
 * Usage:
 *   <NameAvatar name="张三" />
 *   <NameAvatar name="张三" size={36} color={APP.accent} />
 */
import { Avatar } from "antd-mobile";
import { APP, FONT } from "../theme";

export default function NameAvatar({
  name,
  size = 40,
  color = APP.primary,
  charPosition = "first",
}) {
  const ch =
    charPosition === "last"
      ? (name || "?").slice(-1)
      : (name || "?")[0];

  const fontSize = size <= 36 ? FONT.sm : FONT.md;

  return (
    <Avatar
      src=""
      fallback={
        <div
          style={{
            width: size,
            height: size,
            borderRadius: 8,
            backgroundColor: APP.primaryLight,
            color: APP.primary,
            fontSize,
            fontWeight: 600,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          {ch}
        </div>
      }
      style={{ "--size": `${size}px`, flexShrink: 0 }}
    />
  );
}
