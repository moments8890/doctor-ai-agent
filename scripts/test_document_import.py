"""
本地文档导入管道测试工具。

无需 WeChat/WeCom 环境，直接用本地文件测试完整的文档解析 → 文本提取 → 病历结构化流程。

Usage:
    source .venv/bin/activate

    # Test a PDF
    python scripts/test_document_import.py path/to/report.pdf

    # Test an image (体检报告截图)
    python scripts/test_document_import.py path/to/report.jpg

    # Test a Word document
    python scripts/test_document_import.py path/to/report.docx

    # Test raw text
    python scripts/test_document_import.py path/to/report.txt

    # Test WeChat chat export
    python scripts/test_document_import.py path/to/chat_export.txt --type chat

    # Skip structuring (just show extracted text)
    python scripts/test_document_import.py path/to/report.pdf --no-structure

    # Use a specific vision LLM provider for image OCR
    VISION_LLM=gemini python scripts/test_document_import.py path/to/report.jpg
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _detect_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return "pdf"
    if suffix in (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff"):
        return "image"
    if suffix in (".docx", ".doc"):
        return "word"
    if suffix == ".txt":
        return "text"
    # Sniff bytes
    data = path.read_bytes()
    if data.startswith(b"%PDF"):
        return "pdf"
    if data.startswith(b"\xff\xd8\xff"):
        return "image"  # JPEG
    if data.startswith(b"\x89PNG"):
        return "image"
    return "text"


def _mime_type(path: Path) -> str:
    suffix = path.suffix.lower()
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".bmp": "image/bmp",
        ".tiff": "image/tiff",
    }.get(suffix, "image/jpeg")


def _extract_text(path: Path, doc_type: str) -> tuple[str, float]:
    """Extract text from file. Returns (text, elapsed_seconds)."""
    data = path.read_bytes()
    t0 = time.perf_counter()

    if doc_type == "pdf":
        from services.knowledge.pdf_extract import extract_text_from_pdf
        text = extract_text_from_pdf(data)

    elif doc_type == "word":
        from services.knowledge.word_extract import extract_text_from_docx
        text = extract_text_from_docx(data)

    elif doc_type == "text" or doc_type == "chat":
        text = data.decode("utf-8", errors="replace")

    elif doc_type == "image":
        # Image OCR is async — handled separately
        text = "__IMAGE__"

    else:
        raise ValueError(f"Unknown doc type: {doc_type}")

    elapsed = time.perf_counter() - t0
    return text, elapsed


async def _extract_image_text(path: Path) -> tuple[str, float]:
    from services.ai.vision import extract_text_from_image
    data = path.read_bytes()
    mime = _mime_type(path)
    t0 = time.perf_counter()
    text = await extract_text_from_image(data, mime)
    elapsed = time.perf_counter() - t0
    return text, elapsed


async def _structure(text: str) -> tuple[dict, float]:
    from services.ai.structuring import structure_medical_record
    t0 = time.perf_counter()
    record = await structure_medical_record(text)
    elapsed = time.perf_counter() - t0
    return record.model_dump(), elapsed


def _chunk(text: str, doc_type: str, sender_filter: str | None = None) -> tuple[list[str], float]:
    from services.wechat.wechat_domain import _preprocess_import_text, _chunk_history_text
    t0 = time.perf_counter()
    source = "chat_export" if doc_type == "chat" else doc_type
    clean = _preprocess_import_text(text, source, sender_filter=sender_filter)
    chunks = _chunk_history_text(clean)
    elapsed = time.perf_counter() - t0
    return chunks, elapsed


def _print_section(title: str, char: str = "─") -> None:
    print(f"\n{char * 60}")
    print(f"  {title}")
    print(char * 60)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Test document import pipeline locally")
    parser.add_argument("file", help="Path to document (PDF, image, Word, txt)")
    parser.add_argument("--type", choices=["pdf", "image", "word", "text", "chat"],
                        help="Override auto-detected file type")
    parser.add_argument("--no-structure", action="store_true",
                        help="Skip LLM structuring (just show extracted text + chunks)")
    parser.add_argument("--sender", help="For chat exports: only import this sender's messages")
    parser.add_argument("--max-chunks", type=int, default=3,
                        help="Max chunks to structure (default: 3, to limit LLM calls)")
    parser.add_argument("--output", help="Save full result as JSON to this file")
    args = parser.parse_args()

    path = Path(args.file)
    if not path.exists():
        print(f"ERROR: File not found: {path}")
        sys.exit(1)

    doc_type = args.type or _detect_type(path)
    print(f"\n📄 File:  {path.name}")
    print(f"   Type:  {doc_type}")
    print(f"   Size:  {path.stat().st_size:,} bytes")

    result: dict = {"file": str(path), "type": doc_type, "stages": {}}

    # ── Stage 1: Text extraction ─────────────────────────────────────────────
    _print_section("Stage 1: Text Extraction")
    if doc_type == "image":
        raw_text, t1 = await _extract_image_text(path)
    else:
        raw_text, t1 = _extract_text(path, doc_type)

    result["stages"]["extraction"] = {"elapsed_s": round(t1, 2), "chars": len(raw_text)}
    print(f"  Elapsed:  {t1:.2f}s")
    print(f"  Chars:    {len(raw_text)}")
    if raw_text:
        print(f"\n  Preview (first 400 chars):\n")
        print("  " + raw_text[:400].replace("\n", "\n  "))
    else:
        print("  ⚠️  No text extracted")
        sys.exit(1)

    # ── Stage 2: Chat sender selection (if chat export) ──────────────────────
    if doc_type == "chat":
        from services.wechat.wechat_chat_export import list_senders
        senders = list_senders(raw_text)
        _print_section("Stage 2: Chat Senders Detected")
        for i, s in enumerate(senders):
            marker = " ← will import" if (args.sender and s == args.sender) or (not args.sender and i == 0) else ""
            print(f"  {i+1}. {s}{marker}")
        if not args.sender and len(senders) > 1:
            print(f"\n  ℹ️  Use --sender NAME to filter. Importing all senders' clinical messages.")

    # ── Stage 3: Chunking ────────────────────────────────────────────────────
    _print_section("Stage 3: Chunking")
    chunks, t3 = _chunk(raw_text, doc_type, sender_filter=args.sender)
    result["stages"]["chunking"] = {"elapsed_s": round(t3, 3), "chunk_count": len(chunks)}
    print(f"  Elapsed:     {t3*1000:.1f}ms")
    print(f"  Chunks found: {len(chunks)}")
    for i, chunk in enumerate(chunks):
        preview = chunk[:120].replace("\n", " ")
        print(f"\n  [{i+1}] {preview}{'...' if len(chunk) > 120 else ''}")

    if not chunks:
        print("  ⚠️  No chunks found — check input format")
        sys.exit(1)

    # ── Stage 4: Structuring ─────────────────────────────────────────────────
    if args.no_structure:
        print("\n  (Structuring skipped — use without --no-structure to run LLM)")
    else:
        _print_section("Stage 4: LLM Structuring")
        structured = []
        to_structure = chunks[:args.max_chunks]
        print(f"  Structuring {len(to_structure)} of {len(chunks)} chunks...")
        for i, chunk in enumerate(to_structure):
            print(f"\n  Chunk {i+1}:", end=" ", flush=True)
            try:
                record, t4 = await _structure(chunk)
                structured.append({"chunk": i+1, "elapsed_s": round(t4, 2), "record": record})
                print(f"{t4:.1f}s")
                # Show key fields
                for field in ("chief_complaint", "diagnosis", "treatment_plan"):
                    val = record.get(field)
                    if val:
                        print(f"    {field}: {str(val)[:80]}")
            except Exception as e:
                print(f"FAILED — {e}")
                structured.append({"chunk": i+1, "error": str(e)})

        result["stages"]["structuring"] = structured

    # ── Summary ──────────────────────────────────────────────────────────────
    _print_section("Summary", "═")
    stages = result["stages"]
    print(f"  Extraction:   {stages['extraction']['elapsed_s']:.2f}s  →  {stages['extraction']['chars']} chars")
    print(f"  Chunking:     {stages['chunking']['elapsed_s']*1000:.1f}ms  →  {stages['chunking']['chunk_count']} chunks")
    if "structuring" in stages:
        ok = sum(1 for s in stages["structuring"] if "record" in s)
        print(f"  Structuring:  {ok}/{len(stages['structuring'])} succeeded")

    if args.output:
        out = Path(args.output)
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n  Full result saved to: {out}")

    print()


if __name__ == "__main__":
    asyncio.run(main())
