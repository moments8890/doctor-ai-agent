/**
 * Debug HUD for diagnosing mobile keyboard viewport behavior.
 *
 * Enable by appending ?debug=kb to any route URL. Shows live:
 *   innerHeight, visualViewport.height, documentElement.clientHeight,
 *   --vvh (if set), --keyboard-height (if set), activeElement tag.
 *
 * Updates on visualViewport.resize / scroll / focusin / focusout.
 * Fixed top-right, dismissable by tapping.
 */
import { useEffect, useState } from "react";

function read() {
  const vv = window.visualViewport;
  const root = document.documentElement;
  const cs = getComputedStyle(root);
  const active = document.activeElement;
  return {
    innerH: window.innerHeight,
    vvH: vv ? Math.round(vv.height) : null,
    vvOffsetTop: vv ? Math.round(vv.offsetTop) : null,
    clientH: root.clientHeight,
    vvhVar: cs.getPropertyValue("--vvh").trim() || "(unset)",
    kbVar: cs.getPropertyValue("--keyboard-height").trim() || "(unset)",
    focus: active ? `${active.tagName}${active.id ? "#" + active.id : ""}` : "none",
  };
}

export default function KeyboardDebugHUD() {
  const enabled =
    typeof window !== "undefined" &&
    window.location.search.includes("debug=kb");

  const [data, setData] = useState(enabled ? read() : null);
  const [hidden, setHidden] = useState(false);

  useEffect(() => {
    if (!enabled) return;
    const tick = () => setData(read());
    tick();
    const vv = window.visualViewport;
    const fns = [];
    if (vv) {
      vv.addEventListener("resize", tick);
      vv.addEventListener("scroll", tick);
      fns.push(() => vv.removeEventListener("resize", tick));
      fns.push(() => vv.removeEventListener("scroll", tick));
    }
    window.addEventListener("resize", tick);
    document.addEventListener("focusin", tick);
    document.addEventListener("focusout", tick);
    fns.push(() => window.removeEventListener("resize", tick));
    fns.push(() => document.removeEventListener("focusin", tick));
    fns.push(() => document.removeEventListener("focusout", tick));
    const interval = setInterval(tick, 500);
    fns.push(() => clearInterval(interval));
    return () => fns.forEach((f) => f());
  }, [enabled]);

  if (!enabled || hidden || !data) return null;

  const row = (label, val) => (
    <div style={{ display: "flex", gap: 6, justifyContent: "space-between" }}>
      <span style={{ opacity: 0.7 }}>{label}</span>
      <span>{String(val)}</span>
    </div>
  );

  return (
    <div
      onClick={() => setHidden(true)}
      style={{
        position: "fixed",
        bottom: 6,
        right: 6,
        zIndex: 99999,
        background: "rgba(0,0,0,0.82)",
        color: "#0f0",
        fontFamily: "ui-monospace, Menlo, monospace",
        fontSize: 10,
        lineHeight: 1.35,
        padding: "6px 8px",
        borderRadius: 4,
        minWidth: 165,
        pointerEvents: "auto",
      }}
    >
      {row("innerH", data.innerH)}
      {row("vv.h", data.vvH ?? "—")}
      {row("vv.top", data.vvOffsetTop ?? "—")}
      {row("clientH", data.clientH)}
      {row("--vvh", data.vvhVar)}
      {row("--kbH", data.kbVar)}
      {row("focus", data.focus)}
      <div
        style={{
          marginTop: 4,
          textAlign: "right",
          opacity: 0.5,
          fontSize: 9,
        }}
      >
        tap to hide
      </div>
    </div>
  );
}
