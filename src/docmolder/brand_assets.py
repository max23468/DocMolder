from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from docmolder.branding import BRAND_COLORS, BRAND_NAME, BRAND_TAGLINE


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOURCE_MARK = PROJECT_ROOT / "assets" / "brand" / "docmolder-mark-master.png"
SOURCE_MARK_SVG = PROJECT_ROOT / "assets" / "brand" / "docmolder-mark-master.svg"


def _load_font(size: int, *, bold: bool = False, family: str = "avenir") -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    family_candidates: dict[str, tuple[str, ...]] = {
        "avenir": ("/System/Library/Fonts/Avenir Next.ttc",),
        "helvetica": ("/System/Library/Fonts/HelveticaNeue.ttc",),
        "sf": ("/System/Library/Fonts/SFNS.ttf",),
    }
    fallback = (
        (
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
            "/System/Library/Fonts/Supplemental/Arial.ttf",
        )
        if bold
        else ("/System/Library/Fonts/Supplemental/Arial.ttf",)
    )
    candidates = (*family_candidates.get(family, family_candidates["avenir"]), *fallback)
    for path in candidates:
        try:
            return ImageFont.truetype(path, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _load_source_mark(size: int) -> Image.Image:
    return Image.open(SOURCE_MARK).convert("RGBA").resize((size, size), Image.Resampling.LANCZOS)


def render_circle_variant(size: int = 1024) -> Image.Image:
    return _load_source_mark(size)


def render_square_variant(size: int = 1024) -> Image.Image:
    image = Image.new("RGBA", (size, size), BRAND_COLORS["slate"])
    mark = _load_source_mark(int(size * 0.82))
    image.alpha_composite(mark, ((size - mark.width) // 2, (size - mark.height) // 2))
    return image


def render_ios_variant(size: int = 1024) -> Image.Image:
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    pad = int(size * 0.04)
    draw.rounded_rectangle(
        (pad, pad, size - pad, size - pad),
        radius=int(size * 0.22),
        fill=BRAND_COLORS["slate"],
    )
    mark = _load_source_mark(int(size * 0.76))
    canvas.alpha_composite(mark, ((size - mark.width) // 2, (size - mark.height) // 2))
    return canvas


def render_horizontal_logo(size: tuple[int, int] = (1800, 560), *, font_family: str = "avenir") -> Image.Image:
    image = Image.new("RGBA", size, BRAND_COLORS["ink"])
    mark = _load_source_mark(340)
    image.alpha_composite(mark, (96, 108))

    draw = ImageDraw.Draw(image)
    title_font = _load_font(128, bold=True, family=font_family)
    subtitle_font = _load_font(34, bold=False, family=font_family)
    draw.text((500, 150), BRAND_NAME, fill=BRAND_COLORS["paper"], font=title_font)
    draw.text((506, 286), BRAND_TAGLINE, fill=BRAND_COLORS["mist"], font=subtitle_font)
    return image


def render_share_card(size: tuple[int, int] = (1600, 900)) -> Image.Image:
    width, height = size
    image = Image.new("RGBA", (width, height), BRAND_COLORS["ink"])
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(
        (90, 90, width - 90, height - 90),
        radius=72,
        fill=BRAND_COLORS["slate"],
    )
    mark = _load_source_mark(320)
    image.alpha_composite(mark, (120, 290))

    title_font = _load_font(116, bold=True, family="avenir")
    subtitle_font = _load_font(34, family="avenir")
    body_font = _load_font(30, family="avenir")
    draw.text((500, 280), BRAND_NAME, fill=BRAND_COLORS["paper"], font=title_font)
    draw.text((506, 412), BRAND_TAGLINE, fill=BRAND_COLORS["mist"], font=subtitle_font)
    draw.text(
        (506, 492),
        "Utility documentale Telegram-first per PDF, scansioni e immagini.",
        fill=BRAND_COLORS["paper"],
        font=body_font,
    )
    return image


def render_brand_assets(output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    generated_paths: list[Path] = []

    named_images: tuple[tuple[str, Image.Image], ...] = (
        ("docmolder-logo-square.png", render_square_variant(size=2048)),
        ("docmolder-logo-ios-rounded.png", render_ios_variant(size=2048)),
        ("docmolder-app-icon.png", render_ios_variant(size=1024)),
        ("docmolder-logo-horizontal.png", render_horizontal_logo(font_family="avenir")),
        ("docmolder-share-card.png", render_share_card()),
    )

    for filename, image in named_images:
        path = output_dir / filename
        image.save(path, format="PNG")
        generated_paths.append(path)

    telegram_profile_jpg = output_dir / "docmolder-telegram-profile.jpg"
    render_circle_variant(size=2048).convert("RGB").save(telegram_profile_jpg, format="JPEG", quality=98)
    generated_paths.append(telegram_profile_jpg)

    return generated_paths
