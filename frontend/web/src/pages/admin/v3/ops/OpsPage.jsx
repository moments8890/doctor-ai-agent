// OpsPage — top-level shell for the 运营 module.
// Routes the four sub-sections (invites / pilot / report / export) to
// their corresponding sub-page components. The breadcrumb is rendered
// by index.jsx so this component focuses on body content.
//
// URL contract: ?v=3&section=ops/<subsection>
//   ops/invites — InviteCodes
//   ops/pilot   — PilotProgress
//   ops/report  — PartnerReport
//   ops/export  — DataExport (placeholder)

import { COLOR, FONT } from "../tokens";
import InviteCodes from "./InviteCodes";
import PilotProgress from "./PilotProgress";
import PartnerReport from "./PartnerReport";
import DataExport from "./DataExport";

const TITLES = {
  invites: "邀请码",
  pilot: "试点进度",
  report: "合作伙伴报表",
  export: "数据导出",
};

export default function OpsPage({ subsection }) {
  const sub = subsection || "invites";
  const title = TITLES[sub] || "运营";

  let body;
  if (sub === "invites") body = <InviteCodes />;
  else if (sub === "pilot") body = <PilotProgress />;
  else if (sub === "report") body = <PartnerReport />;
  else if (sub === "export") body = <DataExport />;
  else body = <UnknownSubsection sub={sub} />;

  return (
    <div>
      <h1
        style={{
          fontSize: 22,
          fontWeight: 600,
          letterSpacing: "-0.015em",
          color: COLOR.text1,
          margin: "0 0 16px",
        }}
      >
        {title}
      </h1>
      {body}
    </div>
  );
}

function UnknownSubsection({ sub }) {
  return (
    <div
      style={{
        padding: "40px 16px",
        color: COLOR.text2,
        fontSize: FONT.body,
        textAlign: "center",
      }}
    >
      未知运营页面：{sub}
    </div>
  );
}
