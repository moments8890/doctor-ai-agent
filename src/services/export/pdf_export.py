"""
病历 PDF 导出：使用 fpdf2 生成带中文字体的结构化病历 PDF。

字体配置（优先级）：
  1. PDF_FONT_PATH 环境变量（绝对路径）
  2. macOS STHeiti Light
  3. Ubuntu Noto CJK
  4. Arial Unicode（通用回退）

若所有字体路径均不存在，导出仍可执行但中文可能显示为方块（ASCII only fallback）。
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import List, Optional

from utils.log import log


# ---------------------------------------------------------------------------
# Font resolution
# ---------------------------------------------------------------------------

_CANDIDATE_FONTS = [
    "/System/Library/Fonts/STHeiti Light.ttc",           # macOS
    "/System/Library/Fonts/PingFang.ttc",                # macOS (newer)
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",  # Ubuntu
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",  # Ubuntu alt
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",   # Ubuntu WQY
    "/Library/Fonts/Arial Unicode.ttf",                  # macOS fallback
]


def _resolve_font_path() -> Optional[str]:
    env_path = os.environ.get("PDF_FONT_PATH", "").strip()
    if env_path and os.path.exists(env_path):
        return env_path
    for p in _CANDIDATE_FONTS:
        if os.path.exists(p):
            return p
    return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_tags(raw_tags) -> List[str]:
    if isinstance(raw_tags, list):
        return raw_tags
    if isinstance(raw_tags, str):
        try:
            parsed = json.loads(raw_tags)
            return parsed if isinstance(parsed, list) else []
        except Exception:
            return []
    return []


def _record_type_label(record_type: str) -> str:
    mapping = {
        "visit": "门诊",
        "dictation": "口述",
        "import": "导入",
        "interview_summary": "问诊总结",
    }
    return mapping.get(record_type or "visit", record_type or "门诊")


def _fmt_date(dt: Optional[datetime]) -> str:
    if dt is None:
        return "—"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.strftime("%Y-%m-%d")


def _fmt_datetime(dt: Optional[datetime]) -> str:
    if dt is None:
        return "—"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M")


# ---------------------------------------------------------------------------
# PDF generation
# ---------------------------------------------------------------------------

_RISK_LABEL = {
    "critical": "极高危",
    "high": "高危",
    "medium": "中危",
    "low": "低危",
}


def _age_from_year(year_of_birth: Optional[int]) -> Optional[int]:
    if not year_of_birth:
        return None
    return datetime.now().year - int(year_of_birth)


def _make_set_font(pdf, has_cjk: bool):
    """返回闭包，按 CJK 可用情况设置字体。"""
    def _set_font(size: int, bold: bool = False):
        if has_cjk:
            pdf.set_font("CJK", size=size)
        else:
            style = "B" if bold else ""
            pdf.set_font("Helvetica", style=style, size=size)
    return _set_font


def _draw_patient_block(pdf, _set_font, patient, patient_name, doctor_name, records) -> None:
    """绘制患者人口学信息块（含彩色背景矩形）。"""
    p_name = (getattr(patient, "name", None) if patient else None) or patient_name or "—"
    p_gender = getattr(patient, "gender", None) if patient else None
    p_yob = getattr(patient, "year_of_birth", None) if patient else None
    p_age = _age_from_year(p_yob)
    # primary_risk_level is not mapped on the Patient ORM model; always None.
    # Kept as a placeholder for future risk-scoring integration.
    p_risk = None
    p_category = getattr(patient, "primary_category", None) if patient else None

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


def _draw_record_entry(pdf, _set_font, i: int, rec) -> None:
    """绘制单条病历记录（标题行 + 内容 + 标签 + 分隔线）。"""
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

    content = (getattr(rec, "content", None) or "").strip()
    if content:
        _set_font(10)
        pdf.set_x(pdf.l_margin + 3)
        pdf.multi_cell(0, 5.5, content, new_x="LMARGIN", new_y="NEXT")

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


def generate_records_pdf(
    records: list,
    patient_name: Optional[str] = None,
    patient: object = None,
    clinic_name: Optional[str] = None,
    doctor_name: Optional[str] = None,
    scores_map: Optional[dict] = None,
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
    Returns raw PDF bytes. Raises RuntimeError if fpdf2 is not installed.
    """
    from fpdf import FPDF  # raises ImportError if not installed
    clinic = clinic_name or os.environ.get("CLINIC_NAME", "医疗机构")
    pdf, _set_font = _create_records_pdf_doc()
    pdf.add_page()

    _draw_records_title(pdf, _set_font, clinic)

    _draw_patient_block(pdf, _set_font, patient, patient_name, doctor_name, records)

    if not records:
        _set_font(10)
        pdf.set_text_color(120, 120, 120)
        pdf.cell(0, 10, "（暂无病历记录）", align="C", new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)
    else:
        for i, rec in enumerate(records):
            _draw_record_entry(pdf, _set_font, i, rec)

    return bytes(pdf.output())


# ---------------------------------------------------------------------------
# China Standard Outpatient Report PDF (卫生部 2010 门诊病历格式)
# ---------------------------------------------------------------------------

def _draw_outpatient_header(
    pdf, _sf, clinic: str,
    patient_name: Optional[str], patient_info: Optional[str],
    department: str, doctor_name: Optional[str],
) -> None:
    """绘制门诊病历标题块和患者/医生信息行。"""
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
    if patient_info:
        row_parts.append(patient_info)
    if department:
        row_parts.append(f"科别：{department}")
    if doctor_name:
        row_parts.append(f"接诊医师：{doctor_name}")
    row_parts.append(f"就诊日期：{datetime.now().strftime('%Y-%m-%d')}")
    pdf.cell(0, 7, "    ".join(row_parts), new_x="LMARGIN", new_y="NEXT")
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


def generate_outpatient_report_pdf(
    fields: dict,
    patient_name: Optional[str] = None,
    patient_info: Optional[str] = None,
    clinic_name: Optional[str] = None,
    doctor_name: Optional[str] = None,
) -> bytes:
    """按卫生部 2010 门诊病历格式生成 PDF，返回原始字节。"""
    from services.export.outpatient_report import OUTPATIENT_FIELDS, _HEADER_ONLY_FIELDS
    clinic = clinic_name or os.environ.get("CLINIC_NAME", "医疗机构")
    department = (fields.get("department") or "").strip()
    pdf, _sf = _create_outpatient_pdf_doc()
    pdf.add_page()
    _draw_outpatient_header(
        pdf, _sf, clinic,
        patient_name, patient_info, department, doctor_name,
    )
    _draw_outpatient_fields(pdf, _sf, fields, OUTPATIENT_FIELDS, _HEADER_ONLY_FIELDS)
    _draw_outpatient_footer(pdf, _sf)
    return bytes(pdf.output())
