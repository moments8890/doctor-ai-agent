export const MOBILE_FRAME_CONTAINER_ID = "mobile-frame-container";

export function getDialogContainer() {
  if (typeof document === "undefined") return undefined;
  return document.getElementById(MOBILE_FRAME_CONTAINER_ID) || document.body;
}
