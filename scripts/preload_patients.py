#!/usr/bin/env python3
from __future__ import annotations

"""Preload mock patients for a target doctor (by doctor_id or doctor name).

Examples:
  .venv/bin/python scripts/preload_patients.py --doctor-id wm80GmBgAAIQojCKNChQIjEOg5VFsgGQ --count 30
  .venv/bin/python scripts/preload_patients.py --doctor-name 章三 --count 20 --with-records
  .venv/bin/python scripts/preload_patients.py --doctor-name 章三 --count 10 --reset-doctor-data
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
from models.medical_record import MedicalRecord

_SURNAMES = list("赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦许何吕施张孔曹严华金魏陶姜谢邹喻柏范彭郎鲁韦马苗凤花方俞袁柳鲍史唐费薛雷贺倪汤殷罗毕郝邬安常乐于傅皮卞齐康伍余顾孟黄萧尹姚邵汪毛禹狄贝臧计成戴宋茅庞熊纪舒屈项祝董梁杜阮蓝闵席季麻强贾路江童颜郭梅盛林刁钟徐邱骆高夏蔡田樊胡凌霍虞万支柯管卢莫经房裘缪干解应宗丁宣邓杭洪包左石崔吉钮龚程嵇邢裴陆荣翁荀羊甄曲家封芮靳汲邴糜松井段富巫乌焦巴弓牧隗车侯宓蓬全班仰秋仲伊宫宁仇栾甘厉戎祖武符刘景詹束龙叶司韶黎印宿白怀蒲台鄂索赖卓蔺屠蒙池乔胥能苍双闻莘党翟谭贡劳姬申扶堵冉宰郦雍桑桂濮牛寿通边扈燕冀郏浦尚农温别庄晏柴瞿阎连茹习艾鱼容向古易慎戈廖庾终暨居衡步都耿满弘匡国文寇广禄阙东欧殳沃利蔚越师巩聂晁勾敖融冷辛阚简饶曾沙养鞠须丰巢关蒯相查后荆红游竺权盖益桓公")
_GIVEN = ["安", "宁", "卓", "晖", "岚", "越", "晨", "琪", "朗", "舟", "诚", "衡", "熙", "辰", "彬", "睿", "清", "轩", "瑶", "悦", "楠", "烁", "岩", "涛", "霖"]
_CHIEF = [
    "胸痛2小时伴出汗",
    "胸闷反复3天",
    "心悸1天",
    "头痛2天睡眠差",
    "活动后气短1周",
]
_DIAG = ["疑似ACS", "冠心病", "高血压", "心律失常", "偏头痛"]


def _slug(text: str) -> str:
    raw = re.sub(r"\s+", "_", text.strip())
    raw = re.sub(r"[^\w\u4e00-\u9fff-]", "", raw)
    return raw or "doctor"


def _pick_name(seed: int) -> str:
    return _SURNAMES[seed % len(_SURNAMES)] + _GIVEN[seed % len(_GIVEN)]


async def _resolve_or_create_doctor_id(
    doctor_id: Optional[str],
    doctor_name: Optional[str],
) -> str:
    if doctor_id and doctor_id.strip():
        return doctor_id.strip()

    if not doctor_name or not doctor_name.strip():
        raise ValueError("Either --doctor-id or --doctor-name is required")

    target_name = doctor_name.strip()
    async with AsyncSessionLocal() as db:
        rows = (
            await db.execute(
                select(Doctor).where(Doctor.name == target_name).order_by(Doctor.updated_at.desc())
            )
        ).scalars().all()
        if rows:
            return rows[0].doctor_id

        generated = "doc_{0}_{1}".format(_slug(target_name), datetime.now().strftime("%Y%m%d%H%M%S"))
        db.add(Doctor(doctor_id=generated, name=target_name, channel="app"))
        await db.commit()
        return generated


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
            patient = await create_patient(db, doctor_id, name, gender, age)
            created += 1
            if with_records:
                idx = i % len(_CHIEF)
                record = MedicalRecord(
                    chief_complaint=_CHIEF[idx],
                    history_of_present_illness="症状持续中，建议复查。",
                    diagnosis=_DIAG[idx],
                    treatment_plan="按医嘱门诊随访。",
                    follow_up_plan="7天后复诊",
                )
                await save_record(db, doctor_id, record, patient.id)
    print("Preload complete: doctor_id={0}, patients={1}, with_records={2}".format(doctor_id, created, with_records))


def main() -> None:
    parser = argparse.ArgumentParser(description="Preload mock patients for a target doctor")
    parser.add_argument("--doctor-id", default="", help="Target doctor_id (recommended)")
    parser.add_argument("--doctor-name", default="", help="Target doctor name (resolved to latest matching doctor)")
    parser.add_argument("--count", type=int, default=20, help="How many patients to create")
    parser.add_argument("--with-records", action="store_true", help="Also create 1 mock record per patient")
    parser.add_argument("--reset-doctor-data", action="store_true", help="Delete existing patients/records/tasks for this doctor before preload")
    args = parser.parse_args()

    async def _run() -> None:
        did = await _resolve_or_create_doctor_id(args.doctor_id, args.doctor_name)
        if args.reset_doctor_data:
            await _reset_doctor_data(did)
        await _preload(did, max(1, int(args.count)), with_records=bool(args.with_records))

    asyncio.run(_run())


if __name__ == "__main__":
    main()

