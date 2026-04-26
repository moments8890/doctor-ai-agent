/**
 * SuggestionChips — clickable chip row rendered below an AI bubble that
 * carries `suggestions: string[]`.
 *
 * UX: tapping a chip sends that text as a new patient turn (via onPick).
 * The first chip is treated as the recommended option (primary color);
 * the remainder are secondary. Free-text input via ChatComposer remains
 * the canonical fallback path.
 *
 * Sizing/colors come from v2 tokens (APP, FONT, RADIUS); never hardcoded.
 */

import { APP, FONT, RADIUS } from "../theme";

export default function SuggestionChips({ suggestions, onPick, disabled }) {
  if (!Array.isArray(suggestions) || suggestions.length === 0) return null;

  return (
    <div style={styles.row}>
      {suggestions.map((s, i) => {
        const isPrimary = i === 0;
        const baseStyle = isPrimary ? styles.chipPrimary : styles.chipSecondary;
        return (
          <span
            key={`${i}-${s}`}
            role="button"
            tabIndex={0}
            aria-disabled={disabled || undefined}
            onClick={disabled ? undefined : () => onPick?.(s)}
            style={{
              ...baseStyle,
              opacity: disabled ? 0.5 : 1,
              cursor: disabled ? "default" : "pointer",
            }}
          >
            {s}
          </span>
        );
      })}
    </div>
  );
}

const styles = {
  row: {
    display: "flex",
    flexWrap: "wrap",
    gap: 6,
    // Aligned under the AI bubble (which has paddingLeft 44 for the avatar)
    padding: "4px 12px 0 44px",
  },
  chipPrimary: {
    display: "inline-block",
    padding: "6px 12px",
    borderRadius: RADIUS.lg,
    fontSize: FONT.sm,
    fontWeight: 500,
    background: APP.primary,
    color: APP.white,
    border: `1px solid ${APP.primary}`,
    userSelect: "none",
    whiteSpace: "nowrap",
  },
  chipSecondary: {
    display: "inline-block",
    padding: "6px 12px",
    borderRadius: RADIUS.lg,
    fontSize: FONT.sm,
    fontWeight: 500,
    background: APP.surface,
    color: APP.primary,
    border: `1px solid ${APP.primary}`,
    userSelect: "none",
    whiteSpace: "nowrap",
  },
};
