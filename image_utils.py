"""Image loading utilities for pm970 refresh pipeline."""

from __future__ import annotations

from pathlib import Path

from PIL import Image


def to_java_int32(argb: int) -> int:
    """Convert unsigned ARGB (0..4294967295) to signed Java int32."""
    argb &= 0xFFFFFFFF
    return argb - 0x100000000 if argb >= 0x80000000 else argb


def load_argb_pixels(
    path: str | Path,
    width: int,
    height: int,
) -> list[int]:
    """
    Load image file and return Android-style ARGB pixel array.

    Matches Bitmap.getPixels() format used by CardSdkAgent.getRefreshData():
      (A << 24) | (R << 16) | (G << 8) | B
    """
    image_path = Path(path)
    if not image_path.is_file():
        raise FileNotFoundError(f"Image not found: {image_path}")

    with Image.open(image_path) as img:
        rgba = img.convert("RGBA").resize((width, height), Image.Resampling.LANCZOS)
        pixels: list[int] = []
        for r, g, b, a in rgba.getdata():
            argb = ((a & 0xFF) << 24) | ((r & 0xFF) << 16) | ((g & 0xFF) << 8) | (b & 0xFF)
            if a < 255:
                # Match DitheringUtils behaviour for translucent pixels on white background.
                inv_alpha = 255 - a
                r = min(255, r + inv_alpha)
                g = min(255, g + inv_alpha)
                b = min(255, b + inv_alpha)
                argb = (0xFF << 24) | ((r & 0xFF) << 16) | ((g & 0xFF) << 8) | (b & 0xFF)
            pixels.append(to_java_int32(argb))
    return pixels


def resolve_lcd_type(side_a: str | None, side_b: str | None, same_image: bool) -> int:
    """Resolve LCD type the same way as selfDeveloped.BleManager.connectBle2()."""
    from .constants import LCD_TYPE_DIFFERENT_AB, LCD_TYPE_EQUAL_AB, LCD_TYPE_ONLY_A, LCD_TYPE_ONLY_B

    has_a = side_a is not None
    has_b = side_b is not None

    if has_a and has_b:
        return LCD_TYPE_EQUAL_AB if same_image else LCD_TYPE_DIFFERENT_AB
    if has_a:
        return LCD_TYPE_ONLY_A
    if has_b:
        return LCD_TYPE_ONLY_B
    raise ValueError("At least one image (A or B) is required")
