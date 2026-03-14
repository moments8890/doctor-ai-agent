"""User-facing message strings.

Usage: ``from messages import M`` then ``M.draft_confirmed``.

LLM system prompts live in ``prompts/*.md``, not here.
"""
from __future__ import annotations

from utils.prompt_loader import get_prompt_sync


class M:
    """Message constants."""

    # -- fast-path replies --------------------------------------------------
    greeting = (
        "您好！我是您的专属医助，很高兴为您服务。\n\n"
        "我可以帮您：\n"
        "• 建立患者档案（如：新患者张三，男，45岁）\n"
        "• 快速录入门诊病历（如：张三，胸痛2小时）\n"
        "• 查询患者历史记录（如：查询张三）\n"
        "• 管理待办任务和随访提醒\n\n"
        "请直接说您想做什么，或描述患者情况开始录入。"
    )
    help = (
        "📋 患者管理\n"
        "  新患者[姓名] — 创建新患者\n"
        "  查看[姓名] — 查看患者病历\n\n"
        "📝 病历\n"
        "  直接描述病情 — 自动生成结构化病历草稿\n"
        "  确认 / 取消 — 保存或放弃草稿\n\n"
        "📥 导入\n"
        "  发送 PDF / 图片 — 自动识别并创建\n\n"
        "📌 任务\n"
        "  待办任务 — 查看所有任务\n"
        "  完成 3 — 标记任务#3完成\n\n"
        "📊 导出\n"
        "  PDF:患者姓名 — 导出病历PDF"
    )

    # -- turn orchestrator --------------------------------------------------
    empty_input = "请输入内容。"

    # -- draft guard --------------------------------------------------------
    draft_pending = "您有{patient}的待确认病历草稿。请回复「确认」保存，或「取消」放弃。"
    draft_expired = "草稿已过期或不存在。"
    draft_save_failed = "保存失败，请重试。"
    draft_confirmed = "✅ {patient}的病历已保存。"
    draft_abandoned = "已放弃{patient}的病历草稿。"

    # -- commit engine ------------------------------------------------------
    need_patient_name = "请提供患者姓名。"
    patient_not_found = "未找到患者【{name}】。请确认姓名或说「新建患者 {name}」。"
    unsaved_notes_cleared = "注意：关于{name}的未保存记录已清除。"
    patient_exists_selected = "患者【{name}】已存在，已为您选择。"
    create_patient_failed = "创建患者失败：{error}"
    need_patient_for_draft = "请先选择或创建患者，再生成病历草稿。"
    no_clinical_content = "没有找到需要记录的临床内容。请先描述患者情况。"
    structuring_failed = "病历生成失败，请稍后重试。"
    draft_created = "📋 已为【{patient}】生成病历草稿：\n{preview}\n\n回复「确认」保存，「取消」放弃。"
    patient_created_with_draft = "✅ 已为【{patient}】建档。\n{draft_reply}"

    # -- conversation model fallbacks ---------------------------------------
    parse_error_reply = "抱歉，我没有理解您的意思。请再说一次。"
    default_reply = "好的，请继续。"
    service_unavailable = "服务暂时不可用，请稍后再试。"

    # -- conversation model system prompt (loaded from prompts/conversation.md)
    system_prompt = get_prompt_sync("conversation")

    # -- context block labels (LLM-facing) ----------------------------------
    ctx_patient = "当前患者"
    ctx_no_patient = "未选择"
    ctx_note = "临床记录"
    ctx_candidate = "候选患者"
    ctx_summary = "摘要"
