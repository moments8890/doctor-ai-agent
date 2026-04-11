# src/domain/knowledge/onboarding_scenarios.py
"""Onboarding scenario content for persona pick-your-style flow."""

GENERIC_SCENARIOS = [
    {
        "id": "postop_followup",
        "title": "术后随访",
        "patient_message": "医生，术后第三天头还是有点疼，VAS大概5-6分，伤口周围有点胀，体温37.1度。这些正常吗？要不要加点止疼药？",
        "patient_info": "患者张先生，56岁，术后第3天",
        "options": [
            {
                "id": "a",
                "text": "张叔，VAS 5-6分在术后第三天是正常的，伤口周围胀也是局部水肿的表现，体温37.1不算发热。目前不需要加止疼药，继续观察就行。如果VAS超过7分或者体温超过38.5度，随时联系我。",
                "traits": {"reply_style": "口语化，称呼用昵称", "structure": "先给结论再解释", "avoid": "以安抚为主，给具体阈值"}
            },
            {
                "id": "b",
                "text": "张先生您好。术后第三天头痛VAS 5-6分属于正常范围，伤口周围肿胀系术区局部水肿所致，体温37.1°C处于正常体温上限，暂不需要特殊处理。目前不建议增加止痛药物，继续按现有方案即可。如疼痛明显加重（VAS≥7）、体温超过38.5°C或出现恶心呕吐等情况，请及时联系。",
                "traits": {"reply_style": "书面语，称呼用全名敬称", "structure": "逐项回应", "avoid": "标注具体指标"}
            },
            {
                "id": "c",
                "text": "都是正常的。VAS 5-6分术后三天没问题，不用加药。体温也正常。疼得厉害或者烧起来了再说。",
                "traits": {"reply_style": "极简直接", "structure": "只给结论", "avoid": "不展开解释"}
            },
        ],
    },
    {
        "id": "medication_question",
        "title": "用药咨询",
        "patient_message": "医生，这个药吃了两周了，最近老觉得困，白天也没精神，是药的副作用吗？能不能换个药或者减量？",
        "patient_info": "患者李阿姨，62岁，服用左乙拉西坦",
        "options": [
            {
                "id": "a",
                "text": "李阿姨，困和没精神确实是常见的副作用，一般吃一段时间身体适应了会好一些。现在先不要自己减量，因为这个阶段预防很重要。下次复查的时候我看看情况再决定要不要调整，如果实在影响生活可以提前来一趟。",
                "traits": {"reply_style": "口语亲切，安抚为主", "closing": "留口子下次调整"}
            },
            {
                "id": "b",
                "text": "嗜睡乏力是该药的常见不良反应，多数患者2-4周内可自行缓解。目前不建议减量或换药。建议下次门诊复查时评估，如症状严重影响日常生活，可提前就诊讨论方案调整。",
                "traits": {"reply_style": "专业书面", "structure": "先解释机制再给建议"}
            },
            {
                "id": "c",
                "text": "是药的副作用，正常的，再坚持坚持。别自己减药，下次来的时候我给你看看要不要调。",
                "traits": {"reply_style": "极简口语", "structure": "直接确认+指令"}
            },
        ],
    },
    {
        "id": "urgent_symptom",
        "title": "紧急情况",
        "patient_message": "医生，我爸今天突然说头很疼，比前几天厉害多了，还吐了一次。是不是有什么问题？",
        "patient_info": "家属代问，患者术后第5天",
        "options": [
            {
                "id": "a",
                "text": "这个情况需要重视。术后突然头痛加重伴呕吐，需要排除颅内出血或脑水肿加重的可能。请尽快带他到最近的医院急诊做一个头颅CT，拿到结果后拍给我看。如果是在我们医院附近，直接来急诊找我。",
                "traits": {"reply_style": "严肃但不恐慌", "structure": "说明原因+给行动路径"}
            },
            {
                "id": "b",
                "text": "头痛突然加重加上呕吐，术后第五天这个时间点要警惕。赶紧去急诊做个CT，做完了把片子发给我。能来我们医院最好。",
                "traits": {"reply_style": "简洁紧迫", "structure": "直接给行动"}
            },
            {
                "id": "c",
                "text": "术后新发剧烈头痛伴呕吐属于危险信号，不排除迟发性颅内出血可能，建议立即前往就近医院急诊行头颅CT平扫。如结果异常请随时联系我，或直接转至我院神经外科急诊处理。",
                "traits": {"reply_style": "标准书面", "structure": "明确诊断方向+完整就医路径"}
            },
        ],
    },
]


def extract_rules_from_picks(picks: list[dict]) -> dict:
    """Extract persona rules from onboarding picks.

    picks: [{"scenario_id": "postop_followup", "option_id": "a"}, ...]
    Returns: persona fields dict ready to write.
    """
    from db.crud.persona import generate_rule_id
    from db.models.doctor_persona import EMPTY_PERSONA_FIELDS

    fields = EMPTY_PERSONA_FIELDS()

    for pick in picks:
        scenario = next((s for s in GENERIC_SCENARIOS if s["id"] == pick.get("scenario_id")), None)
        if not scenario:
            continue
        option = next((o for o in scenario["options"] if o["id"] == pick.get("option_id")), None)
        if not option:
            continue

        traits = option.get("traits", {})
        for field_key, text in traits.items():
            if field_key in fields and text:
                # Avoid duplicate rules
                existing_texts = {r["text"] for r in fields[field_key]}
                if text not in existing_texts:
                    fields[field_key].append({
                        "id": generate_rule_id(),
                        "text": text,
                        "source": "onboarding",
                        "usage_count": 0,
                    })

    return fields
