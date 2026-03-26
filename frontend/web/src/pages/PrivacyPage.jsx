/** @route /privacy */
import { Box, Typography } from "@mui/material";
import { COLOR, TYPE } from "../theme";

const SECTIONS = [
  {
    title: "一、我们收集的信息",
    content: [
      "我们会收集以下类型的信息：",
      "",
      "1. 您主动提供的信息",
      "• 账号信息：手机号码、出生年份（用于登录验证）",
      "• 医生信息：姓名、执业信息（仅医生用户）",
      "• 患者信息：姓名、性别、年龄、联系方式、病历资料（由医生录入）",
      "",
      "2. 自动收集的信息",
      "• 设备信息：设备型号、操作系统版本",
      "• 网络信息：网络类型",
      "• 日志信息：访问时间、功能使用记录",
      "",
      "3. 我们不会收集的信息",
      "• 我们不会收集您的精确地理位置",
      "• 我们不会读取您的通讯录、短信、通话记录",
      "• 我们不会访问您的相册（除非您主动上传图片）",
    ],
  },
  {
    title: "二、信息的使用目的",
    content: [
      "我们收集的信息仅用于：",
      "• 提供和改进应用功能",
      "• 记录管理和辅助分析",
      "• 账号验证和安全保障",
      "• 用户体验优化",
    ],
  },
  {
    title: "三、信息的存储和保护",
    content: [
      "• 您的数据存储在中国境内的云服务器",
      "• 我们采用加密传输（HTTPS）和加密存储保护您的数据",
      "• 用户数据与普通数据隔离存储",
      "• 我们会定期进行安全评估和漏洞扫描",
    ],
  },
  {
    title: "四、信息的共享",
    content: [
      "我们不会将您的个人信息出售、交易或转让给第三方，但以下情况除外：",
      "• 获得您的明确同意",
      "• 根据法律法规的要求",
      "• 为维护公共利益所必需",
    ],
  },
  {
    title: "五、AI 辅助功能说明",
    content: [
      "本应用使用人工智能技术辅助健康信息整理和分析：",
      "• AI 生成的内容仅供参考，不构成诊断依据",
      "• AI 处理的数据不会用于模型训练",
      "• 最终决策由持证专业人员做出",
    ],
  },
  {
    title: "六、您的权利",
    content: [
      "您有权：",
      "• 查看和修改您的个人信息",
      "• 删除您的账号和相关数据",
      "• 撤回您的授权同意",
      "• 获取您个人信息的副本",
    ],
  },
  {
    title: "七、未成年人保护",
    content: [
      "本应用面向专业人员，不面向未满 18 周岁的未成年人。",
    ],
  },
  {
    title: "八、隐私政策更新",
    content: [
      "我们可能会适时更新本政策。更新后会在应用内通知您。",
    ],
  },
  {
    title: "九、联系我们",
    content: [
      "如有任何问题，请联系：",
      "• 邮箱：support@doctoragentai.cn",
    ],
  },
];

export default function PrivacyPage() {
  return (
    <Box sx={{
      minHeight: "100vh",
      bgcolor: COLOR.white,
      display: "flex",
      justifyContent: "center",
      py: 4,
      px: 2,
    }}>
      <Box sx={{ maxWidth: 680, width: "100%" }}>
        <Typography sx={{ ...TYPE.title, fontSize: 20, mb: 1, textAlign: "center" }}>
          鲸鱼随行隐私政策
        </Typography>
        <Typography sx={{ ...TYPE.caption, color: COLOR.text4, textAlign: "center", mb: 4 }}>
          最后更新日期：2026 年 3 月 23 日
        </Typography>

        <Typography sx={{ ...TYPE.body, color: COLOR.text2, lineHeight: 1.8, mb: 3 }}>
          「鲸鱼随行」由苏州市昆山市鲸鱼互联网有限责任公司（以下简称"我们"）开发和运营。我们深知个人信息对您的重要性，将严格遵守《中华人民共和国个人信息保护法》《中华人民共和国数据安全法》《中华人民共和国网络安全法》等法律法规，保护您的个人信息安全。
        </Typography>

        {SECTIONS.map((section) => (
          <Box key={section.title} sx={{ mb: 3 }}>
            <Typography sx={{ ...TYPE.heading, color: COLOR.text1, mb: 1 }}>
              {section.title}
            </Typography>
            {section.content.map((line, i) =>
              line === "" ? (
                <Box key={i} sx={{ height: 8 }} />
              ) : (
                <Typography key={i} sx={{ ...TYPE.body, color: COLOR.text2, lineHeight: 1.8 }}>
                  {line}
                </Typography>
              )
            )}
          </Box>
        ))}
      </Box>
    </Box>
  );
}
