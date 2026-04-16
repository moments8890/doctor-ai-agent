// frontend/web/src/config/releases.js
//
// Release notes content. Newest release first.
// On each release, prepend a new entry with the version, date, title,
// and feature cards. Icons are direct MUI component imports.

import AutoAwesomeIcon from "@mui/icons-material/AutoAwesome";
import MenuBookIcon from "@mui/icons-material/MenuBook";
import GroupsIcon from "@mui/icons-material/Groups";
import AssignmentTurnedInIcon from "@mui/icons-material/AssignmentTurnedIn";

export const RELEASES = [
  {
    version: "2.0.0",
    date: "2026-04-15",
    title: "v2.0 更新内容",
    features: [
      {
        icon: AutoAwesomeIcon,
        title: "AI 智能随访",
        description: "基于您的知识库，自动生成个性化随访建议",
      },
      {
        icon: MenuBookIcon,
        title: "知识库升级",
        description: "支持网页导入、拍照上传，AI 自动提取要点",
      },
      {
        icon: GroupsIcon,
        title: "患者管理",
        description: "查看患者问诊记录，跟踪随访进度",
      },
      {
        icon: AssignmentTurnedInIcon,
        title: "审核工作台",
        description: "一站式审核 AI 生成的诊断建议和回复草稿",
      },
    ],
  },
];

export function getLatestRelease() {
  return RELEASES[0] || null;
}
