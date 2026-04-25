// Placeholder pages for the 概览 sidebar items that don't have a real
// implementation yet. Each click lands here with a "coming soon" empty state
// so the sidebar feels alive while the real cross-doctor pages get built.
//
// When a real page lands (e.g. cross-doctor 全体患者 list), import it inside
// `AdminPageV3` for that subsection and remove the placeholder branch.

import EmptyState from "../components/EmptyState";

const COPY = {
  dashboard: {
    icon: "dashboard",
    title: "仪表盘 即将上线",
    desc: "跨医生的总览仪表盘正在搭建。当前可在「全体医生」中选择某位医生查看其总览。",
  },
  patients: {
    icon: "groups",
    title: "全体患者 即将上线",
    desc: "跨医生的患者列表与筛选正在搭建。当前可在「全体医生」中选择医生后查看其患者。",
  },
  chat: {
    icon: "forum",
    title: "沟通中心 即将上线",
    desc: "跨医生的沟通汇总正在搭建。当前可在医生页面的「沟通」标签查看单医生的会话。",
  },
  ai: {
    icon: "network_intelligence",
    title: "知识 & AI 即将上线",
    desc: "跨医生的知识库与 AI 决策汇总正在搭建。当前可在医生页面的「AI 与知识」标签查看。",
  },
};

export default function OverviewPlaceholder({ sub }) {
  const copy = COPY[sub] || COPY.dashboard;
  return (
    <div style={{ paddingTop: 24 }}>
      <EmptyState icon={copy.icon} title={copy.title} desc={copy.desc} />
    </div>
  );
}
