/**
 * Decide whether to seed a synthetic /doctor/my-ai history entry behind a
 * deep-link entry URL, so back-tap from the deep link unwinds to home
 * instead of exiting the app.
 *
 * Returns one of:
 *   { kind: "noop" }                   — don't seed (already at home, not a doctor path, or has history)
 *   { kind: "seed", homePath, target } — seed home then re-push target
 */
export function decideColdStartSeed({ pathname, search, hash, historyLength }) {
  const isDoctorPath =
    pathname.startsWith("/doctor/") || pathname.startsWith("/mock/doctor/");
  const isHome =
    pathname === "/doctor/my-ai" || pathname === "/mock/doctor/my-ai";
  if (!isDoctorPath || isHome || historyLength > 1) {
    return { kind: "noop" };
  }
  const homePath = pathname.startsWith("/mock/")
    ? "/mock/doctor/my-ai"
    : "/doctor/my-ai";
  return {
    kind: "seed",
    homePath,
    target: pathname + search + hash,
  };
}
