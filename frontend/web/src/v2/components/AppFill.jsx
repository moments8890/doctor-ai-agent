/**
 * AppFill — filled variant to pair with antd-mobile-icons AppOutline.
 *
 * The library ships AppOutline only, so the "我的AI" tab had no active-state
 * fill. This mirrors the outlined hexagon-with-cube silhouette but renders
 * it as a solid shape, matching TeamFill / CheckShieldFill / ClockCircleFill.
 */
export default function AppFill(props) {
  return (
    <svg
      width="1em"
      height="1em"
      viewBox="0 0 48 48"
      xmlns="http://www.w3.org/2000/svg"
      {...props}
      style={{ verticalAlign: "-0.125em", ...(props.style || {}) }}
      className={["antd-mobile-icon", props.className].filter(Boolean).join(" ")}
    >
      {/* Solid hexagon body */}
      <path
        fill="currentColor"
        d="M38.667 11.528L27.351 4.908c-2.068-1.211-4.62-1.211-6.693 0L9.337 11.528C7.27 12.739 6 14.968 6 17.38v13.24c0 2.412 1.274 4.645 3.337 5.852l11.317 6.62c2.072 1.21 4.62 1.21 6.692 0l11.317-6.62C40.73 35.266 42 33.032 42 30.62V17.385c.004-2.417-1.265-4.647-3.333-5.857z"
      />
      {/* Inner cube edges — drawn white to cut through the solid body */}
      <path
        stroke="#fff"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        fill="none"
        d="M24 24 L24 42 M24 24 L9 15.5 M24 24 L39 15.5"
      />
    </svg>
  );
}
