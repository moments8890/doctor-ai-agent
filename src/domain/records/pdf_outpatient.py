"""
门诊病历 PDF 生成：generate_outpatient_report_pdf() 及其私有辅助函数。

按卫生部 2010 门诊病历格式（卫医政发〔2010〕11号 / 国卫办医政发〔2024〕16号）。
依赖 pdf_helpers.py 中的共享辅助工具（字体解析、字体设置等）。
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

from utils.log import log

from domain.records.pdf_helpers import (
    _make_set_font,
    _resolve_font_path,
)
from domain.records.schema import OUTPATIENT_FIELD_META


# ---------------------------------------------------------------------------
# Outpatient PDF — private helpers
# ---------------------------------------------------------------------------

def _draw_outpatient_header(
    pdf, _sf, clinic: str,
    patient_name: Optional[str], patient_info,
    department: str, doctor_name: Optional[str],
) -> None:
    """绘制门诊病历标题块和患者/医生信息行。

    ``patient_info`` may be a plain string (legacy) **or** a dict with keys
    ``"text"`` (demographics string) and optional ``"source_annotation"``
    (e.g. date range / record count when merging multiple records).
    """
    # Normalise patient_info to text + optional annotation
    if isinstance(patient_info, dict):
        info_text: Optional[str] = patient_info.get("text")
        source_annotation: Optional[str] = patient_info.get("source_annotation")
    else:
        info_text = patient_info
        source_annotation = None

    _sf(16, bold=True)
    pdf.cell(0, 10, clinic, align="C", new_x="LMARGIN", new_y="NEXT")
    _sf(13, bold=True)
    pdf.cell(0, 8, "门  诊  病  历", align="C", new_x="LMARGIN", new_y="NEXT")
    _sf(9)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 5, "卫医政发〔2010〕11号  ·  国卫办医政发〔2024〕16号", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(2)
    pdf.set_draw_color(60, 80, 140)
    pdf.set_line_width(0.5)
    pdf.line(18, pdf.get_y(), pdf.w - 18, pdf.get_y())
    pdf.set_line_width(0.2)
    pdf.set_draw_color(180, 180, 180)
    pdf.ln(4)

    _sf(10)
    row_parts: list[str] = []
    if patient_name:
        row_parts.append(f"姓名：{patient_name}")
    if info_text:
        row_parts.append(info_text)
    if department:
        row_parts.append(f"科别：{department}")
    if doctor_name:
        row_parts.append(f"接诊医师：{doctor_name}")
    row_parts.append(f"就诊日期：{datetime.now().strftime('%Y-%m-%d')}")
    pdf.cell(0, 7, "    ".join(row_parts), new_x="LMARGIN", new_y="NEXT")

    # If records metadata is available, show source annotation
    if source_annotation:
        _sf(8)
        pdf.set_text_color(120, 120, 120)
        pdf.cell(0, 5, source_annotation, new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)

    pdf.ln(3)
    pdf.line(18, pdf.get_y(), pdf.w - 18, pdf.get_y())
    pdf.ln(4)


def _draw_outpatient_fields(pdf, _sf, fields: dict, OUTPATIENT_FIELDS, _HEADER_ONLY_FIELDS) -> None:
    """绘制门诊病历各字段节（标签列 + 内容列 + 分隔线）。"""
    label_w = 32
    for key, label in OUTPATIENT_FIELDS:
        if key in _HEADER_ONLY_FIELDS:
            continue
        value = (fields.get(key) or "").strip()
        if pdf.get_y() > pdf.h - 40:
            pdf.add_page()
        pdf.set_fill_color(235, 240, 250)
        _sf(10, bold=True)
        pdf.cell(label_w, 7, f"【{label}】", fill=True, new_x="RIGHT", new_y="TOP")
        _sf(10)
        if value:
            x_start = pdf.get_x()
            avail_w = pdf.w - pdf.r_margin - x_start
            pdf.multi_cell(avail_w, 7, value, new_x="LMARGIN", new_y="NEXT")
        else:
            pdf.cell(0, 7, "", new_x="LMARGIN", new_y="NEXT")
        pdf.set_draw_color(210, 210, 210)
        pdf.line(18, pdf.get_y(), pdf.w - 18, pdf.get_y())
        pdf.ln(2)


def _create_outpatient_pdf_doc():
    """创建门诊病历 PDF 文档对象并注册字体，返回 (pdf, _sf)。"""
    from fpdf import FPDF
    font_path = _resolve_font_path()
    pdf = FPDF()
    pdf.set_margins(left=18, top=18, right=18)
    pdf.set_auto_page_break(auto=True, margin=18)
    has_cjk = False
    if font_path:
        try:
            pdf.add_font("CJK", fname=font_path)
            has_cjk = True
        except Exception as exc:
            log(f"[PDF] font load failed ({font_path}): {exc}")
    return pdf, _make_set_font(pdf, has_cjk)


def _draw_outpatient_footer(pdf, _sf) -> None:
    """绘制门诊病历签名栏和页脚。"""
    pdf.ln(6)
    _sf(10)
    sig_line = f"接诊医师签名：{'_' * 12}    日期：{'_' * 10}"
    pdf.cell(0, 7, sig_line, new_x="LMARGIN", new_y="NEXT")
    pdf.set_y(-15)
    _sf(8)
    pdf.set_text_color(150, 150, 150)
    pdf.cell(
        0, 5,
        "本文件由 AI 助手辅助生成，仅供参考，以原始病历为准  |  "
        f"共 {pdf.page} 页",
        align="C",
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_outpatient_report_pdf(
    fields: dict,
    patient_name: Optional[str] = None,
    patient_info=None,
    clinic_name: Optional[str] = None,
    doctor_name: Optional[str] = None,
) -> bytes:
    """按卫生部 2010 门诊病历格式生成 PDF（14 fields），返回原始字节。

    ``patient_info`` accepts a plain string (legacy) **or** a dict with keys
    ``"text"`` and optional ``"source_annotation"`` for merged-record context.
    """
    # Use shared 14-field schema as the single source of truth
    _HEADER_ONLY_FIELDS = {"department"}
    clinic = clinic_name or os.environ.get("CLINIC_NAME", "医疗机构")
    department = (fields.get("department") or "").strip()
    pdf, _sf = _create_outpatient_pdf_doc()
    pdf.add_page()
    _draw_outpatient_header(
        pdf, _sf, clinic,
        patient_name, patient_info, department, doctor_name,
    )
    _draw_outpatient_fields(pdf, _sf, fields, OUTPATIENT_FIELD_META, _HEADER_ONLY_FIELDS)
    _draw_outpatient_footer(pdf, _sf)
    return bytes(pdf.output())
