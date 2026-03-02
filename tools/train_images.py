#!/usr/bin/env python3
"""
Image training runner: POSTs each test image to /api/records/from-image
and validates the returned MedicalRecord against per-field assertions
defined in the test plan markdown file.

Usage:
    python tools/train_images.py [markdown_file] [server_url]

Defaults:
    markdown_file : train/data/image_cases_cardiology_v1.md
    server_url    : http://127.0.0.1:8000

Examples:
    python tools/train_images.py
    python tools/train_images.py train/data/image_cases_cardiology_v1.md
    python tools/train_images.py train/data/image_cases_cardiology_v1.md http://host:8000
    python tools/train_images.py --cases 001,002
"""

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

try:
    import httpx
except ImportError:
    print("httpx not found. Run: pip install httpx")
    sys.exit(1)

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA = ROOT / "train" / "data" / "image_cases_cardiology_v1.md"
BASE_URL = "http://127.0.0.1:8000"

GREEN  = "\033[32m"
RED    = "\033[31m"
YELLOW = "\033[33m"
GRAY   = "\033[90m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

FIELDS = [
    "chief_complaint",
    "history_of_present_illness",
    "past_medical_history",
    "physical_examination",
    "auxiliary_examinations",
    "diagnosis",
    "treatment_plan",
    "follow_up_plan",
]

MIME_MAP = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
}


@dataclass
class Assertion:
    rule: str          # "non-null" | "null" | "any"
    contains: str = "" # substring that must appear in the field value


@dataclass
class ImageCase:
    number: str
    doctor: str
    patient: str
    date: str
    image_path: Path
    assertions: dict = field(default_factory=dict)  # field_name → Assertion


# ── Parsing ──────────────────────────────────────────────────────────────────

def _parse_assertion_line(line: str):
    """Parse one assertion line: '<field>: <rule> [, contains=<text>]'"""
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    m = re.match(r'^(\w+)\s*:\s*(.+)$', line)
    if not m:
        return None
    fname = m.group(1).strip()
    rest  = m.group(2).strip()
    rule     = "any"
    contains = ""
    for part in [p.strip() for p in rest.split(",")]:
        if part in ("non-null", "null", "any"):
            rule = part
        elif part.startswith("contains="):
            contains = part[len("contains="):].strip()
    return fname, Assertion(rule=rule, contains=contains)


def parse_cases(content: str, root: Path) -> list[ImageCase]:
    cases = []
    for block in re.split(r'-{40,}', content):
        block = block.strip()
        if not block:
            continue

        num_m  = re.search(r'##\s*Image Case\s*(\d+)', block)
        doc_m  = re.search(r'\*\*医生\*\*[：:]\s*(.+)', block)
        pat_m  = re.search(r'\*\*患者\*\*[：:]\s*(.+)', block)
        date_m = re.search(r'\*\*日期\*\*[：:]\s*(.+)', block)
        img_m  = re.search(r'\*\*图片\*\*[：:]\s*(.+)', block)

        if not (num_m and doc_m and pat_m and img_m):
            continue

        img_rel  = img_m.group(1).strip().rstrip('\\').strip()
        img_path = (root / img_rel).resolve()

        assertions = {}
        # Extract the ```assertions ... ``` fenced block
        assert_m = re.search(r'```assertions\s*\n(.*?)```', block, re.DOTALL)
        if assert_m:
            for line in assert_m.group(1).splitlines():
                result = _parse_assertion_line(line)
                if result:
                    fname, assertion = result
                    assertions[fname] = assertion

        cases.append(ImageCase(
            number     = num_m.group(1).strip(),
            doctor     = doc_m.group(1).strip().rstrip('\\').strip(),
            patient    = pat_m.group(1).strip().rstrip('\\').strip(),
            date       = date_m.group(1).strip().rstrip('\\').strip() if date_m else "",
            image_path = img_path,
            assertions = assertions,
        ))
    return cases


# ── API call ─────────────────────────────────────────────────────────────────

