"""
向本地 SQLite 数据库填充真实的模拟数据（用于开发/演示环境）。
运行方式：python scripts/seed_mock_data.py

Seed the local SQLite DB with realistic mock data for development/demo.
"""
import asyncio
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("ENVIRONMENT", "development")

from db.engine import AsyncSessionLocal
from db.init_db import create_tables
from db.models import Doctor, InviteCode, Patient, MedicalRecordDB, DoctorTask
from sqlalchemy import text

def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)

def ago(days=0, hours=0):
    return utcnow() - timedelta(days=days, hours=hours)

def ahead(days=0):
    return utcnow() + timedelta(days=days)

# ── doctors ───────────────────────────────────────────────────────────────────

DOCTORS = [
    dict(doctor_id="demo_neuro", name="张伟", specialty="神经内科", channel="app"),
    dict(doctor_id="demo_cardio", name="李明", specialty="心内科", channel="app"),
]

INVITE_CODES = [
    dict(code="NEURO2025", doctor_id="demo_neuro", doctor_name="张伟"),
    dict(code="CARDIO888", doctor_id="demo_cardio", doctor_name="李明"),
]

# ── patients ──────────────────────────────────────────────────────────────────
# (doctor_id, name, gender, yob, category)
PATIENTS = [
    ("demo_neuro",  "王建国", "male",   1955, "stroke"),
    ("demo_neuro",  "陈秀英", "female", 1962, "parkinson"),
    ("demo_neuro",  "赵志强", "male",   1948, "dementia"),
    ("demo_neuro",  "刘桂兰", "female", 1970, "epilepsy"),
    ("demo_neuro",  "孙明远", "male",   1980, "headache"),
    ("demo_neuro",  "周海燕", "female", 1958, "stroke"),
    ("demo_cardio", "吴国强", "male",   1950, "heart_failure"),
    ("demo_cardio", "郑淑华", "female", 1965, "arrhythmia"),
    ("demo_cardio", "冯建军", "male",   1972, "hypertension"),
    ("demo_cardio", "蒋雪梅", "female", 1957, "coronary"),
]

# ── records ───────────────────────────────────────────────────────────────────
# Each entry is a list of (content, tags, encounter_type, days_ago, signed_off)

