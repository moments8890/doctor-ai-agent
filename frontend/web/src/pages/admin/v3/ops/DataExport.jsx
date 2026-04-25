// DataExport — 数据导出 placeholder.
// Spec scope: this is a placeholder per Phase 3 plan; full export wizard
// is out of scope and will land in a separate task.

import { COLOR, FONT, RADIUS, SHADOW } from "../tokens";

export default function DataExport() {
  return (
    <section
      style={{
        background: COLOR.bgCard,
        border: `1px solid ${COLOR.borderSubtle}`,
        borderRadius: RADIUS.lg,
        boxShadow: SHADOW.s1,
        padding: "48px 24px",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        textAlign: "center",
        gap: 12,
        minHeight: 280,
        justifyContent: "center",
      }}
    >
      <div
        style={{
          width: 56,
          height: 56,
          borderRadius: "50%",
          background: COLOR.infoTint,
          color: COLOR.info,
          display: "grid",
          placeItems: "center",
        }}
      >
        <span className="material-symbols-outlined" style={{ fontSize: 28 }}>
          download
        </span>
      </div>
      <div
        style={{
          fontSize: 16,
          fontWeight: 600,
          color: COLOR.text1,
        }}
      >
        数据导出 — 该模块即将上线
      </div>
      <div
        style={{
          fontSize: FONT.body,
          color: COLOR.text2,
          maxWidth: 420,
          lineHeight: 1.55,
        }}
      >
        我们正在打磨患者列表、AI 决策记录和合作伙伴报表的 CSV / PDF
        导出能力。试点期间如需导出，请联系运营团队。
      </div>
    </section>
  );
}
