/**
 * Debug HUD for diagnosing mobile keyboard viewport behavior.
 *
 * Enable by appending ?debug=kb to any route URL. Shows live:
 *   innerHeight, visualViewport.height/offsetTop, clientHeight,
 *   --vvh, --keyboard-height, window.scrollY, body overflow, focus,
 *   and a rolling log of the last 6 events (focusin, focusout,
 *   vv.resize, vv.scroll, window scroll).
 */
import { useEffect, useRef, useState } from "react";

const MAX_EVENTS = 6;

function snap() {
  const vv = window.visualViewport;
  const root = document.documentElement;
  const cs = getComputedStyle(root);
  const active = document.activeElement;
  return {
    innerH: window.innerHeight,
    vvH: vv ? Math.round(vv.height) : null,
    vvTop: vv ? Math.round(vv.offsetTop) : null,
    clientH: root.clientHeight,
    scrollY: Math.round(window.scrollY),
    vvhVar: cs.getPropertyValue("--vvh").trim() || "(unset)",
    kbVar: cs.getPropertyValue("--keyboard-height").trim() || "(unset)",
    bodyOverflow: document.body.style.overflow || "(empty)",
    htmlOverflow: root.style.overflow || "(empty)",
    focus: active ? `${active.tagName}` : "none",
  };
}

export default function KeyboardDebugHUD() {
  const enabled =
    typeof window !== "undefined" &&
    window.location.search.includes("debug=kb");

  const [data, setData] = useState(enabled ? snap() : null);
  const [events, setEvents] = useState([]);
  const [hidden, setHidden] = useState(false);
  const startRef = useRef(Date.now());

  useEffect(() => {
    if (!enabled) return;

    const tick = () => setData(snap());
    const log = (label) => {
      const t = Date.now() - startRef.current;
      const s = snap();
      const line = `t+${t}ms ${label} sY=${s.scrollY} vvT=${s.vvTop ?? "-"} vvH=${s.vvH ?? "-"}`;
      setEvents((prev) => [line, ...prev].slice(0, MAX_EVENTS));
      setData(s);
    };

    const onFocusIn = (e) => log(`focusin:${e.target?.tagName || "?"}`);
    const onFocusOut = (e) => log(`focusout:${e.target?.tagName || "?"}`);
    const onWinScroll = () => log("win:scroll");

    const vv = window.visualViewport;
    const onVvResize = () => log("vv:resize");
    const onVvScroll = () => log("vv:scroll");

    document.addEventListener("focusin", onFocusIn, true);
    document.addEventListener("focusout", onFocusOut, true);
    window.addEventListener("scroll", onWinScroll);
    if (vv) {
      vv.addEventListener("resize", onVvResize);
      vv.addEventListener("scroll", onVvScroll);
    }
    const interval = setInterval(tick, 500);

    return () => {
      document.removeEventListener("focusin", onFocusIn, true);
      document.removeEventListener("focusout", onFocusOut, true);
      window.removeEventListener("scroll", onWinScroll);
      if (vv) {
        vv.removeEventListener("resize", onVvResize);
        vv.removeEventListener("scroll", onVvScroll);
      }
      clearInterval(interval);
    };
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
        top: 120,
        right: 6,
        zIndex: 99999,
        background: "rgba(0,0,0,0.85)",
        color: "#0f0",
        fontFamily: "ui-monospace, Menlo, monospace",
        fontSize: 10,
        lineHeight: 1.3,
        padding: "6px 8px",
        borderRadius: 4,
        minWidth: 220,
        maxWidth: 280,
        pointerEvents: "auto",
      }}
    >
      {row("innerH", data.innerH)}
      {row("vv.h/top", `${data.vvH ?? "—"} / ${data.vvTop ?? "—"}`)}
      {row("clientH", data.clientH)}
      {row("scrollY", data.scrollY)}
      {row("--vvh", data.vvhVar)}
      {row("--kbH", data.kbVar)}
      {row("body.ovf", data.bodyOverflow)}
      {row("html.ovf", data.htmlOverflow)}
      {row("focus", data.focus)}
      <div style={{ marginTop: 4, borderTop: "1px dashed #444", paddingTop: 4, opacity: 0.9 }}>
        {events.length === 0 ? (
          <div style={{ opacity: 0.5 }}>no events yet</div>
        ) : (
          events.map((e, i) => (
            <div
              key={i}
              style={{
                whiteSpace: "nowrap",
                overflow: "hidden",
                textOverflow: "ellipsis",
                opacity: i === 0 ? 1 : 0.55,
              }}
            >
              {e}
            </div>
          ))
        )}
      </div>
      <div style={{ marginTop: 4, textAlign: "right", opacity: 0.45, fontSize: 9 }}>
        tap to hide
      </div>
    </div>
  );
}
