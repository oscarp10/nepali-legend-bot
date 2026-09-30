from __future__ import annotations

import io
from typing import Sequence, TypedDict

from PIL import Image, ImageDraw, ImageFont


class LogHit(TypedDict, total=False):
    name: str
    stars: int
    destruction: int
    trophies: int


def progress_bar(current: int, total: int, *, width: int = 10) -> str:
    """Unicode bar for attack/defense progress."""
    total = max(1, total)
    current = max(0, min(current, total))
    filled = int(round(width * current / total))
    return "▰" * filled + "▱" * (width - filled)


def destruction_bar(pct: int, *, width: int = 8) -> str:
    pct = max(0, min(100, pct))
    filled = int(round(width * pct / 100))
    return "█" * filled + "░" * (width - filled)


def _font(size: int) -> ImageFont.ImageFont:
    for name in (
        "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansCJKjp-Bold.otf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/Library/Fonts/Arial Bold.ttf",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
    ):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


# Clash names often use phonetic small-caps that many fonts miss
_SMALL_CAPS = str.maketrans(
    {
        "ᴀ": "a",
        "ʙ": "b",
        "ᴄ": "c",
        "ᴅ": "d",
        "ᴇ": "e",
        "ꜰ": "f",
        "ɢ": "g",
        "ʜ": "h",
        "ɪ": "i",
        "ᴊ": "j",
        "ᴋ": "k",
        "ʟ": "l",
        "ᴍ": "m",
        "ɴ": "n",
        "ᴏ": "o",
        "ᴘ": "p",
        "ǫ": "q",
        "ʀ": "r",
        "ꜱ": "s",
        "ᴛ": "t",
        "ᴜ": "u",
        "ᴠ": "v",
        "ᴡ": "w",
        "ʏ": "y",
        "ᴢ": "z",
        "Ｇ": "G",
        "Ａ": "A",
    }
)


def _readable_name(name: str) -> str:
    import unicodedata

    return unicodedata.normalize("NFKC", name).translate(_SMALL_CAPS)


