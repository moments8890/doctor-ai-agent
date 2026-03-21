#!/usr/bin/env python3
"""Seed mock data for UI screenshot capture.

Creates enough data to populate every page with realistic content.
Safe to run multiple times — checks for existing data before inserting.

Usage:
    PYTHONPATH=src ENVIRONMENT=development python scripts/seed_ui_data.py

Test accounts created:
    Doctor: test_doctor / 1234
    Patient: test_patient / 1234
"""
from __future__ import annotations

import asyncio
import json
import os
import sys

# Ensure src is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
os.environ.setdefault("ENVIRONMENT", "development")


async def main():
    # Import after path setup
    from db.engine import AsyncSessionLocal
    from db.init_db import create_tables
    from db.models import Patient, MedicalRecordDB, DoctorTask
    from db.models.doctor import Doctor, DoctorKnowledgeItem
    from db.models.review_queue import ReviewQueue
    from db.models.diagnosis_result import DiagnosisResult
    from db.models.case_history import CaseHistory
    from db.models.interview_session import InterviewSessionDB, InterviewStatus
    from db.models.base import _utcnow
    from sqlalchemy import select, func
    from datetime import timedelta

    await create_tables()

    DOCTOR_ID = "test_doctor"
    now = _utcnow()

    async with AsyncSessionLocal() as db:
        # ── 1. Doctor ───────────────────────────────────────────
        doctor = (await db.execute(
            select(Doctor).where(Doctor.doctor_id == DOCTOR_ID)
        )).scalar_one_or_none()
        if not doctor:
            doctor = Doctor(
                doctor_id=DOCTOR_ID, name="test_doctor",
                specialty="neurosurgery", channel="app",
            )
            db.add(doctor)
            await db.flush()
            print("  Created doctor: test_doctor")
        else:
            print("  Doctor exists: test_doctor")

        # ── 2. Patients ─────────────────────────────────────────
        patients_data = [
            {"name": "张三", "gender": "male", "year_of_birth": 1968},
            {"name": "李四", "gender": "female", "year_of_birth": 1975},
            {"name": "王五", "gender": "male", "year_of_birth": 1982},
        ]
        patient_ids = []
        for pd in patients_data:
            existing = (await db.execute(
                select(Patient).where(
                    Patient.doctor_id == DOCTOR_ID,
                    Patient.name == pd["name"],
                )
            )).scalar_one_or_none()
            if existing:
                patient_ids.append(existing.id)
                print(f"  Patient exists: {pd['name']} (id={existing.id})")
            else:
                p = Patient(
                    doctor_id=DOCTOR_ID, name=pd["name"],
                    gender=pd["gender"], year_of_birth=pd["year_of_birth"],
                )
                db.add(p)
                await db.flush()
                patient_ids.append(p.id)
                print(f"  Created patient: {pd['name']} (id={p.id})")

        # ── 3. Medical Records ──────────────────────────────────
        records_data = [
            {
                "patient_idx": 0, "record_type": "interview_summary",
                "content": "患者张三，男，56岁，主诉头痛3天，伴恶心呕吐。",
                "structured": {
                    "department": "神经外科",
                    "chief_complaint": "头痛3天，伴恶心呕吐",
                    "present_illness": "3天前无明显诱因出现持续性头痛，以额部为主，伴恶心、非喷射性呕吐。头痛程度逐渐加重，休息后无明显缓解。",
                    "past_history": "高血压10年，服用氨氯地平5mg qd",
                    "allergy_history": "青霉素过敏",
                    "family_history": "母亲有高血压病史",
                    "personal_history": "吸烟20年，每日10支",
                },
                "tags": ["头痛", "恶心", "高血压"],
            },
            {
                "patient_idx": 0, "record_type": "interview_summary",
                "content": "张三复诊，头痛好转，血压控制尚可。",
                "structured": {
                    "chief_complaint": "复诊，头痛好转",
                    "present_illness": "经治疗后头痛明显好转，偶有轻微头晕，恶心消失。血压140/90mmHg。",
                    "past_history": "高血压10年",
                },
                "tags": ["复诊", "头痛好转"],
            },
            {
                "patient_idx": 1, "record_type": "interview_summary",
                "content": "患者李四，女，49岁，右上肢无力2天。",
                "structured": {
                    "department": "神经外科",
                    "chief_complaint": "右上肢无力2天",
                    "present_illness": "2天前晨起发现右手持物不稳，右上肢抬举费力。无头痛、言语障碍、视物异常。",
                    "past_history": "糖尿病5年，服用二甲双胍",
                    "allergy_history": "无",
                    "family_history": "父亲脑梗死病史",
                },
                "tags": ["肢体无力", "糖尿病"],
            },
            {
                "patient_idx": 2, "record_type": "interview_summary",
                "content": "患者王五，男，42岁，腰痛伴左下肢放射痛1周。",
                "structured": {
                    "chief_complaint": "腰痛伴左下肢放射痛1周",
                    "present_illness": "1周前搬重物后出现腰痛，逐渐向左下肢放射，咳嗽时加重。无大小便障碍。",
                    "past_history": "无特殊",
                    "allergy_history": "无",
                },
                "tags": ["腰痛", "放射痛"],
            },
        ]

        record_ids = []
        for rd in records_data:
            pid = patient_ids[rd["patient_idx"]]
            # Check if similar record exists
            count = (await db.execute(
                select(func.count()).select_from(MedicalRecordDB).where(
                    MedicalRecordDB.doctor_id == DOCTOR_ID,
                    MedicalRecordDB.patient_id == pid,
                    MedicalRecordDB.record_type == rd["record_type"],
                )
            )).scalar()
            if count >= 2:
                # Already have enough records
                rid = (await db.execute(
                    select(MedicalRecordDB.id).where(
                        MedicalRecordDB.doctor_id == DOCTOR_ID,
                        MedicalRecordDB.patient_id == pid,
                    ).order_by(MedicalRecordDB.created_at.desc()).limit(1)
                )).scalar()
                record_ids.append(rid)
                print(f"  Records exist for patient {pid}")
                continue

            rec = MedicalRecordDB(
                doctor_id=DOCTOR_ID, patient_id=pid,
                record_type=rd["record_type"],
                content=rd["content"],
                structured=json.dumps(rd["structured"], ensure_ascii=False),
                tags=json.dumps(rd["tags"], ensure_ascii=False) if rd.get("tags") else None,
                created_at=now - timedelta(hours=len(record_ids)),
            )
            db.add(rec)
            await db.flush()
            record_ids.append(rec.id)
            print(f"  Created record id={rec.id} for patient {pid}")

        # ── 4. Review Queue ─────────────────────────────────────
        for i, rid in enumerate(record_ids[:3]):
            existing = (await db.execute(
                select(ReviewQueue).where(ReviewQueue.record_id == rid)
            )).scalar_one_or_none()
            if existing:
                print(f"  Review exists for record {rid}")
                continue
            status = "pending_review" if i == 0 else "reviewed"
            rq = ReviewQueue(
                record_id=rid, doctor_id=DOCTOR_ID,
                patient_id=patient_ids[i % len(patient_ids)],
                status=status, created_at=now - timedelta(hours=i),
            )
            db.add(rq)
            await db.flush()
            print(f"  Created review id={rq.id} status={status}")

        # ── 5. Diagnosis Results ────────────────────────────────
        for i, rid in enumerate(record_ids[:2]):
            existing = (await db.execute(
                select(DiagnosisResult).where(DiagnosisResult.record_id == rid)
            )).scalar_one_or_none()
            if existing:
                print(f"  Diagnosis exists for record {rid}")
                continue

            ai_output = {
                "differentials": [
                    {"condition": "脑膜瘤", "confidence": "高", "reasoning": "持续性头痛+恶心+高血压→颅内占位可能"},
                    {"condition": "高血压性头痛", "confidence": "中", "reasoning": "长期高血压病史，血压控制不佳"},
                    {"condition": "蛛网膜下腔出血", "confidence": "低", "reasoning": "非雷击样头痛，可能性较低"},
                ],
                "workup": [
                    {"test": "头颅MRI增强", "rationale": "排除颅内占位", "urgency": "紧急"},
                    {"test": "血常规+CRP", "rationale": "排除感染", "urgency": "常规"},
                    {"test": "血压24小时动态监测", "rationale": "评估血压控制", "urgency": "常规"},
                ],
                "treatment": [
                    {"drug_class": "降压药调整", "intervention": "药物", "description": "氨氯地平加量或联合用药"},
                    {"drug_class": "止痛对症", "intervention": "药物", "description": "对乙酰氨基酚或布洛芬"},
                ],
            }
            dx = DiagnosisResult(
                record_id=rid, doctor_id=DOCTOR_ID,
                ai_output=json.dumps(ai_output, ensure_ascii=False),
                red_flags=json.dumps(["持续性头痛伴恶心呕吐需排除颅内占位"], ensure_ascii=False),
                case_references=json.dumps([
                    {"chief_complaint": "头痛+恶心", "final_diagnosis": "脑膜瘤", "similarity": 0.87},
                ], ensure_ascii=False),
                status="completed",
                completed_at=now,
            )
            db.add(dx)
            await db.flush()
            print(f"  Created diagnosis id={dx.id} for record {rid}")

        # ── 6. Tasks ────────────────────────────────────────────
        tasks_data = [
            {"title": "张三 MRI复查", "task_type": "follow_up", "status": "pending",
             "content": "头痛好转后1月复查MRI", "patient_idx": 0},
            {"title": "李四 血糖监测", "task_type": "lab_review", "status": "pending",
             "content": "空腹血糖+糖化血红蛋白", "patient_idx": 1},
            {"title": "王五 随访电话", "task_type": "follow_up", "status": "completed",
             "content": "术后2周随访", "patient_idx": 2},
        ]
        for td in tasks_data:
            existing = (await db.execute(
                select(func.count()).select_from(DoctorTask).where(
                    DoctorTask.doctor_id == DOCTOR_ID,
                    DoctorTask.title == td["title"],
                )
            )).scalar()
            if existing:
                print(f"  Task exists: {td['title']}")
                continue
            task = DoctorTask(
                doctor_id=DOCTOR_ID,
                patient_id=patient_ids[td["patient_idx"]],
                title=td["title"],
                task_type=td["task_type"],
                content=td["content"],
                status=td["status"],
                created_at=now - timedelta(hours=2),
            )
            db.add(task)
            print(f"  Created task: {td['title']}")

        # ── 7. Knowledge Items ──────────────────────────────────
        knowledge_data = [
            {"text": "头痛问诊要点：先问发作方式（突发/渐进），突发性头痛需追问雷击样特征", "category": "interview_guide", "source": "doctor"},
            {"text": "头痛+恶心+视乳头水肿三联征→颅内高压，需紧急CT排除占位", "category": "diagnosis_rule", "source": "doctor"},
            {"text": "雷击样头痛→立即排除SAH，先CT后腰穿", "category": "red_flag", "source": "doctor"},
            {"text": "脑膜瘤术后：地塞米松10mg→逐渐减量，抗癫痫预防1周", "category": "treatment_protocol", "source": "doctor"},
            {"text": "老年患者优先保守治疗，除非有明确手术指征", "category": "custom", "source": "doctor"},
            {"text": "肢体无力急性起病→优先考虑卒中，立即CT排除出血", "category": "diagnosis_rule", "source": "agent_auto"},
        ]
        for kd in knowledge_data:
            existing = (await db.execute(
                select(func.count()).select_from(DoctorKnowledgeItem).where(
                    DoctorKnowledgeItem.doctor_id == DOCTOR_ID,
                    DoctorKnowledgeItem.content.contains(kd["text"][:30]),
                )
            )).scalar()
            if existing:
                print(f"  Knowledge exists: {kd['text'][:30]}...")
                continue
            payload = json.dumps({"v": 1, "text": kd["text"], "source": kd["source"], "confidence": 1.0 if kd["source"] == "doctor" else 0.6}, ensure_ascii=False)
            item = DoctorKnowledgeItem(
                doctor_id=DOCTOR_ID, content=payload,
                category=kd.get("category", "custom"),
            )
            db.add(item)
            print(f"  Created knowledge: {kd['text'][:40]}...")

        # ── 8. Case History ─────────────────────────────────────
        cases_data = [
            {"chief_complaint": "头痛伴恶心2周", "final_diagnosis": "右额叶脑膜瘤（WHO I级）",
             "treatment": "开颅肿瘤切除术", "outcome": "好转", "confidence_status": "confirmed"},
            {"chief_complaint": "突发剧烈头痛", "final_diagnosis": "蛛网膜下腔出血",
             "treatment": "动脉瘤夹闭术", "outcome": "好转", "confidence_status": "confirmed"},
        ]
        for cd in cases_data:
            existing = (await db.execute(
                select(func.count()).select_from(CaseHistory).where(
                    CaseHistory.doctor_id == DOCTOR_ID,
                    CaseHistory.chief_complaint == cd["chief_complaint"],
                )
            )).scalar()
            if existing:
                print(f"  Case exists: {cd['chief_complaint']}")
                continue
            case = CaseHistory(
                doctor_id=DOCTOR_ID,
                chief_complaint=cd["chief_complaint"],
                final_diagnosis=cd["final_diagnosis"],
                treatment=cd["treatment"],
                outcome=cd["outcome"],
                confidence_status=cd["confidence_status"],
                reference_count=5,
                source="review",
            )
            db.add(case)
            print(f"  Created case: {cd['chief_complaint']}")

        # ── 9. Interview Session (for conversation in review) ───
        existing_session = (await db.execute(
            select(func.count()).select_from(InterviewSessionDB).where(
                InterviewSessionDB.doctor_id == DOCTOR_ID,
            )
        )).scalar()
        if not existing_session and record_ids:
            conversation = [
                {"role": "assistant", "content": "您好！请描述您的症状。"},
                {"role": "user", "content": "我头痛3天了"},
                {"role": "assistant", "content": "头痛是什么时候开始的？是突然发生的还是逐渐加重的？"},
                {"role": "user", "content": "3天前开始的，逐渐加重"},
                {"role": "assistant", "content": "有没有伴随其他不适？比如恶心、呕吐、视物模糊？"},
                {"role": "user", "content": "有恶心，吐了两次"},
                {"role": "assistant", "content": "了解。您以前有过类似的头痛吗？有没有高血压、糖尿病等慢性病？"},
                {"role": "user", "content": "有高血压10年了，一直在吃药"},
            ]
            import uuid
            sess = InterviewSessionDB(
                id=str(uuid.uuid4()),
                doctor_id=DOCTOR_ID,
                patient_id=patient_ids[0],
                status=InterviewStatus.confirmed,
                mode="patient",
                collected=json.dumps({
                    "chief_complaint": "头痛3天",
                    "present_illness": "3天前开始持续性头痛，逐渐加重，伴恶心呕吐2次",
                    "past_history": "高血压10年，服药中",
                }, ensure_ascii=False),
                conversation=json.dumps(conversation, ensure_ascii=False),
                turn_count=4,
                created_at=now - timedelta(hours=1),
                updated_at=now,
            )
            db.add(sess)
            print("  Created interview session with conversation")

        await db.commit()
        print("\n✅ Seed data complete. All UI pages should now have content.")


if __name__ == "__main__":
    asyncio.run(main())
