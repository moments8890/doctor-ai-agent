/**
 * Show a red circle on every Playwright click action in video recordings.
 */
import type { Page } from "@playwright/test";

export async function injectClickIndicator(page: Page) {
  // Use page.evaluate after each navigation — reliable across all PW versions
  const inject = async () => {
    try {
      await page.evaluate(() => {
        if ((window as any).__pwTapReady) return;
        (window as any).__pwTapReady = true;

        const s = document.createElement("style");
        s.textContent = `
          .pw-tap {
            position: fixed; pointer-events: none; z-index: 2147483647;
            width: 36px; height: 36px; border-radius: 50%;
            border: 3px solid red; background: rgba(255,0,0,0.35);
            transform: translate(-50%,-50%) scale(1);
            animation: pw-ring 0.2s ease-out forwards;
          }
          @keyframes pw-ring {
            0%   { transform: translate(-50%,-50%) scale(0.8); opacity: 1; }
            100% { transform: translate(-50%,-50%) scale(1.5); opacity: 0; }
          }
        `;
        (document.head || document.documentElement).appendChild(s);

        ["pointerdown"].forEach((evt) => {
          document.addEventListener(evt, (e: any) => {
            const x = e.clientX || 0;
            const y = e.clientY || 0;
            if (!x && !y) return;
            const d = document.createElement("div");
            d.className = "pw-tap";
            d.style.left = x + "px";
            d.style.top = y + "px";
            (document.body || document.documentElement).appendChild(d);
            setTimeout(() => { try { d.remove(); } catch {} }, 250);
          }, true);
        });
      });
    } catch {
      // page closed or navigating — ignore
    }
  };

  // Inject after every navigation
  page.on("load", inject);
  // Also inject right now
  await inject();
}
