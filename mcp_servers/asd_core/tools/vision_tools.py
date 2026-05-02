"""Vision tools for drawing analysis — Vision Cascade."""

from typing import Optional
import uuid


def vision_analyze(
    image_path: str,
    drawing_type: Optional[str] = None,
) -> dict:
    """
    Стадия 1 Vision Cascade: общий анализ чертежа.

    Определяет тип документа, извлекает штампы, формирует карту tiles
    для детального анализа.

    Args:
        image_path: Путь к файлу изображения чертежа.
        drawing_type: Подсказка типа (AR|KR|OV|VK|EOM). Если None — определяется автоматически.

    Returns:
        dict с результатами общего анализа и списком tile-координат.
    """
    # TODO: integrate with MLX vision model
    return {
        "task_id": str(uuid.uuid4()),
        "status": "not_implemented",
        "image_path": image_path,
        "drawing_type": drawing_type,
        "tiles": [],
        "metadata": {
            "note": "Vision pipeline pending MLX integration",
        },
    }


def vision_tile(
    image_path: str,
    tile_coords: tuple[int, int, int, int],
    context: Optional[str] = None,
) -> dict:
    """
    Стадия 2 Vision Cascade: детальный анализ одного tile.

    Args:
        image_path: Путь к исходному изображению.
        tile_coords: (x, y, width, height) области tile.
        context: Контекст из общего анализа для данного tile.

    Returns:
        dict с извлечёнными данными (размеры, материалы, марки).
    """
    # TODO: implement tile extraction + MLX vision inference
    return {
        "task_id": str(uuid.uuid4()),
        "status": "not_implemented",
        "coords": list(tile_coords),
        "extracted_items": [],
        "metadata": {
            "note": "Tile inference pipeline pending MLX integration",
        },
    }
