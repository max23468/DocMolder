from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from docmolder.branding import BRAND_COLORS


def _rounded_rectangle(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], radius: int, fill: str) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill)


def _draw_mark(draw: ImageDraw.ImageDraw, size: int) -> None:
    card_pad = int(size * 0.08)
    card_radius = int(size * 0.22)
    card_box = (card_pad, card_pad, size - card_pad, size - card_pad)
    _rounded_rectangle(draw, card_box, radius=card_radius, fill=BRAND_COLORS["slate"])

    _rounded_rectangle(
        draw,
        (
            int(size * 0.18),
            int(size * 0.13),
            int(size * 0.76),
            int(size * 0.82),
        ),
        radius=int(size * 0.09),
        fill=BRAND_COLORS["paper"],
    )

    sheet_left = int(size * 0.18)
    sheet_top = int(size * 0.13)
    sheet_right = int(size * 0.76)
    sheet_bottom = int(size * 0.82)
    fold_size = int(size * 0.13)

    draw.polygon(
        [
            (sheet_right - fold_size, sheet_top),
            (sheet_right, sheet_top),
            (sheet_right, sheet_top + fold_size),
        ],
        fill=BRAND_COLORS["mist"],
    )

    accent_left = int(size * 0.23)
    accent_right = int(size * 0.29)
    accent_top = int(size * 0.26)
    accent_bottom = int(size * 0.68)
    _rounded_rectangle(
        draw,
        (accent_left, accent_top, accent_right, accent_bottom),
        radius=int(size * 0.03),
        fill=BRAND_COLORS["teal"],
    )

    stroke_width = max(12, size // 30)
    line_left = int(size * 0.35)
    line_right = int(size * 0.67)
    draw.line(
        [(line_left, int(size * 0.34)), (line_right, int(size * 0.34))],
        fill=BRAND_COLORS["slate"],
        width=stroke_width,
    )
    draw.line(
        [(line_left, int(size * 0.46)), (line_right, int(size * 0.46))],
        fill=BRAND_COLORS["slate"],
        width=stroke_width,
    )
    draw.line(
        [(line_left, int(size * 0.58)), (int(size * 0.60), int(size * 0.58))],
        fill=BRAND_COLORS["slate"],
        width=stroke_width,
    )

    badge_size = int(size * 0.24)
    badge_left = int(size * 0.58)
    badge_top = int(size * 0.58)
    _rounded_rectangle(
        draw,
        (badge_left, badge_top, badge_left + badge_size, badge_top + badge_size),
        radius=int(size * 0.07),
        fill=BRAND_COLORS["coral"],
    )
    border_width = max(12, size // 42)
    draw.rounded_rectangle(
        (badge_left, badge_top, badge_left + badge_size, badge_top + badge_size),
        radius=int(size * 0.07),
        outline=BRAND_COLORS["slate"],
        width=border_width,
    )

    arrow_width = max(12, size // 32)
    arrow_left = badge_left + int(badge_size * 0.28)
    arrow_right = badge_left + int(badge_size * 0.72)
    arrow_top = badge_top + int(badge_size * 0.33)
    arrow_mid = badge_top + badge_size // 2
    arrow_bottom = badge_top + int(badge_size * 0.67)
    draw.line(
        [
            (arrow_left, arrow_mid),
            (arrow_right - int(badge_size * 0.12), arrow_mid),
        ],
        fill=BRAND_COLORS["paper"],
        width=arrow_width,
    )
    draw.line(
        [
            (arrow_right - int(badge_size * 0.12), arrow_mid),
            (arrow_right - int(badge_size * 0.28), arrow_top),
        ],
        fill=BRAND_COLORS["paper"],
        width=arrow_width,
    )
    draw.line(
        [
            (arrow_right - int(badge_size * 0.12), arrow_mid),
            (arrow_right - int(badge_size * 0.28), arrow_bottom),
        ],
        fill=BRAND_COLORS["paper"],
        width=arrow_width,
    )


def render_mark_png(size: int = 1024, background: str | None = None) -> Image.Image:
    oversample = 4
    render_size = size * oversample
    image = Image.new("RGBA", (render_size, render_size), color=background or BRAND_COLORS["ink"])
    draw = ImageDraw.Draw(image)
    _draw_mark(draw, render_size)
    return image.resize((size, size), Image.Resampling.LANCZOS)


def render_share_card(size: tuple[int, int] = (1600, 900)) -> Image.Image:
    width, height = size
    oversample = 2
    render_width = width * oversample
    render_height = height * oversample
    image = Image.new("RGBA", (render_width, render_height), color=BRAND_COLORS["ink"])
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(
        (120, 120, render_width - 120, render_height - 120),
        radius=96,
        fill=BRAND_COLORS["slate"],
    )
    mark = render_mark_png(size=440 * oversample, background=BRAND_COLORS["slate"])
    image.alpha_composite(mark, (160, 430))
    return image.resize(size, Image.Resampling.LANCZOS)


def render_brand_assets(output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    generated_paths: list[Path] = []

    telegram_profile = output_dir / "docmolder-telegram-profile.png"
    render_mark_png(size=2048).save(telegram_profile, format="PNG")
    generated_paths.append(telegram_profile)

    telegram_profile_jpg = output_dir / "docmolder-telegram-profile.jpg"
    render_mark_png(size=2048).convert("RGB").save(telegram_profile_jpg, format="JPEG", quality=98)
    generated_paths.append(telegram_profile_jpg)

    app_icon = output_dir / "docmolder-app-icon.png"
    render_mark_png(size=1024).save(app_icon, format="PNG")
    generated_paths.append(app_icon)

    share_card = output_dir / "docmolder-share-card.png"
    render_share_card().save(share_card, format="PNG")
    generated_paths.append(share_card)

    return generated_paths
