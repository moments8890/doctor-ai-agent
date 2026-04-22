#!/usr/bin/env python3
"""Regenerate frontend/web/public/specs-index.json from the symlinked specs dir.

Run after adding or renaming a spec under docs/superpowers/specs/.
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
SPECS_DIR = os.path.join(ROOT, "public", "specs")
OUT = os.path.join(ROOT, "public", "specs-index.json")

if not os.path.isdir(SPECS_DIR):
    print(f"error: {SPECS_DIR} not found (did you create the symlink?)", file=sys.stderr)
    sys.exit(1)

files = sorted(f for f in os.listdir(SPECS_DIR) if f.endswith(".md"))
entries = []
for f in files:
    date = f[:10] if len(f) > 10 and f[4] == "-" and f[7] == "-" else ""
    name = f[11:] if date else f
    for suffix in ("-design.md", ".md"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
            break
    title = name.replace("-", " ").replace("_", " ")
    entries.append({"file": f, "date": date, "title": title})

with open(OUT, "w") as out:
    json.dump(entries, out, indent=2, ensure_ascii=False)
    out.write("\n")

print(f"wrote {len(entries)} entries → {OUT}")
