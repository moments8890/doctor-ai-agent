"""图像 → 文本提取 → 结构化病历全流程集成测试。

Integration tests for the image → extracted text → structured record pipeline.

Requires: running server + Ollama with vision model (auto-skipped otherwise).
Vision model: set OLLAMA_VISION_MODEL=qwen2.5vl:7b in .env
"""

import pytest
from pathlib import Path
import httpx

SERVER = "http://127.0.0.1:8001"
IMAGES_DIR = Path(__file__).resolve().parents[2] / "train" / "images"


def _post_image(image_path: Path) -> dict:
    with open(image_path, "rb") as f:
        resp = httpx.post(
            f"{SERVER}/api/records/from-image",
            files={"image": (image_path.name, f, "image/jpeg")},
            timeout=120,
        )
    resp.raise_for_status()
    return resp.json()


@pytest.mark.integration
@pytest.mark.parametrize("image_file", [
    "ChatGPT Image Mar 1, 2026, 05_00_42 PM.png",
    "ChatGPT Image Mar 1, 2026, 05_02_49 PM.png",
])
def test_image_extracts_and_structures(image_file):
    """Image upload → vision extraction → structured record with non-null chief_complaint."""
    image_path = IMAGES_DIR / image_file
    if not image_path.exists():
        pytest.skip(f"Test image not found: {image_file}")

    data = _post_image(image_path)

    assert "chief_complaint" in data, "Response missing chief_complaint field"
    assert data["chief_complaint"], (
        f"chief_complaint is null for image '{image_file}' — "
        "vision model may not have extracted clinical content"
    )
