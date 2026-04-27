// frontend/web/src/config/releases.js
//
// Release notes content. Newest release first.
// On each release, prepend a new entry with the version, date, title,
// and feature cards. Icons are direct MUI component imports.

import AutoAwesomeIcon from "@mui/icons-material/AutoAwesome";
import MenuBookIcon from "@mui/icons-material/MenuBook";
import GroupsIcon from "@mui/icons-material/Groups";
import AssignmentTurnedInIcon from "@mui/icons-material/AssignmentTurnedIn";
import QuestionAnswerOutlinedIcon from "@mui/icons-material/QuestionAnswerOutlined";
import PsychologyOutlinedIcon from "@mui/icons-material/PsychologyOutlined";
import FactCheckOutlinedIcon from "@mui/icons-material/FactCheckOutlined";
import NotificationsActiveOutlinedIcon from "@mui/icons-material/NotificationsActiveOutlined";
import QrCode2OutlinedIcon from "@mui/icons-material/QrCode2Outlined";
import AddToHomeScreenOutlinedIcon from "@mui/icons-material/AddToHomeScreenOutlined";

export const RELEASES = [
  {
    version: "2.1.0",
    date: "2026-04-26",
    title: "v2.1 更新内容",
    features: [
      {
        icon: QuestionAnswerOutlinedIcon,
        title: "AI 智能问诊",
        description: "患者就诊前自动完成结构化问诊，到诊时主诉、现病史、既往史已就位",
      },
      {
        icon: PsychologyOutlinedIcon,
        title: "诊断更可靠",
        description: "AI 诊断附带临床推理证据，可追溯思考过程；自动重试异常输出",
      },
      {
        icon: FactCheckOutlinedIcon,
        title: "审核更高效",
        description: "完成一项审核自动进入下一项，连贯流畅；待审核直达首条待办",
      },
      {
        icon: NotificationsActiveOutlinedIcon,
        title: "新患者一眼可见",
        description: "今日关注 自动突出新患者；患者列表带 新 / 待关注 提示",
      },
      {
        icon: QrCode2OutlinedIcon,
        title: "扫码加号",
        description: "在 设置-我的二维码 分享给患者，患者扫码即加入您的列表",
      },
      {
        icon: AddToHomeScreenOutlinedIcon,
        title: "添加到桌面",
        description: "一键将工作台添加到主屏，下次打开像 App 一样直达",
      },
    ],
  },
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
