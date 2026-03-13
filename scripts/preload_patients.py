#!/usr/bin/env python3
from __future__ import annotations

"""Preload mock patients for a target doctor (by doctor_id or doctor name).

Examples:
  .venv/bin/python scripts/preload_patients.py --doctor-id wm80GmBgAAIQojCKNChQIjEOg5VFsgGQ --count 30
  .venv/bin/python scripts/preload_patients.py --doctor-id doc_001 --count 20 --with-records
  .venv/bin/python scripts/preload_patients.py --doctor-id doc_001 --count 10 --reset-doctor-data
"""

import argparse
import asyncio
import random
import re
from datetime import datetime
from typing import Optional

from sqlalchemy import delete, select

from db.crud import create_patient, save_record
from db.engine import AsyncSessionLocal
from db.models import Doctor, DoctorTask, MedicalRecordDB, Patient
from db.models.medical_record import MedicalRecord

_SURNAMES = list("赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦许何吕施张孔曹严华金魏陶姜谢邹喻柏范彭郎鲁韦马苗凤花方俞袁柳鲍史唐费薛雷贺倪汤殷罗毕郝邬安常乐于傅皮卞齐康伍余顾孟黄萧尹姚邵汪毛禹狄贝臧计成戴宋茅庞熊纪舒屈项祝董梁杜阮蓝闵席季麻强贾路江童颜郭梅盛林刁钟徐邱骆高夏蔡田樊胡凌霍虞万支柯管卢莫经房裘缪干解应宗丁宣邓杭洪包左石崔吉钮龚程嵇邢裴陆荣翁荀羊甄曲家封芮靳汲邴糜松井段富巫乌焦巴弓牧隗车侯宓蓬全班仰秋仲伊宫宁仇栾甘厉戎祖武符刘景詹束龙叶司韶黎印宿白怀蒲台鄂索赖卓蔺屠蒙池乔胥能苍双闻莘党翟谭贡劳姬申扶堵冉宰郦雍桑桂濮牛寿通边扈燕冀郏浦尚农温别庄晏柴瞿阎连茹习艾鱼容向古易慎戈廖庾终暨居衡步都耿满弘匡国文寇广禄阙东欧殳沃利蔚越师巩聂晁勾敖融冷辛阚简饶曾沙养鞠须丰巢关蒯相查后荆红游竺权盖益桓公")
_GIVEN = ["安", "宁", "卓", "晖", "岚", "越", "晨", "琪", "朗", "舟", "诚", "衡", "熙", "辰", "彬", "睿", "清", "轩", "瑶", "悦", "楠", "烁", "岩", "涛", "霖"]

# Sample clinical content using the current MedicalRecord(content, tags) model
_CONTENT_SAMPLES = [
    ("患者因胸痛2小时伴出汗就诊。心电图示ST段抬高，肌钙蛋白阳性。初步诊断：疑似ACS。建议住院治疗。",
     ["胸痛", "ACS", "心电图异常"]),
    ("反复胸闷3天，活动后加重。既往高血压病史5年。查体血压160/95mmHg。诊断：冠心病。调整降压药物。",
     ["胸闷", "冠心病", "高血压"]),
    ("心悸1天，发作时心率120次/分。心电图示窦性心动过速。诊断：心律失常。建议随访观察。",
     ["心悸", "心律失常", "窦性心动过速"]),
    ("头痛2天，睡眠差。查体无神经系统阳性体征。诊断：偏头痛。予止痛对症处理，7天后复诊。",
     ["头痛", "偏头痛", "睡眠障碍"]),
    ("活动后气短1周，既往无心肺疾病史。肺功能检查正常。诊断：待查。建议心脏超声检查。",
     ["气短", "待查", "心脏超声"]),
]


def _slug(text: str) -> str:
    raw = re.sub(r"\s+", "_", text.strip())
    raw = re.sub(r"[^\w\u4e00-\u9fff-]", "", raw)
    return raw or "doctor"


def _pick_name(seed: int) -> str:
    return _SURNAMES[seed % len(_SURNAMES)] + _GIVEN[seed % len(_GIVEN)]


async def _resolve_doctor_id(doctor_id: Optional[str]) -> str:
    """Resolve --doctor-id to a valid doctor_id, creating the doctor if needed."""
    if not doctor_id or not doctor_id.strip():
        raise ValueError("--doctor-id is required")
    return doctor_id.strip()


async def _reset_doctor_data(doctor_id: str) -> None:
    async with AsyncSessionLocal() as db:
        patient_rows = (await db.execute(select(Patient.id).where(Patient.doctor_id == doctor_id))).scalars().all()
        if patient_rows:
            await db.execute(delete(MedicalRecordDB).where(MedicalRecordDB.doctor_id == doctor_id))
            await db.execute(delete(DoctorTask).where(DoctorTask.doctor_id == doctor_id))
            await db.execute(delete(Patient).where(Patient.doctor_id == doctor_id))
        await db.commit()


async def _preload(doctor_id: str, count: int, with_records: bool) -> None:
    created = 0
    async with AsyncSessionLocal() as db:
        for i in range(count):
            age = random.randint(28, 79)
            gender = "男" if i % 2 == 0 else "女"
            name = _pick_name(i)
            patient, _access_code = await create_patient(db, doctor_id, name, gender, age)
            created += 1
            if with_records:
                idx = i % len(_CONTENT_SAMPLES)
                content, tags = _CONTENT_SAMPLES[idx]
                record = MedicalRecord(
                    content=content,
                    tags=tags,
                    record_type="visit",
                )
                await save_record(db, doctor_id, record, patient.id)
    print("Preload complete: doctor_id={0}, patients={1}, with_records={2}".format(doctor_id, created, with_records))


def main() -> None:
    parser = argparse.ArgumentParser(description="Preload mock patients for a target doctor")
    parser.add_argument("--doctor-id", required=True, help="Target doctor_id (exact match)")
    parser.add_argument("--count", type=int, default=20, help="How many patients to create")
    parser.add_argument("--with-records", action="store_true", help="Also create 1 mock record per patient")
    parser.add_argument("--reset-doctor-data", action="store_true", help="Delete existing patients/records/tasks for this doctor before preload")
    args = parser.parse_args()

    async def _run() -> None:
        did = await _resolve_doctor_id(args.doctor_id)
        if args.reset_doctor_data:
            await _reset_doctor_data(did)
        await _preload(did, max(1, int(args.count)), with_records=bool(args.with_records))

    asyncio.run(_run())


if __name__ == "__main__":
    main()
