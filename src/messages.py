"""User-facing message strings.

Usage: ``from messages import M`` then ``M.greeting``.

LLM system prompts live in ``prompts/*.md``, not here.
Agent-generated replies replace most of these — only fast-path
and error messages remain.
"""
from __future__ import annotations


class M:
    """Message constants."""

    # -- fast-path replies --------------------------------------------------
    greeting = (
        "您好！我是您的专属医助，很高兴为您服务。\n\n"
        "我可以帮您：\n\n"
        "- 建立患者档案（如：新患者张三，男，45岁）\n"
        "- 快速录入门诊病历（如：张三，胸痛2小时）\n"
        "- 查询患者历史记录（如：查询张三）\n"
        "- 管理待办任务和随访提醒\n\n"
        "请直接说您想做什么，或描述患者情况开始录入。"
    )
    help = (
        "**患者管理**\n\n"
        "- 新患者[姓名] — 创建新患者\n"
        "- 查看[姓名] — 查看患者病历\n\n"
        "**病历**\n\n"
        "- 直接描述病情 — 自动生成结构化病历草稿\n"
        "- 确认 / 取消 — 保存或放弃草稿\n\n"
        "**导入**\n\n"
        "- 发送 PDF / 图片 — 自动识别并创建\n\n"
        "**任务**\n\n"
        "- 待办任务 — 查看所有任务\n"
        "- 完成 3 — 标记任务#3完成\n\n"
        "**导出**\n\n"
        "- PDF:患者姓名 — 导出病历PDF"
    )

    # -- turn orchestrator --------------------------------------------------
    empty_input = "请输入内容。"

    # -- draft lifecycle ----------------------------------------------------
    draft_expired = "草稿已过期或不存在。"
    draft_save_failed = "保存失败，请重试。"
    draft_confirmed = "✅ {patient}的病历已保存。"
    draft_abandoned = "已放弃{patient}的病历草稿。"

    # -- error / fallback ---------------------------------------------------
    parse_error_reply = "抱歉，我没有理解您的意思。请再说一次。"
    default_reply = "好的，请继续。"
    service_unavailable = "服务暂时不可用，请稍后再试。"
