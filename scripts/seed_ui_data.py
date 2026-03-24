#!/usr/bin/env python3
"""Seed mock data for UI screenshot capture.

Creates realistic neurosurgery data to populate every page.
Use --reset to clear existing data first.

Usage:
    PYTHONPATH=src ENVIRONMENT=development python scripts/seed_ui_data.py --doctor-id=inv_hh_Y7p5cGJ0J --reset

Test accounts:
    Doctor: 张三 / 1234
    Patient: 周海涛 / 1968
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from datetime import timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
os.environ.setdefault("ENVIRONMENT", "development")

# Default doctor_id — override with --doctor-id=xxx
DOCTOR_ID = "test_doctor"
for arg in sys.argv:
    if arg.startswith("--doctor-id="):
        DOCTOR_ID = arg.split("=", 1)[1]
RESET = "--reset" in sys.argv


async def main():
    from db.engine import AsyncSessionLocal
    from db.init_db import create_tables
    from db.models import Patient, MedicalRecordDB, DoctorTask
    from db.models.doctor import Doctor, DoctorKnowledgeItem
    from db.models.interview_session import InterviewSessionDB, InterviewStatus
    from db.models.base import _utcnow
    from sqlalchemy import select, delete, func

    await create_tables()
    now = _utcnow()

    async with AsyncSessionLocal() as db:

        # ── Reset ───────────────────────────────────────────────
        if RESET:
            print("Resetting test_doctor data...")
            for model in [InterviewSessionDB, DoctorTask,
                          MedicalRecordDB, DoctorKnowledgeItem]:
                await db.execute(delete(model).where(model.doctor_id == DOCTOR_ID))
            await db.execute(delete(Patient).where(Patient.doctor_id == DOCTOR_ID))
            await db.commit()
            print("  Cleared all test_doctor data.\n")

        # ── Doctor ──────────────────────────────────────────────
        doctor = (await db.execute(select(Doctor).where(Doctor.doctor_id == DOCTOR_ID))).scalar_one_or_none()
        if not doctor:
            doctor = Doctor(doctor_id=DOCTOR_ID, name="张三", specialty="neurosurgery", channel="app")
            db.add(doctor)
            await db.flush()
            print(f"  Created doctor: 张三 ({DOCTOR_ID})")
        else:
            print(f"  Doctor exists: {doctor.name}")

        # ── Patients (5) ────────────────────────────────────────
        patients_data = [
            {"name": "周海涛", "gender": "male", "year_of_birth": 1971},
            {"name": "吴晓燕", "gender": "female", "year_of_birth": 1978},
            {"name": "孙国庆", "gender": "male", "year_of_birth": 1963},
            {"name": "何丽萍", "gender": "female", "year_of_birth": 1985},
            {"name": "马文斌", "gender": "male", "year_of_birth": 1958},
        ]
        patients = {}
        for pd in patients_data:
            existing = (await db.execute(
                select(Patient).where(Patient.doctor_id == DOCTOR_ID, Patient.name == pd["name"])
            )).scalar_one_or_none()
            if existing:
                patients[pd["name"]] = existing.id
                print(f"  Patient exists: {pd['name']} (id={existing.id})")
            else:
                p = Patient(doctor_id=DOCTOR_ID, **pd)
                db.add(p)
                await db.flush()
                patients[pd["name"]] = p.id
                print(f"  Created patient: {pd['name']} (id={p.id})")

        # ── Medical Records ─────────────────────────────────────
        records_data = [
            {
                "patient": "周海涛", "record_type": "interview_summary",
                "content": "患者周海涛，男，55岁，主诉头痛2周，伴恶心呕吐，加重3天。",
                "structured": {
                    "department": "神经外科", "chief_complaint": "头痛2周，加重3天",
                    "present_illness": "2周前无明显诱因出现持续性头痛，以额部为主，伴恶心、非喷射性呕吐。3天前头痛明显加重，出现视物模糊。",
                    "past_history": "高血压10年，服用氨氯地平5mg qd。糖尿病3年，二甲双胍控制。",
                    "allergy_history": "青霉素过敏", "family_history": "母亲高血压",
                    "personal_history": "吸烟20年，每日10支。饮酒偶尔。",
                },
                "tags": ["头痛", "恶心", "视物模糊", "高血压"],
                "hours_ago": 2,
            },
            {
                "patient": "吴晓燕", "record_type": "interview_summary",
                "content": "患者吴晓燕，女，48岁，右上肢无力2天，伴言语不清。",
                "structured": {
                    "department": "神经外科", "chief_complaint": "右上肢无力2天，伴言语不清",
                    "present_illness": "2天前晨起发现右手持物不稳，右上肢抬举费力，同时出现言语含糊。无头痛、无意识障碍。",
                    "past_history": "糖尿病5年，服用二甲双胍。房颤2年，华法林抗凝。",
                    "allergy_history": "无", "family_history": "父亲脑梗死病史",
                },
                "tags": ["肢体无力", "言语不清", "糖尿病", "房颤"],
                "hours_ago": 5,
            },
            {
                "patient": "孙国庆", "record_type": "interview_summary",
                "content": "患者孙国庆，男，63岁，腰痛伴左下肢放射痛1周，加重2天。",
                "structured": {
                    "chief_complaint": "腰痛伴左下肢放射痛1周",
                    "present_illness": "1周前搬重物后出现腰痛，逐渐向左下肢后外侧放射，咳嗽时加重。2天前出现左足背感觉减退。无大小便障碍。",
                    "past_history": "腰椎间盘突出症10年", "allergy_history": "无",
                },
                "tags": ["腰痛", "放射痛", "感觉减退"],
                "hours_ago": 24,
            },
            {
                "patient": "何丽萍", "record_type": "interview_summary",
                "content": "患者何丽萍，女，41岁，反复癫痫发作3月，近1周频率增加。",
                "structured": {
                    "department": "神经外科", "chief_complaint": "反复癫痫发作3月，加重1周",
                    "present_illness": "3月前首次出现全面性强直-阵挛发作，每月约2次。近1周发作频率增至隔日1次，伴发作后头痛。外院MRI提示左颞叶占位。",
                    "past_history": "既往体健", "allergy_history": "磺胺类药物过敏",
                    "family_history": "无特殊",
                },
                "tags": ["癫痫", "颞叶占位", "发作频率增加"],
                "hours_ago": 48,
            },
            {
                "patient": "马文斌", "record_type": "interview_summary",
                "content": "患者马文斌，男，68岁，动脉瘤夹闭术后2周复查。",
                "structured": {
                    "chief_complaint": "动脉瘤夹闭术后2周复查",
                    "present_illness": "2周前因右侧大脑中动脉动脉瘤行开颅夹闭术，术后恢复良好。目前无头痛、无肢体活动障碍。切口愈合良好。",
                    "past_history": "高血压15年，冠心病5年", "allergy_history": "无",
                },
                "tags": ["术后复查", "动脉瘤", "恢复良好"],
                "hours_ago": 72,
            },
            {
                "patient": "周海涛", "record_type": "interview_summary",
                "content": "周海涛复诊，头痛好转，MRI结果回报。",
                "structured": {
                    "chief_complaint": "复诊，头痛好转",
                    "present_illness": "经治疗后头痛明显好转，恶心消失。MRI示右额叶占位性病变，考虑脑膜瘤可能。",
                },
                "tags": ["复诊", "头痛好转", "MRI", "脑膜瘤"],
                "hours_ago": 1,
            },
        ]

        record_ids = {}
        for rd in records_data:
            pid = patients[rd["patient"]]
            rec = MedicalRecordDB(
                doctor_id=DOCTOR_ID, patient_id=pid, record_type=rd["record_type"],
                content=rd["content"],
                structured=json.dumps(rd["structured"], ensure_ascii=False),
                tags=json.dumps(rd.get("tags", []), ensure_ascii=False),
                created_at=now - timedelta(hours=rd["hours_ago"]),
            )
            db.add(rec)
            await db.flush()
            key = f"{rd['patient']}_{rd['hours_ago']}"
            record_ids[key] = rec.id
            print(f"  Record id={rec.id}: {rd['patient']} — {rd['structured'].get('chief_complaint', '')[:30]}")

        # ── Tasks (5) ──────────────────────────────────────────
        tasks = [
            {"title": "周海涛 MRI增强复查", "type": "review", "status": "pending", "patient": "周海涛",
             "content": "头痛好转后1月复查MRI增强，评估脑膜瘤变化", "due_hours": 48},
            {"title": "吴晓燕 INR监测", "type": "review", "status": "pending", "patient": "吴晓燕",
             "content": "华法林调整后3天复查INR，目标2.0-3.0", "due_hours": 24},
            {"title": "孙国庆 腰椎MRI", "type": "review", "status": "pending", "patient": "孙国庆",
             "content": "腰椎MRI评估椎间盘突出程度，决定是否手术", "due_hours": 72},
            {"title": "马文斌 术后随访电话", "type": "general", "status": "completed", "patient": "马文斌",
             "content": "动脉瘤夹闭术后2周电话随访，了解恢复情况"},
            {"title": "何丽萍 抗癫痫药物调整", "type": "review", "status": "pending", "patient": "何丽萍",
             "content": "左乙拉西坦加量至1000mg bid，观察发作控制情况", "due_hours": 168},
        ]
        for td in tasks:
            pid = patients.get(td["patient"])
            task = DoctorTask(
                doctor_id=DOCTOR_ID, patient_id=pid,
                title=td["title"], task_type=td["type"],
                content=td["content"], status=td["status"],
                due_at=(now + timedelta(hours=td.get("due_hours", 0))) if td.get("due_hours") else None,
                created_at=now - timedelta(hours=3),
            )
            db.add(task)
            print(f"  Task: {td['title']} [{td['status']}]")

        # ── Patient-facing tasks (target='patient') ───────────
        patient_tasks = [
            {"title": "MRI增强检查", "type": "review", "status": "pending", "patient": "周海涛",
             "content": "请于3日内到放射科完成头颅MRI增强扫描，空腹，携带既往片子", "due_hours": 72},
            {"title": "复查血常规+凝血", "type": "review", "status": "pending", "patient": "周海涛",
             "content": "术前检查，空腹抽血，结果当日出", "due_hours": 24},
            {"title": "按时服药提醒", "type": "general", "status": "completed", "patient": "周海涛",
             "content": "氨氯地平5mg 每日一次，二甲双胍500mg 每日两次"},
        ]
        for ptd in patient_tasks:
            pid = patients.get(ptd["patient"])
            pt = DoctorTask(
                doctor_id=DOCTOR_ID, patient_id=pid, target="patient",
                title=ptd["title"], task_type=ptd["type"],
                content=ptd["content"], status=ptd["status"],
                due_at=(now + timedelta(hours=ptd.get("due_hours", 0))) if ptd.get("due_hours") else None,
                created_at=now - timedelta(hours=1),
            )
            db.add(pt)
            print(f"  Patient task: {ptd['title']} [{ptd['status']}]")

        # ── Knowledge Items (6 across categories) ───────────────
        knowledge = [
            {"text": "头痛问诊要点：先问发作方式（突发/渐进），突发→追问雷击样特征。持续性头痛+恶心+视乳头水肿→颅高压三联征。",
             "category": "interview_guide", "source": "doctor"},
            {"text": "急性肢体无力问诊：首先区分急性（<24h）还是慢性。急性起病→卒中筛查：发病时间、言语障碍、面部不对称、房颤/高血压史。",
             "category": "interview_guide", "source": "doctor"},
            {"text": "头痛+恶心+视乳头水肿三联征→颅内高压，需紧急CT/MRI排除占位。老年患者同时排除慢性硬膜下血肿。",
             "category": "diagnosis_rule", "source": "doctor"},
            {"text": "雷击样头痛（数秒内达峰值）→无论其他症状如何，必须立即排除SAH。先CT后腰穿，时间窗至关重要。",
             "category": "red_flag", "source": "doctor"},
            {"text": "进行性双下肢无力+鞍区感觉减退+大小便功能障碍→马尾综合征，24小时内手术减压。",
             "category": "red_flag", "source": "agent_auto"},
            {"text": "脑膜瘤术后标准方案：地塞米松10mg术中→术后4mg q6h×3天→逐渐减量。抗癫痫预防用药至少1周。",
             "category": "treatment_protocol", "source": "doctor"},
        ]
        for kd in knowledge:
            payload = json.dumps({"v": 1, "text": kd["text"], "source": kd["source"],
                                  "confidence": 1.0 if kd["source"] == "doctor" else 0.6}, ensure_ascii=False)
            item = DoctorKnowledgeItem(
                doctor_id=DOCTOR_ID, content=payload,
                category=kd["category"], reference_count=3 if kd["source"] == "doctor" else 1,
            )
            db.add(item)
            print(f"  Knowledge [{kd['category']}]: {kd['text'][:40]}...")

        # ── Interview Session (with conversation) ───────────────
        conversation = [
            {"role": "assistant", "content": "您好！请描述您的症状，我来帮您整理病情。"},
            {"role": "user", "content": "我头痛两个星期了，最近几天越来越严重"},
            {"role": "assistant", "content": "头痛两周加重，了解了。头痛是持续性的还是间歇性的？主要痛在哪个部位？"},
            {"role": "user", "content": "一直都痛，主要是前额这边，有时候整个头都痛"},
            {"role": "assistant", "content": "持续性前额头痛。有没有伴随其他不适？比如恶心、呕吐、看东西模糊？"},
            {"role": "user", "content": "有恶心，吐了几次，最近看东西有点模糊"},
            {"role": "assistant", "content": "头痛伴恶心呕吐和视物模糊，这些症状需要重视。您以前有过类似头痛吗？有没有高血压、糖尿病等慢性病？"},
            {"role": "user", "content": "以前没这么痛过。有高血压十几年了，一直吃降压药。糖尿病三年"},
            {"role": "assistant", "content": "了解，高血压10年+糖尿病3年。您对什么药物过敏吗？"},
            {"role": "user", "content": "青霉素过敏"},
            {"role": "assistant", "content": "好的。家里人有没有类似的疾病？"},
            {"role": "user", "content": "我妈也有高血压"},
            {"role": "assistant", "content": "您的情况我都记下来了。主要是持续性头痛两周加重，伴恶心呕吐和视物模糊，有高血压和糖尿病病史。请确认后提交给医生。"},
        ]
        sess = InterviewSessionDB(
            id=str(uuid.uuid4()), doctor_id=DOCTOR_ID,
            patient_id=patients["周海涛"], status=InterviewStatus.confirmed, mode="patient",
            collected=json.dumps({
                "chief_complaint": "头痛2周，加重3天",
                "present_illness": "持续性前额头痛，逐渐加重，伴恶心呕吐数次，近日视物模糊",
                "past_history": "高血压10年，服用氨氯地平；糖尿病3年",
                "allergy_history": "青霉素过敏",
                "family_history": "母亲高血压",
            }, ensure_ascii=False),
            conversation=json.dumps(conversation, ensure_ascii=False),
            turn_count=7, created_at=now - timedelta(hours=2), updated_at=now,
        )
        db.add(sess)
        print("  Interview session: 周海涛 (13 messages)")

        await db.commit()
        print(f"\n✅ Seed complete: 5 patients, 6 records, 5+3 tasks, 6 knowledge, 1 interview")


if __name__ == "__main__":
    asyncio.run(main())
