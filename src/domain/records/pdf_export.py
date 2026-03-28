"""
病历 PDF 导出：薄型重新导出枢纽。

字体配置（优先级）：
  1. PDF_FONT_PATH 环境变量（绝对路径）
  2. macOS STHeiti Light
  3. Ubuntu Noto CJK
  4. Arial Unicode（通用回退）

若所有字体路径均不存在，导出仍可执行但中文可能显示为方块（ASCII only fallback）。

实现细节：
  - pdf_helpers.py   — 共享辅助工具（字体、日期格式化等）
  - pdf_records.py   — generate_records_pdf() 及其私有辅助
  - pdf_outpatient.py — generate_outpatient_report_pdf() 及其私有辅助
"""
from __future__ import annotations

# Re-export shared constants so existing importers continue to work.
from domain.records.pdf_helpers import VALID_SECTIONS  # noqa: F401

# Re-export the two public generators.
from domain.records.pdf_records import generate_records_pdf  # noqa: F401
from domain.records.pdf_outpatient import generate_outpatient_report_pdf  # noqa: F401

__all__ = [
    "VALID_SECTIONS",
    "generate_records_pdf",
    "generate_outpatient_report_pdf",
]
