"""
病历记录 PDF 生成：generate_records_pdf() 及其私有辅助函数。

依赖 pdf_export.py 中的共享辅助工具（字体解析、日期格式化等）。
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

from utils.log import log
from utils.response_formatting import parse_tags as _parse_tags

from domain.records.pdf_helpers import (
    _FIELD_LABELS,
    _RISK_LABEL,
    _age_from_year,
    _allowed_fields,
    _fmt_datetime,
    _make_set_font,
    _record_type_label,
    _resolve_font_path,
)


# ---------------------------------------------------------------------------
# Records PDF — private helpers
# ---------------------------------------------------------------------------

def _draw_patient_block(pdf, _set_font, patient, patient_name, doctor_name, records) -> None:
    """绘制患者人口学信息块（含彩色背景矩形）。"""
    p_name = (getattr(patient, "name", None) if patient else None) or patient_name or "—"
    p_gender = getattr(patient, "gender", None) if patient else None
    p_yob = getattr(patient, "year_of_birth", None) if patient else None
    p_age = _age_from_year(p_yob)
    p_risk = None
    p_category = None

    pdf.set_fill_color(240, 245, 255)
    pdf.set_draw_color(180, 200, 240)
    box_y = pdf.get_y()
    box_h = 22
    pdf.rect(20, box_y, pdf.w - 40, box_h, style="FD")
    pdf.set_y(box_y + 2)
    _set_font(13, bold=True)
    pdf.set_x(25)
    pdf.cell(0, 8, f"患者：{p_name}", new_x="LMARGIN", new_y="NEXT")

    _set_font(9)
    pdf.set_text_color(80, 80, 80)
    meta_parts: list[str] = []
    if p_gender:
        meta_parts.append(p_gender)
    if p_age is not None:
        meta_parts.append(f"{p_age} 岁（{p_yob} 年生）")
    if p_category:
        meta_parts.append(f"专科：{p_category}")
    if p_risk:
        meta_parts.append(f"风险：{_RISK_LABEL.get(p_risk, p_risk)}")
    if doctor_name:
        meta_parts.append(f"医生：{doctor_name}")
    meta_parts.append(f"共 {len(records)} 条记录")
    meta_parts.append(f"导出日期：{datetime.now().strftime('%Y-%m-%d')}")
    pdf.set_x(25)
    pdf.cell(0, 6, "  ｜  ".join(meta_parts), new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    pdf.set_y(box_y + box_h + 4)
    pdf.set_draw_color(180, 180, 180)


def _draw_record_entry(pdf, _set_font, i: int, rec, allowed_fields: Optional[set] = None) -> None:
    """绘制单条病历记录（标题行 + 内容 + 标签 + 分隔线）。

    When *allowed_fields* is ``None`` the full record is rendered (backwards-
    compatible).  When it is a set of field names, only structured fields whose
    key is in the set are rendered — the raw ``content`` blob is skipped.
    """
    if pdf.get_y() > pdf.h - 55:
        pdf.add_page()

    date_str = _fmt_datetime(getattr(rec, "created_at", None))
    rtype = _record_type_label(getattr(rec, "record_type", "visit") or "visit")
    rec_id = getattr(rec, "id", None)

    header_parts = [f"{i + 1}.", date_str, f"[{rtype}]"]
    if rec_id is not None:
        header_parts.append(f"#R{rec_id}")

    _set_font(10, bold=True)
    pdf.set_fill_color(235, 240, 250)
    pdf.set_text_color(30, 50, 100)
    pdf.cell(0, 7, "  " + "  ".join(header_parts), fill=True, new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)

    if allowed_fields is None:
        # ---- unfiltered (original behaviour): render raw content blob ----
        content = (getattr(rec, "content", None) or "").strip()
        if content:
            _set_font(10)
            pdf.set_x(pdf.l_margin + 3)
            pdf.multi_cell(0, 5.5, content, new_x="LMARGIN", new_y="NEXT")
    else:
        # ---- filtered: render only structured fields in *allowed_fields* --
        for field_key in _FIELD_LABELS:
            if field_key not in allowed_fields:
                continue
            value = (getattr(rec, field_key, None) or "").strip()
            if not value:
                continue
            if pdf.get_y() > pdf.h - 40:
                pdf.add_page()
            label = _FIELD_LABELS[field_key]
            _set_font(9, bold=True)
            pdf.set_text_color(60, 60, 60)
            pdf.set_x(pdf.l_margin + 3)
            pdf.cell(0, 6, f"【{label}】", new_x="LMARGIN", new_y="NEXT")
            _set_font(10)
            pdf.set_text_color(0, 0, 0)
            pdf.set_x(pdf.l_margin + 6)
            pdf.multi_cell(0, 5.5, value, new_x="LMARGIN", new_y="NEXT")

    tags = _parse_tags(getattr(rec, "tags", None))
    if tags:
        _set_font(9)
        pdf.set_text_color(60, 80, 180)
        pdf.set_x(pdf.l_margin + 3)
        pdf.cell(0, 5, "标签：" + "  ·  ".join(tags), new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)

    pdf.set_draw_color(210, 215, 225)
    pdf.line(20, pdf.get_y() + 2, pdf.w - 20, pdf.get_y() + 2)
    pdf.ln(6)


def _create_records_pdf_doc():
    """创建病历 PDF 文档对象并注册字体，返回 (pdf, _set_font)。"""
    from fpdf import FPDF
    font_path = _resolve_font_path()
    _footer_text = "本文件由 AI 助手生成，仅供参考，以原始病历为准"

    class _PDF(FPDF):
        """FPDF subclass with per-page footer."""
        _has_cjk = False

        def footer(self):
            self.set_y(-13)
            if self._has_cjk:
                self.set_font("CJK", size=8)
            else:
                self.set_font("Helvetica", size=8)
            self.set_text_color(150, 150, 150)
            self.cell(0, 5, f"{_footer_text}  |  第 {self.page_no()} / {{nb}} 页", align="C")

    pdf = _PDF()
    pdf.alias_nb_pages()
    pdf.set_margins(left=20, top=20, right=20)
    pdf.set_auto_page_break(auto=True, margin=18)
    has_cjk = False
    if font_path:
        try:
            pdf.add_font("CJK", fname=font_path)
            has_cjk = True
            _PDF._has_cjk = True
            log(f"[PDF] using font: {font_path}")
        except Exception as exc:
            log(f"[PDF] font load failed ({font_path}): {exc}")
    return pdf, _make_set_font(pdf, has_cjk)


def _draw_records_title(pdf, _set_font, clinic: str) -> None:
    """绘制病历记录标题和分隔线。"""
    _set_font(15, bold=True)
    pdf.cell(0, 9, clinic, align="C", new_x="LMARGIN", new_y="NEXT")
    _set_font(11)
    pdf.cell(0, 7, "病  历  记  录", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    pdf.set_draw_color(60, 80, 140)
    pdf.set_line_width(0.5)
    pdf.line(20, pdf.get_y(), pdf.w - 20, pdf.get_y())
    pdf.set_line_width(0.2)
    pdf.set_draw_color(180, 180, 180)
    pdf.ln(5)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_records_pdf(
    records: list,
    patient_name: Optional[str] = None,
    patient: object = None,
    clinic_name: Optional[str] = None,
    doctor_name: Optional[str] = None,
    scores_map: Optional[dict] = None,
    sections: Optional[set] = None,
) -> bytes:
    """
    Generate a PDF containing one or more MedicalRecordDB rows.

    Args:
        records: list of MedicalRecordDB ORM objects
        patient_name: fallback name string if patient object not given
        patient: Patient ORM object for rich demographics block
        clinic_name: overrides CLINIC_NAME env var
        doctor_name: attending physician name
        scores_map: ignored (kept for call-site compatibility)
        sections: optional set of section keys (e.g. ``{"diagnosis", "visits"}``).
            When provided, only structured fields belonging to these sections
            are rendered.  ``"basic"`` controls the patient demographics block.
            When ``None``, the full record is rendered (backwards compatible).
    Returns raw PDF bytes. Raises RuntimeError if fpdf2 is not installed.
    """
    from fpdf import FPDF  # raises ImportError if not installed
    clinic = clinic_name or os.environ.get("CLINIC_NAME", "医疗机构")
    pdf, _set_font = _create_records_pdf_doc()
    pdf.add_page()

    _draw_records_title(pdf, _set_font, clinic)

    # "basic" section controls the patient demographics block.
    # When sections is None (unfiltered) or explicitly contains "basic", draw it.
    if sections is None or "basic" in sections:
        _draw_patient_block(pdf, _set_font, patient, patient_name, doctor_name, records)

    # Compute the set of allowed structured fields (None = render raw content).
    af = _allowed_fields(sections)

    if not records:
        _set_font(10)
        pdf.set_text_color(120, 120, 120)
        pdf.cell(0, 10, "（暂无病历记录）", align="C", new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)
    else:
        for i, rec in enumerate(records):
            _draw_record_entry(pdf, _set_font, i, rec, allowed_fields=af)

    return bytes(pdf.output())