def board_banner_png(
    *,
    title: str,
    clan_tag: str,
    day_key: str,
    podium: Sequence[tuple[str, int]],
    accent: tuple[int, int, int] = (200, 150, 60),
) -> bytes:
    """Compact gold/stone day-board banner with optional top-3 podium."""
    w, h = 800, 220
    img = Image.new("RGB", (w, h), (42, 32, 22))
    draw = ImageDraw.Draw(img)

    # Stone gradient bands
    for y in range(h):
        t = y / h
        r = int(55 + 40 * t)
        g = int(42 + 28 * t)
        b = int(28 + 18 * t)
        draw.line([(0, y), (w, y)], fill=(r, g, b))

    # Gold frame
    draw.rounded_rectangle(
        [12, 12, w - 12, h - 12],
        radius=18,
        outline=accent,
        width=3,
    )
    draw.rounded_rectangle(
        [20, 20, w - 20, h - 20],
        radius=14,
        outline=(accent[0] // 2, accent[1] // 2, accent[2] // 2),
        width=1,
    )

    title_font = _font(36)
    sub_font = _font(20)
    small_font = _font(18)

    draw.text((40, 36), title, fill=(255, 230, 170), font=title_font)
    draw.text(
        (40, 84),
        f"{clan_tag}  ·  Legend day {day_key}",
        fill=(220, 200, 160),
        font=sub_font,
    )

    medals = ("🥇", "🥈", "🥉")
    # Draw podium as plain text (emoji may not render in default fonts — use #1 #2 #3)
    labels = ("#1", "#2", "#3")
    x = 40
    y = 130
    if podium:
        draw.text((40, 118), "Today's podium", fill=accent, font=small_font)
        for i, (name, net) in enumerate(podium[:3]):
            label = labels[i] if i < 3 else f"#{i+1}"
            sign = f"+{net}" if net >= 0 else str(net)
            draw.text(
                (x + i * 250, y + 10),
                f"{label}  {name[:16]}",
                fill=(255, 245, 220),
                font=small_font,
            )
            draw.text(
                (x + i * 250, y + 36),
                f"{sign} trophies",
                fill=(180, 220, 140),
                font=small_font,
            )
    else:
        draw.text(
            (40, 140),
            "Season warming up — podium appears when hits land",
            fill=(180, 160, 130),
            font=small_font,
        )

    # Trophy accent circle
    draw.ellipse([700, 40, 760, 100], outline=accent, width=3)
    draw.text((714, 52), "🏆", fill=accent, font=_font(28))

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _draw_star(draw: ImageDraw.ImageDraw, cx: int, cy: int, r: int, filled: bool) -> None:
    # Compact 5-point star
    from math import cos, pi, sin

    pts = []
    for i in range(10):
        ang = -pi / 2 + i * pi / 5
        rad = r if i % 2 == 0 else r * 0.42
        pts.append((cx + rad * cos(ang), cy + rad * sin(ang)))
    if filled:
        draw.polygon(pts, fill=(255, 210, 40))
    else:
        draw.polygon(pts, outline=(170, 170, 175), fill=(90, 90, 98))


def _draw_trophy(draw: ImageDraw.ImageDraw, x: int, y: int, s: int = 14) -> None:
    gold = (255, 200, 50)
    dark = (180, 130, 20)
    draw.ellipse([x, y, x + s, y + s * 0.7], fill=gold, outline=dark)
    draw.rectangle([x + s * 0.35, y + s * 0.55, x + s * 0.65, y + s * 0.85], fill=gold)
    draw.rectangle([x + s * 0.2, y + s * 0.85, x + s * 0.8, y + s], fill=gold, outline=dark)


def _draw_sword(draw: ImageDraw.ImageDraw, x: int, y: int) -> None:
    # Simple crossed-blade cue (blue-ish)
    draw.polygon(
        [(x + 10, y), (x + 14, y + 4), (x + 6, y + 18), (x + 2, y + 14)],
        fill=(90, 170, 230),
    )
    draw.rectangle([x + 5, y + 16, x + 11, y + 22], fill=(200, 200, 210))


def _draw_shield(draw: ImageDraw.ImageDraw, x: int, y: int) -> None:
    draw.polygon(
        [(x + 10, y), (x + 20, y + 4), (x + 18, y + 18), (x + 10, y + 22), (x + 2, y + 18), (x, y + 4)],
        fill=(150, 150, 160),
        outline=(90, 90, 100),
    )


def _diamond_bg(img: Image.Image, color: tuple[int, int, int]) -> None:
    draw = ImageDraw.Draw(img, "RGBA")
    w, h = img.size
    step = 28
    for y in range(-step, h + step, step):
        for x in range(-step, w + step, step):
            if ((x // step) + (y // step)) % 2 == 0:
                draw.polygon(
                    [(x, y + step // 2), (x + step // 2, y), (x + step, y + step // 2), (x + step // 2, y + step)],
                    fill=(*color, 28),
                )


def battle_log_png(
    *,
    player_name: str,
    attacks: Sequence[LogHit],
    defenses: Sequence[LogHit],
    slots: int,
    season_trophies: int | None = None,
    player_tag: str | None = None,
) -> bytes:
    """Clash-style Battle Log: Attacks | Defenses with fixed weekly slots."""
    slots = max(1, min(int(slots), 36))
    pad = 18
    gap = 14
    col_w = 430
    header_h = 78
    sub_h = 38
    row_h = 34
    row_gap = 5
    footer_h = 10
    w = pad * 2 + col_w * 2 + gap
    body_h = slots * (row_h + row_gap) - row_gap
    h = pad + header_h + 8 + sub_h + 10 + body_h + footer_h + pad

    img = Image.new("RGB", (w, h), (48, 28, 58))
    _diamond_bg(img, (70, 40, 90))
    draw = ImageDraw.Draw(img)

    # Outer frame
    draw.rounded_rectangle([6, 6, w - 7, h - 7], radius=16, outline=(120, 85, 55), width=4)
    draw.rounded_rectangle([12, 12, w - 13, h - 13], radius=12, outline=(90, 60, 40), width=2)

    name_font = _font(28)
    label_font = _font(15)
    col_font = _font(16)
    row_font = _font(15)
    small_font = _font(14)
    empty_font = _font(14)
    trophy_font = _font(26)

    # Purple header — player name large on top
    hx0, hy0 = pad, pad
    hx1, hy1 = w - pad, pad + header_h
    draw.rounded_rectangle([hx0, hy0, hx1, hy1], radius=8, fill=(92, 48, 130))

    atk_sum = sum(int(a.get("trophies") or 0) for a in attacks)
    def_sum = sum(int(d.get("trophies") or 0) for d in defenses)
    total = season_trophies if season_trophies is not None else (atk_sum + def_sum)
    total_txt = str(total)
    tw = draw.textlength(total_txt, font=trophy_font)

    # Trophy total (right)
    _draw_trophy(draw, int(hx1 - 28 - tw - 24), hy0 + 26, 22)
    draw.text((hx1 - 16 - tw, hy0 + 24), total_txt, fill=(255, 255, 255), font=trophy_font)

    # Name room: leave space for trophy cluster
    name_max_w = hx1 - hx0 - 16 - tw - 60
    display_name = _readable_name(player_name or "Player")
    # Truncate by measured width
    while len(display_name) > 1 and draw.textlength(display_name, font=name_font) > name_max_w:
        display_name = display_name[:-1]
    if display_name != _readable_name(player_name or "Player") and len(display_name) > 1:
        display_name = display_name[:-1] + "…"

    draw.text((hx0 + 16, hy0 + 10), display_name, fill=(255, 255, 255), font=name_font)
    sub = "CURRENT RANKED STANDINGS"
    if player_tag:
        sub = f"{sub}  ·  {player_tag}"
    draw.text((hx0 + 16, hy0 + 46), sub, fill=(210, 185, 230), font=label_font)

    # Column sub-headers
    ay = hy1 + 8
    left_x = pad
    right_x = pad + col_w + gap

    def _col_header(x: int, label: str, net: int, attack: bool) -> None:
        draw.rounded_rectangle([x, ay, x + col_w, ay + sub_h], radius=6, fill=(70, 40, 95))
        if attack:
            _draw_sword(draw, x + 10, ay + 8)
        else:
            _draw_shield(draw, x + 8, ay + 6)
        draw.text((x + 36, ay + 9), label, fill=(255, 255, 255), font=col_font)
        net_txt = f"+{net}" if net >= 0 else str(net)
        nw = draw.textlength(net_txt, font=col_font)
        _draw_trophy(draw, int(x + col_w - 22 - nw - 20), ay + 10, 16)
        draw.text((x + col_w - 14 - nw, ay + 9), net_txt, fill=(255, 240, 200), font=col_font)

    _col_header(left_x, "Attacks", atk_sum, True)
    _col_header(right_x, "Defenses", def_sum, False)

    def _row(x: int, y: int, hit: LogHit | None, empty_label: str) -> None:
        draw.rounded_rectangle([x, y, x + col_w, y + row_h], radius=5, fill=(198, 186, 176))
        if hit is None:
            draw.ellipse([x + 10, y + 9, x + 24, y + 23], fill=(70, 140, 210))
            draw.text((x + 14, y + 8), "i", fill=(255, 255, 255), font=small_font)
            draw.text((x + 32, y + 8), empty_label, fill=(70, 70, 80), font=empty_font)
            z = "+0"
            zw = draw.textlength(z, font=small_font)
            _draw_trophy(draw, int(x + col_w - 18 - zw - 18), y + 8, 14)
            draw.text((x + col_w - 12 - zw, y + 8), z, fill=(50, 50, 55), font=small_font)
            return

        name = (hit.get("name") or "Unknown")[:16]
        pct = int(hit.get("destruction") or 0)
        stars = int(hit.get("stars") or 0)
        cups = int(hit.get("trophies") or 0)
        draw.text((x + 10, y + 8), name, fill=(30, 30, 35), font=row_font)

        pct_txt = f"{pct}%"
        pw = draw.textlength(pct_txt, font=small_font)
        cups_txt = f"+{cups}" if cups >= 0 else str(cups)
        cw = draw.textlength(cups_txt, font=small_font)
        tx = x + col_w - 12 - cw
        _draw_trophy(draw, int(tx - 18), y + 8, 14)
        draw.text((tx, y + 8), cups_txt, fill=(40, 40, 45), font=small_font)

        star_x = int(tx - 18 - 52)
        for i in range(3):
            _draw_star(draw, star_x + i * 16, y + row_h // 2, 7, filled=i < stars)

        draw.text((star_x - 8 - pw, y + 8), pct_txt, fill=(40, 40, 45), font=small_font)

    start_y = ay + sub_h + 10
    atk_list = list(attacks)[:slots]
    def_list = list(defenses)[:slots]
    for i in range(slots):
        y = start_y + i * (row_h + row_gap)
        a = atk_list[i] if i < len(atk_list) else None
        d = def_list[i] if i < len(def_list) else None
        _row(left_x, y, a, "No attack performed.")
        _row(right_x, y, d, "No defense received.")

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