def post_image(base_url: str, image_path: Path) -> dict:
    suffix   = image_path.suffix.lower()
    mime     = MIME_MAP.get(suffix, "image/jpeg")
    img_bytes = image_path.read_bytes()

    resp = httpx.post(
        f"{base_url}/api/records/from-image",
        files={"image": (image_path.name, img_bytes, mime)},
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()


# ── Validation ────────────────────────────────────────────────────────────────

def validate(record: dict, assertions: dict) -> list[str]:
    """Return a list of failure messages (empty = all passed)."""
    failures = []
    for fname in FIELDS:
        if fname not in assertions:
            continue
        asrt  = assertions[fname]
        value = record.get(fname) or ""

        if asrt.rule == "non-null" and not value:
            failures.append(f"{fname}: expected non-null but got empty/null")
        elif asrt.rule == "null" and value:
            failures.append(f"{fname}: expected null but got {value[:40]!r}")

        if asrt.contains and asrt.rule != "null" and value:
            if asrt.contains not in value:
                failures.append(
                    f"{fname}: expected to contain {asrt.contains!r}, "
                    f"got {value[:60]!r}"
                )
    return failures


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Image pipeline training runner")
    parser.add_argument("data_path", nargs="?", default=str(DEFAULT_DATA))
    parser.add_argument("base_url",  nargs="?", default=BASE_URL)
    parser.add_argument("--cases",   help="Comma-separated case numbers, e.g. 001,002")
    args = parser.parse_args()

    data_path = Path(args.data_path)
    base_url  = args.base_url.rstrip("/")
    only      = set(args.cases.split(",")) if args.cases else None

    if not data_path.exists():
        print(f"{RED}File not found: {data_path}{RESET}")
        sys.exit(1)

    cases = parse_cases(data_path.read_text(encoding="utf-8"), ROOT)
    if only:
        cases = [c for c in cases if c.number in only]
    if not cases:
        print(f"{YELLOW}No cases parsed from {data_path}{RESET}")
        sys.exit(1)

    print(f"\n{BOLD}🖼️  Image Pipeline Training Run{RESET}")
    print(f"{GRAY}  file   : {data_path}{RESET}")
    print(f"{GRAY}  server : {base_url}{RESET}")
    print(f"{GRAY}  cases  : {len(cases)}{RESET}\n")

    results = []
    for case in cases:
        label = f"Case {case.number}  {case.patient}"
        print(f"  {label:<28}", end=" ", flush=True)

        if not case.image_path.exists():
            print(f"{RED}FAIL{RESET}  {GRAY}image not found: {case.image_path}{RESET}")
            results.append((case.number, False, "image file missing"))
            continue

        try:
            record = post_image(base_url, case.image_path)
        except httpx.ConnectError:
            print(f"{RED}FAIL{RESET}  {GRAY}cannot connect to server{RESET}")
            results.append((case.number, False, "cannot connect to server"))
            continue
        except httpx.HTTPStatusError as e:
            msg = f"HTTP {e.response.status_code}: {e.response.text[:80]}"
            print(f"{RED}FAIL{RESET}  {GRAY}{msg}{RESET}")
            results.append((case.number, False, msg))
            continue
        except Exception as e:
            msg = str(e)[:100]
            print(f"{RED}FAIL{RESET}  {GRAY}{msg}{RESET}")
            results.append((case.number, False, msg))
            continue

        failures = validate(record, case.assertions)
        complaint = record.get("chief_complaint") or ""
        diagnosis = record.get("diagnosis") or ""
        summary = complaint + (f" | dx: {diagnosis[:40]}" if diagnosis else "")

        if not failures:
            print(f"{GREEN}PASS{RESET}  {GRAY}{summary}{RESET}")
            results.append((case.number, True, summary))
        else:
            print(f"{RED}FAIL{RESET}  {GRAY}{summary}{RESET}")
            for f in failures:
                print(f"         {RED}✗{RESET} {f}")
            results.append((case.number, False, "; ".join(failures)))

    passed = sum(1 for _, ok, _ in results if ok)
    total  = len(results)
    colour = GREEN if passed == total else (YELLOW if passed > 0 else RED)

    print(f"\n{'─'*52}")
    print(f"  {BOLD}Result: {colour}{passed}/{total} passed{RESET}")

    failed = [(n, d) for n, ok, d in results if not ok]
    if failed:
        print(f"\n  {RED}Failed:{RESET}")
        for n, d in failed:
            print(f"    Case {n}: {d}")
    else:
        print(f"  {GREEN}All image cases passed.{RESET}")
    print()


if __name__ == "__main__":
    main()
