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

def generate_records_pdf(
    records: list,
    patient_name: Optional[str] = None,
    clinic_name: Optional[str] = None,
    doctor_name: Optional[str] = None,
) -> bytes:
    """
    Generate a PDF containing one or more MedicalRecordDB rows.

    Returns raw PDF bytes. Raises RuntimeError if fpdf2 is not installed.
    """
    try:
        from fpdf import FPDF
    except ImportError:
        raise RuntimeError("fpdf2 is not installed. Run: pip install fpdf2")

    clinic = clinic_name or os.environ.get("CLINIC_NAME", "医疗机构")
    font_path = _resolve_font_path()

    pdf = FPDF()
    pdf.set_margins(left=20, top=20, right=20)
    pdf.set_auto_page_break(auto=True, margin=20)

    # Register Chinese font if available
    has_cjk = False
    if font_path:
        try:
            pdf.add_font("CJK", fname=font_path)
            has_cjk = True
            log(f"[PDF] using font: {font_path}")
        except Exception as exc:
            log(f"[PDF] font load failed ({font_path}): {exc}")

    def _set_font(size: int, bold: bool = False):
        if has_cjk:
            # CJK font registered without bold — use size to signal importance
            pdf.set_font("CJK", size=size)
        else:
            style = "B" if bold else ""
            pdf.set_font("Helvetica", style=style, size=size)

    pdf.add_page()

    # ---- Header ----
    _set_font(16, bold=True)
    pdf.cell(0, 10, clinic, align="C", new_x="LMARGIN", new_y="NEXT")
    _set_font(12)
    pdf.cell(0, 8, "病历记录", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    pdf.set_draw_color(180, 180, 180)
    pdf.line(20, pdf.get_y(), pdf.w - 20, pdf.get_y())
    pdf.ln(4)

    # ---- Patient info ----
    _set_font(10)
    info_parts = []
    if patient_name:
        info_parts.append(f"患者：{patient_name}")
    if doctor_name:
        info_parts.append(f"医生：{doctor_name}")
    info_parts.append(f"导出时间：{datetime.now().strftime('%Y-%m-%d')}")
    info_parts.append(f"共 {len(records)} 条记录")
    pdf.cell(0, 7, "  |  ".join(info_parts), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)

    # ---- Records ----
    for i, rec in enumerate(records):
        if pdf.get_y() > pdf.h - 60:
            pdf.add_page()

        # Record header
        date_str = _fmt_date(getattr(rec, "created_at", None))
        rtype = _record_type_label(getattr(rec, "record_type", "visit") or "visit")
        _set_font(11, bold=True)
        pdf.set_fill_color(245, 247, 250)
        pdf.cell(0, 8, f"  {i + 1}.  {date_str}  [{rtype}]", fill=True, new_x="LMARGIN", new_y="NEXT")

        # Content
        content = (getattr(rec, "content", None) or "").strip()
        if content:
            _set_font(10)
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(0, 6, content, new_x="LMARGIN", new_y="NEXT")

        # Tags
        tags = _parse_tags(getattr(rec, "tags", None))
        if tags:
            _set_font(9)
            pdf.set_text_color(80, 80, 180)
            pdf.cell(0, 6, "标签：" + "  ".join(tags), new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(0, 0, 0)

        pdf.ln(4)

    # ---- Footer ----
    pdf.set_y(-15)
    _set_font(8)
    pdf.set_text_color(150, 150, 150)
    pdf.cell(0, 5, f"本文件由 AI 助手生成，仅供参考，以原始病历为准  |  共 {pdf.page} 页", align="C")

    return bytes(pdf.output())


# ---------------------------------------------------------------------------
# China Standard Outpatient Report PDF (卫生部 2010 门诊病历格式)
# ---------------------------------------------------------------------------

def generate_outpatient_report_pdf(
    fields: dict,
    patient_name: Optional[str] = None,
    patient_info: Optional[str] = None,
    clinic_name: Optional[str] = None,
    doctor_name: Optional[str] = None,
) -> bytes:
    """
    Render a form-style PDF following the 卫生部 2010 门诊病历 standard.

    Args:
        fields: dict with keys from outpatient_report.OUTPATIENT_FIELDS
        patient_name: patient full name
        patient_info: extra info line (age, gender, DOB …)
        clinic_name: defaults to CLINIC_NAME env var
        doctor_name: attending physician
    Returns:
        Raw PDF bytes.
    """
    try:
        from fpdf import FPDF
    except ImportError:
        raise RuntimeError("fpdf2 is not installed. Run: pip install fpdf2")

    from services.export.outpatient_report import OUTPATIENT_FIELDS

    clinic = clinic_name or os.environ.get("CLINIC_NAME", "医疗机构")
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

    def _sf(size: int, bold: bool = False):
        if has_cjk:
            pdf.set_font("CJK", size=size)
        else:
            pdf.set_font("Helvetica", style="B" if bold else "", size=size)

    pdf.add_page()

    # ── Title block ──────────────────────────────────────────────────────────
    _sf(16, bold=True)
    pdf.cell(0, 10, clinic, align="C", new_x="LMARGIN", new_y="NEXT")
    _sf(13, bold=True)
    pdf.cell(0, 8, "门  诊  病  历", align="C", new_x="LMARGIN", new_y="NEXT")
    _sf(9)
    pdf.cell(0, 5, "（卫生部 2010 标准格式）", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    pdf.set_draw_color(60, 80, 140)
    pdf.set_line_width(0.5)
    pdf.line(18, pdf.get_y(), pdf.w - 18, pdf.get_y())
    pdf.set_line_width(0.2)
    pdf.set_draw_color(180, 180, 180)
    pdf.ln(4)

    # ── Patient / doctor info row ────────────────────────────────────────────
    _sf(10)
    row_parts: list[str] = []
    if patient_name:
        row_parts.append(f"姓名：{patient_name}")
    if patient_info:
        row_parts.append(patient_info)
    if doctor_name:
        row_parts.append(f"接诊医师：{doctor_name}")
    row_parts.append(f"就诊日期：{datetime.now().strftime('%Y-%m-%d')}")
    pdf.cell(0, 7, "    ".join(row_parts), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    pdf.line(18, pdf.get_y(), pdf.w - 18, pdf.get_y())
    pdf.ln(4)

    # ── Field sections ───────────────────────────────────────────────────────
    label_w = 22  # width of label column in mm

    for key, label in OUTPATIENT_FIELDS:
        value = (fields.get(key) or "").strip()

        if pdf.get_y() > pdf.h - 40:
            pdf.add_page()

        # Section label (shaded row)
        pdf.set_fill_color(235, 240, 250)
        _sf(10, bold=True)
        pdf.cell(label_w, 7, f"【{label}】", fill=True, new_x="RIGHT", new_y="TOP")

        # Value
        _sf(10)
        if value:
            # Calculate remaining width
            x_start = pdf.get_x()
            avail_w = pdf.w - pdf.r_margin - x_start
            pdf.multi_cell(avail_w, 7, value, new_x="LMARGIN", new_y="NEXT")
        else:
            pdf.cell(0, 7, "", new_x="LMARGIN", new_y="NEXT")

        # Thin separator
        pdf.set_draw_color(210, 210, 210)
        pdf.line(18, pdf.get_y(), pdf.w - 18, pdf.get_y())
        pdf.ln(2)

    # ── Signature block ──────────────────────────────────────────────────────
    pdf.ln(6)
    _sf(10)
    sig_line = f"接诊医师签名：{'_' * 12}    日期：{'_' * 10}"
    pdf.cell(0, 7, sig_line, new_x="LMARGIN", new_y="NEXT")

    # ── Footer ───────────────────────────────────────────────────────────────
    pdf.set_y(-15)
    _sf(8)
    pdf.set_text_color(150, 150, 150)
    pdf.cell(
        0, 5,
        "本文件由 AI 助手辅助生成，仅供参考，以原始病历为准  |  "
        f"共 {pdf.page} 页",
        align="C",
    )

    return bytes(pdf.output())
