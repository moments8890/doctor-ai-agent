/**
 * Card — the standard floating white card used across v2 doctor + patient pages.
 *
 * Sits on the gray pageContainer bg with a small horizontal margin. Section
 * headers and other chrome go OUTSIDE the Card on the gray bg, not inside it.
 *
 * Pass `style` to override or extend (e.g., `marginTop: 8` to stack with sibling
 * cards). The default `margin: "0 12px"` matches the doctor SettingsPage pattern.
 */
import { APP, RADIUS } from "../theme";

export default function Card({ children, style }) {
  return (
    <div
      style={{
        background: APP.surface,
        margin: "0 12px",
        borderRadius: RADIUS.lg,
        overflow: "hidden",
        ...style,
      }}
    >
      {children}
    </div>
  );
}
