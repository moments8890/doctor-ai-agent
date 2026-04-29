// AiDisclaimer — small footer note that surfaces wherever the doctor sees
// AI-generated content. Restored 2026-04-28 after the v2 card-layout
// redesign dropped the v1 disclaimer string.
//
// Usage: drop <AiDisclaimer /> at the bottom of any scrollable AI page,
// just before <SafeArea position="bottom" />.

import { APP, FONT } from "../theme";

export default function AiDisclaimer() {
  return (
    <div
      style={{
        textAlign: "center",
        fontSize: FONT.xs,
        color: APP.text4,
        padding: "20px 16px 8px",
      }}
    >
      本服务为AI生成内容，结果仅供参考
    </div>
  );
}