RECORDS = [
    # 王建国 — stroke
    [
        (
            "主诉：右侧肢体无力伴言语不清2天。\n"
            "现病史：患者2天前无明显诱因出现右侧肢体无力，行走不稳，伴言语不清，无头痛头晕，无恶心呕吐，无意识丧失。\n"
            "既往史：高血压病史10年，长期服用氨氯地平5mg qd。\n"
            "查体：BP 158/92mmHg，神清，构音障碍，右侧肢体肌力4级，Babinski征阳性。\n"
            "辅助检查：头颅MRI示左侧基底节区急性脑梗死。\n"
            "诊断：急性脑梗死（左侧基底节）\n"
            "治疗方案：阿司匹林100mg+氯吡格雷75mg双联抗板，他汀调脂，规范康复训练。\n"
            "随访计划：2周后神经内科门诊复查，监测血压血脂。",
            json.dumps(["脑梗死", "高血压", "阿司匹林", "氯吡格雷", "他汀", "康复"], ensure_ascii=False),
            "inpatient", 30, True,
        ),
        (
            "复诊：脑梗死恢复期，规律服药中。\n"
            "现病史：出院后规律服药，右侧肢体肌力较前好转，言语较前清晰。\n"
            "查体：BP 142/86mmHg，右侧肢体肌力4+级，言语稍含糊。\n"
            "辅助检查：血脂LDL-C 2.1 mmol/L，达标。\n"
            "诊断：脑梗死恢复期\n"
            "治疗方案：继续双联抗板及他汀治疗，加强康复。\n"
            "随访计划：1个月后复诊，复查颅内血管MRA。",
            json.dumps(["脑梗死恢复期", "LDL-C达标", "MRA复查"], ensure_ascii=False),
            "outpatient", 7, True,
        ),
    ],
    # 陈秀英 — parkinson
    [
        (
            "主诉：双手震颤、行动迟缓3年，加重6个月。\n"
            "现病史：患者3年前出现静止性震颤，逐渐出现行动迟缓、面部表情减少，6个月前症状明显加重，起步困难，小碎步。\n"
            "既往史：无特殊，否认家族遗传史。\n"
            "查体：面具脸，静止性震颤（右>左），四肢铅管样强直，起步困难，小步态。\n"
            "辅助检查：DATscan示纹状体多巴胺转运体摄取减少。\n"
            "诊断：帕金森病（H&Y 2.5级）\n"
            "治疗方案：美多芭125mg tid，普拉克索0.5mg tid，加强康复训练。\n"
            "随访计划：3个月后复诊评估运动波动，酌情调整多巴胺能药物。",
            json.dumps(["帕金森病", "美多芭", "普拉克索", "DATscan", "H&Y 2.5级"], ensure_ascii=False),
            "outpatient", 14, True,
        ),
    ],
    # 赵志强 — dementia
    [
        (
            "主诉：记忆力下降4年，近期迷路2次。\n"
            "现病史：家属诉患者4年前出现近事记忆减退，近半年加重，近期在熟悉路段迷路2次，睡眠差，夜间有时喊叫。\n"
            "既往史：2型糖尿病，服二甲双胍。\n"
            "查体：MMSE 16分，时间定向差，延迟回忆0/3。\n"
            "辅助检查：头颅MRI海马萎缩（内侧颞叶萎缩评分3分）。PET-CT：双侧顶枕叶代谢减低。\n"
            "诊断：阿尔茨海默病（中度）\n"
            "治疗方案：多奈哌齐10mg qn，美金刚10mg bid，家属教育，防走失装置。\n"
            "随访计划：3个月后复诊，监测认知功能及BPSD。",
            json.dumps(["阿尔茨海默病", "MMSE 16", "多奈哌齐", "美金刚", "海马萎缩"], ensure_ascii=False),
            "outpatient", 20, True,
        ),
    ],
    # 刘桂兰 — epilepsy
    [
        (
            "主诉：癫痫控制良好复诊。\n"
            "现病史：癫痫病史5年，近6个月未发作，规律服用左乙拉西坦1000mg bid。\n"
            "既往史：无。\n"
            "查体：神经系统查体无阳性体征。\n"
            "辅助检查：脑电图正常范围。血药浓度：左乙拉西坦35μg/mL（正常范围）。\n"
            "诊断：癫痫（局灶性，继发全面性，控制良好）\n"
            "治疗方案：维持左乙拉西坦原剂量，继续随访。\n"
            "随访计划：6个月后复查脑电图，病情稳定可考虑减药。",
            json.dumps(["癫痫", "左乙拉西坦", "脑电图正常", "药物浓度达标"], ensure_ascii=False),
            "outpatient", 5, True,
        ),
    ],
    # 孙明远 — headache
    [
        (
            "主诉：反复偏头痛，每月发作3-4次。\n"
            "现病史：反复偏头痛5年，单侧搏动性头痛，伴恶心畏光，持续4-72小时，NSAID治疗有效，影响工作。\n"
            "既往史：无。\n"
            "查体：神经系统查体无异常。\n"
            "辅助检查：头颅MRI未见异常。\n"
            "诊断：无先兆偏头痛\n"
            "治疗方案：急性期舒马曲坦50mg；预防用药托吡酯从25mg bid逐步加量至100mg。\n"
            "随访计划：3个月后复诊评估预防用药，记录头痛日记。",
            json.dumps(["偏头痛", "舒马曲坦", "托吡酯", "头痛日记"], ensure_ascii=False),
            "outpatient", 10, True,
        ),
    ],
    # 周海燕 — stroke (TIA)
    [
        (
            "主诉：TIA发作后3个月复诊。\n"
            "现病史：3个月前一过性右手麻木无力，持续约20分钟自行缓解，诊断TIA，予抗板治疗。\n"
            "既往史：高血压、血脂异常。\n"
            "查体：BP 138/82mmHg，神经系统查体无阳性体征。\n"
            "辅助检查：颅脑MRA示左侧大脑中动脉轻度狭窄。\n"
            "诊断：TIA（短暂性脑缺血发作）复诊，二级预防中\n"
            "治疗方案：继续阿司匹林100mg+他汀治疗，控制血压。\n"
            "随访计划：1个月后复诊，复查血压血脂。",
            json.dumps(["TIA", "脑缺血", "阿司匹林", "MCA狭窄", "二级预防"], ensure_ascii=False),
            "outpatient", 3, True,
        ),
    ],
    # 吴国强 — heart failure
    [
        (
            "主诉：气促、双下肢水肿加重1周。\n"
            "现病史：心衰病史3年，1周前气促明显加重，夜间不能平卧，双下肢凹陷性水肿加重。\n"
            "既往史：冠心病、陈旧心梗、2型糖尿病。\n"
            "查体：HR 92次/分，BP 110/70mmHg，双肺底湿啰音，双下肢重度水肿。\n"
            "辅助检查：NT-proBNP 4820pg/mL，心超EF 32%，LVED 65mm。\n"
            "诊断：心力衰竭急性加重（HFrEF，NYHA III级）\n"
            "治疗方案：静脉利尿呋塞米40mg iv，β受体阻滞剂减量，SGLT2i恩格列净10mg加用。\n"
            "随访计划：出院后1周复诊，监测BNP、肾功能、电解质。",
            json.dumps(["心力衰竭", "HFrEF", "NT-proBNP", "呋塞米", "恩格列净", "NYHA III"], ensure_ascii=False),
            "inpatient", 21, True,
        ),
        (
            "心衰出院后1周随访，气促好转。\n"
            "现病史：出院后规律服药，气促明显好转，可平卧，双下肢水肿减轻。\n"
            "查体：HR 78次/分，BP 118/74mmHg，双肺无啰音，双下肢轻度水肿。\n"
            "辅助检查：NT-proBNP 1240pg/mL，电解质正常，肌酐75μmol/L。\n"
            "诊断：心力衰竭（HFrEF）病情趋稳\n"
            "治疗方案：继续GDMT（沙库巴曲缬沙坦、比索洛尔、螺内酯、恩格列净），口服托拉塞米10mg。\n"
            "随访计划：1个月后复诊，3个月后复查心超。",
            json.dumps(["心力衰竭", "GDMT", "沙库巴曲缬沙坦", "BNP下降", "复查心超"], ensure_ascii=False),
            "outpatient", 8, True,
        ),
    ],
    # 郑淑华 — arrhythmia
    [
        (
            "主诉：阵发性心悸，Holter示房颤。\n"
            "现病史：反复阵发性心悸3个月，动态心电图示阵发性心房颤动，最长持续2小时。\n"
            "既往史：高血压，甲状腺功能正常。\n"
            "查体：心律不齐，BP 136/84mmHg，HR 76次/分（窦律）。\n"
            "辅助检查：Holter示阵发性房颤，负荷约8%。心超LA 43mm，EF 62%。CHA2DS2-VASc评分2分。\n"
            "诊断：阵发性心房颤动\n"
            "治疗方案：抗凝利伐沙班15mg qd，节律控制普罗帕酮150mg bid，讨论射频消融。\n"
            "随访计划：3个月后复诊评估复律效果，转介电生理科评估消融指征。",
            json.dumps(["房颤", "利伐沙班", "普罗帕酮", "射频消融", "CHA2DS2-VASc 2"], ensure_ascii=False),
            "outpatient", 12, True,
        ),
    ],
    # 冯建军 — hypertension
    [
        (
            "主诉：高血压定期复诊，控制良好。\n"
            "现病史：高血压病史8年，规律服药，血压控制在130/80mmHg以内，无头痛头晕等不适。\n"
            "既往史：无其他慢性病。\n"
            "查体：BP 128/78mmHg，心肺查体无异常。\n"
            "辅助检查：肾功能、电解质正常，尿微量白蛋白阴性。\n"
            "诊断：高血压（2级，低危）达标控制\n"
            "治疗方案：继续苯磺酸氨氯地平5mg qd，低盐饮食，规律运动。\n"
            "随访计划：3个月后复诊。",
            json.dumps(["高血压", "氨氯地平", "血压达标", "低盐饮食"], ensure_ascii=False),
            "outpatient", 2, True,
        ),
    ],
    # 蒋雪梅 — coronary (PCI)
    [
        (
            "主诉：冠心病PCI术后1年随访，偶有胸闷。\n"
            "现病史：1年前因急性心肌梗死行PCI（LAD支架1枚），术后双联抗板已满1年，偶有劳力性胸闷。\n"
            "既往史：高血压、血脂异常、绝经后。\n"
            "查体：BP 134/80mmHg，HR 66次/分，心肺无异常。\n"
            "辅助检查：心电图示正常窦律，V1-V4 T波低平。LDL-C 1.6mmol/L达标。\n"
            "诊断：冠心病PCI术后（LAD），稳定型心绞痛\n"
            "治疗方案：停氯吡格雷，维持阿司匹林100mg单抗，继续他汀+ACEI，完善负荷心肌核素显像。\n"
            "随访计划：2周后复查负荷试验，酌情冠脉造影评估。",
            json.dumps(["冠心病", "PCI", "LAD支架", "阿司匹林", "心肌核素显像", "稳定型心绞痛"], ensure_ascii=False),
            "outpatient", 16, True,
        ),
    ],
]

