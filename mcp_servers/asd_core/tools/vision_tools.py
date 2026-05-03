"""
ASD v12.0 — Vision MCP Tools.

Vision Cascade for drawing analysis: Stage 1 (overview → tiles) + Stage 2 (tile detail).
Supports MLX-VLM on Mac Studio, Ollama Cloud VLM on dev_linux.
"""

import base64
import json
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# VLM model: Gemma 4 31B Cloud on dev_linux, MLX-VLM on Mac Studio
_VLM_MODEL = os.environ.get("ASD_VLM_MODEL", "gemma4:31b-cloud")
_OLLAMA_URL = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434")

_VISION_SYSTEM_PROMPT = """Ты — инженер ПТО. Проанализируй чертёж и ответь строго в JSON.

Для общего анализа верни:
{
  "drawing_type": "AR|KR|OV|VK|EOM|PZ|GP",
  "stamp": {"project": "...", "drawing_number": "...", "date": "ДД.ММ.ГГГГ", "scale": "..."},
  "tiles": [{"x": int, "y": int, "width": int, "height": int, "description": "..."}],
  "materials_detected": ["...", "..."],
  "notes": "..."
}

Для детального анализа tile верни:
{
  "dimensions": [{"value": float, "unit": "мм|м", "description": "..."}],
  "materials": [{"name": "...", "mark": "...", "gost": "..."}],
  "quantities": [{"item": "...", "value": float, "unit": "шт|м|м³|т"}],
  "notes": "..."
}
"""


async def _call_vlm(image_base64: str, question: str) -> dict:
    """Call VLM API (Ollama or MLX). Returns parsed JSON dict."""
    import aiohttp

    payload = {
        "model": _VLM_MODEL,
        "messages": [
            {"role": "system", "content": _VISION_SYSTEM_PROMPT},
            {"role": "user", "content": question, "images": [image_base64]},
        ],
        "format": "json",
        "stream": False,
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{_OLLAMA_URL}/api/chat",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=120),
            ) as resp:
                data = await resp.json()
                content = data.get("message", {}).get("content", "{}")
                return json.loads(content) if isinstance(content, str) else content
    except Exception as e:
        logger.error("VLM call failed: %s", e)
        return {"error": str(e)}


def _image_to_base64(image_path: str) -> str:
    """Convert image file to base64 string."""
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    # Support PDF: extract page 1 as image
    if path.suffix.lower() == ".pdf":
        import subprocess
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp_png = tmp.name
        try:
            subprocess.run(
                ["pdftoppm", "-png", "-r", "150", "-f", "1", "-l", "1",
                 str(path), tmp_png.replace(".png", "")],
                check=True, capture_output=True, timeout=30,
            )
            with open(tmp_png, "rb") as f:
                return base64.b64encode(f.read()).decode()
        finally:
            Path(tmp_png).unlink(missing_ok=True)

    # Regular image
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


async def vision_analyze(
    image_path: str,
    drawing_type: Optional[str] = None,
) -> dict:
    """
    Стадия 1 Vision Cascade: общий анализ чертежа.

    Определяет тип документа (АР/КР/ОВ/ВК/ЭОМ/ПЗ), извлекает штампы,
    формирует карту tiles для детального анализа.

    Args:
        image_path: Путь к файлу изображения (PNG, JPG, PDF).
        drawing_type: Подсказка типа документа (AR|KR|OV|VK|EOM|PZ).
                      Если None — определяется VLM автоматически.

    Returns:
        dict: {status, drawing_type, stamp, tiles, materials_detected, metadata}
    """
    if not Path(image_path).exists():
        return {"status": "error", "image_path": image_path, "message": "File not found"}

    question = "Выполни ОБЩИЙ анализ чертежа: определи тип, прочитай штамп, выдели зоны для детального анализа."
    if drawing_type:
        question += f"\nПредположительный тип чертежа: {drawing_type}"

    try:
        img_b64 = _image_to_base64(image_path)
        result = await _call_vlm(img_b64, question)

        if "error" in result:
            return {"status": "vlm_error", "image_path": image_path, "error": result["error"]}

        return {
            "status": "ok",
            "image_path": image_path,
            "drawing_type": result.get("drawing_type", drawing_type),
            "stamp": result.get("stamp", {}),
            "tiles": result.get("tiles", []),
            "materials_detected": result.get("materials_detected", []),
            "notes": result.get("notes", ""),
            "metadata": {"model": _VLM_MODEL, "stage": "overview"},
        }
    except FileNotFoundError as e:
        return {"status": "error", "image_path": image_path, "message": str(e)}


async def vision_tile(
    image_path: str,
    tile_coords: tuple,
    context: Optional[str] = None,
) -> dict:
    """
    Стадия 2 Vision Cascade: детальный анализ одного tile.

    Извлекает размеры, материалы, марки, спецификации из заданной зоны чертежа.

    Args:
        image_path: Путь к исходному изображению.
        tile_coords: (x, y, width, height) — координаты зоны в пикселях.
        context: Контекст из общего анализа для данного tile.

    Returns:
        dict: {status, dimensions, materials, quantities, metadata}
    """
    if not Path(image_path).exists():
        return {"status": "error", "image_path": image_path, "message": "File not found"}

    x, y, w, h = tile_coords
    question = f"ДЕТАЛЬНЫЙ анализ зоны чертежа (x={x}, y={y}, width={w}, height={h}). Извлеки размеры, материалы, марки, спецификации."
    if context:
        question += f"\nКонтекст: {context}"

    try:
        img_b64 = _image_to_base64(image_path)
        result = await _call_vlm(img_b64, question)

        if "error" in result:
            return {"status": "vlm_error", "image_path": image_path, "error": result["error"]}

        return {
            "status": "ok",
            "image_path": image_path,
            "tile_coords": list(tile_coords),
            "dimensions": result.get("dimensions", []),
            "materials": result.get("materials", []),
            "quantities": result.get("quantities", []),
            "notes": result.get("notes", ""),
            "metadata": {"model": _VLM_MODEL, "stage": "tile_detail"},
        }
    except FileNotFoundError as e:
        return {"status": "error", "image_path": image_path, "message": str(e)}
