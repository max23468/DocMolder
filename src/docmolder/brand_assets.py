from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from docmolder.branding import BRAND_COLORS


def _rounded_rectangle(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], radius: int, fill: str) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill)


def _draw_mark(draw: ImageDraw.ImageDraw, size: int) -> None:
    padding = int(size * 0.12)
    sheet_left = padding
    sheet_top = padding
    sheet_right = size - padding
    sheet_bottom = size - padding
    fold_size = int(size * 0.19)

    _rounded_rectangle(
        draw,
        (sheet_left, sheet_top, sheet_right, sheet_bottom),
        radius=int(size * 0.16),
        fill=BRAND_COLORS["paper"],
    )

    draw.polygon(
        [
            (sheet_right - fold_size, sheet_top),
            (sheet_right, sheet_top),
            (sheet_right, sheet_top + fold_size),
        ],
        fill=BRAND_COLORS["mist"],
    )

    stroke_width = max(10, size // 32)
    line_left = int(size * 0.30)
    line_right = int(size * 0.70)

    draw.line(
        [(line_left, int(size * 0.39)), (line_right, int(size * 0.39))],
        fill=BRAND_COLORS["teal"],
        width=stroke_width,
    )
    draw.line(
        [(line_left, int(size * 0.51)), (line_right, int(size * 0.51))],
        fill=BRAND_COLORS["slate"],
        width=stroke_width,
    )
    draw.line(
        [(line_left, int(size * 0.63)), (int(size * 0.58), int(size * 0.63))],
        fill=BRAND_COLORS["slate"],
        width=stroke_width,
    )

    badge_size = int(size * 0.24)
    badge_left = size - padding - badge_size
    badge_top = size - padding - badge_size
    draw.ellipse(
        (badge_left, badge_top, badge_left + badge_size, badge_top + badge_size),
        fill=BRAND_COLORS["coral"],
    )
    arrow_width = max(10, size // 34)
    arrow_mid_x = badge_left + badge_size // 2
    arrow_mid_y = badge_top + badge_size // 2
    draw.line(
        [
            (arrow_mid_x - badge_size * 0.18, arrow_mid_y),
            (arrow_mid_x + badge_size * 0.12, arrow_mid_y),
        ],
        fill=BRAND_COLORS["paper"],
        width=arrow_width,
    )
    draw.line(
        [
            (arrow_mid_x + badge_size * 0.12, arrow_mid_y),
            (arrow_mid_x, arrow_mid_y - badge_size * 0.12),
        ],
        fill=BRAND_COLORS["paper"],
        width=arrow_width,
    )
    draw.line(
        [
            (arrow_mid_x + badge_size * 0.12, arrow_mid_y),
            (arrow_mid_x, arrow_mid_y + badge_size * 0.12),
        ],
        fill=BRAND_COLORS["paper"],
        width=arrow_width,
    )


def render_mark_png(size: int = 1024, background: str | None = None) -> Image.Image:
    image = Image.new("RGBA", (size, size), color=background or BRAND_COLORS["ink"])
    draw = ImageDraw.Draw(image)
    _draw_mark(draw, size)
    return image


def render_share_card(size: tuple[int, int] = (1600, 900)) -> Image.Image:
    width, height = size
    image = Image.new("RGBA", size, color=BRAND_COLORS["ink"])
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(
        (60, 60, width - 60, height - 60),
        radius=48,
        fill=BRAND_COLORS["slate"],
    )
    mark = render_mark_png(size=340, background=BRAND_COLORS["slate"])
    image.alpha_composite(mark, (110, 280))
    return image


def render_brand_assets(output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    generated_paths: list[Path] = []

    telegram_profile = output_dir / "docmolder-telegram-profile.png"
    render_mark_png(size=1024).save(telegram_profile, format="PNG")
    generated_paths.append(telegram_profile)

    telegram_profile_jpg = output_dir / "docmolder-telegram-profile.jpg"
    render_mark_png(size=1024).convert("RGB").save(telegram_profile_jpg, format="JPEG", quality=95)
    generated_paths.append(telegram_profile_jpg)

    app_icon = output_dir / "docmolder-app-icon.png"
    render_mark_png(size=512).save(app_icon, format="PNG")
    generated_paths.append(app_icon)

    share_card = output_dir / "docmolder-share-card.png"
    render_share_card().save(share_card, format="PNG")
    generated_paths.append(share_card)

    return generated_paths