def make_tasks(doctor_id, patient_id, patient_name, category, risk, fu_state):
    tasks = []
    if fu_state == "overdue":
        tasks.append(DoctorTask(
            doctor_id=doctor_id, patient_id=patient_id,
            task_type="follow_up",
            title=f"随访 {patient_name}（已逾期）",
            content=f"患者{category}，风险等级{risk}，上次随访已超期，请尽快联系。",
            status="pending",
            due_at=ago(days=7),
            created_at=ago(days=14),
        ))
    elif fu_state == "due_soon":
        tasks.append(DoctorTask(
            doctor_id=doctor_id, patient_id=patient_id,
            task_type="follow_up",
            title=f"随访 {patient_name}",
            content=f"患者{category}，随访时间将至。",
            status="pending",
            due_at=ahead(days=3),
            created_at=ago(days=1),
        ))
    if risk == "high":
        tasks.append(DoctorTask(
            doctor_id=doctor_id, patient_id=patient_id,
            task_type="review",
            title=f"复查结果跟进 — {patient_name}",
            content="高风险患者，请审阅最新检查结果并更新治疗方案。",
            status="pending",
            due_at=ahead(days=5),
            created_at=ago(days=2),
        ))
    return tasks


async def _wipe_tables(session) -> None:
    """Delete all rows from data tables (preserves schema)."""
    for tbl in [
        "audit_log", "doctor_conversation_turns", "doctor_session_states",
        "pending_records", "pending_messages", "medical_record_exports",
        "medical_record_versions", "doctor_tasks", "medical_records",
        "patient_label_assignments", "patient_labels", "patients",
        "invite_codes", "doctor_knowledge_items", "doctor_notify_preferences",
        "doctor_contexts", "doctors",
    ]:
        await session.execute(text(f"DELETE FROM {tbl}"))
    await session.commit()
    print("Cleared existing data")


async def _seed_doctors(session) -> None:
    """Insert demo doctors and invite codes."""
    now = utcnow()
    for d in DOCTORS:
        session.add(Doctor(doctor_id=d["doctor_id"], name=d["name"],
                           specialty=d["specialty"], channel=d["channel"],
                           created_at=now, updated_at=now))
    for ic in INVITE_CODES:
        session.add(InviteCode(code=ic["code"], doctor_id=ic["doctor_id"],
                               doctor_name=ic["doctor_name"], active=True, created_at=now))
    await session.commit()
    print(f"Created {len(DOCTORS)} doctors, {len(INVITE_CODES)} invite codes")


async def _seed_patients(session) -> None:
    """Insert demo patients with records and tasks."""
    for i, (doc_id, name, gender, yob, category) in enumerate(PATIENTS):
        patient = Patient(doctor_id=doc_id, name=name, gender=gender,
                          year_of_birth=yob, primary_category=category,
                          created_at=ago(days=30 + i * 5))
        session.add(patient)
        await session.flush()
        for content, tags, enc_type, d, _signed in RECORDS[i]:
            session.add(MedicalRecordDB(patient_id=patient.id, doctor_id=doc_id,
                                        content=content, tags=tags,
                                        record_type="visit", encounter_type=enc_type,
                                        created_at=ago(days=d), updated_at=ago(days=d)))
        for task in make_tasks(doc_id, patient.id, name, category, "medium", "due_soon"):
            session.add(task)
    await session.commit()
    print(f"Created {len(PATIENTS)} patients with records and tasks")


async def seed() -> None:
    """Main seed coroutine: wipe, then insert doctors, patients, tasks."""
    await create_tables()
    async with AsyncSessionLocal() as session:
        await _wipe_tables(session)
        await _seed_doctors(session)
        await _seed_patients(session)
    print("\nSeed complete!")
    print("  Doctors  :", ", ".join(f"{d['name']} ({d['doctor_id']})" for d in DOCTORS))
    print("  Inv codes:", ", ".join(ic["code"] for ic in INVITE_CODES))


asyncio.run(seed())
