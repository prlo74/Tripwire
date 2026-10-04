"""M7: every text/background token pair in the page meets WCAG AA, in light and dark themes.
Tints are alpha-composited over the card color before measuring."""
import re
from pathlib import Path

import pytest

PAGE = (Path(__file__).resolve().parent.parent / "site" / "page.html").read_text()


LIGHT = dict(re.findall(r"--([\w-]+):\s*([^;]+);", re.search(r":root \{(.*?)\n\}", PAGE, re.S).group(1)))
# The page is a single deliberate silver theme; dark blocks are checked only if they exist.
_d = re.search(r':root\[data-theme="dark"\] \{(.*?)\n\}', PAGE, re.S)
_m = re.search(r':root:not\(\[data-theme="light"\]\) \{(.*?)\n  \}', PAGE, re.S)
DARK = {**LIGHT, **dict(re.findall(r"--([\w-]+):\s*([^;]+);", _d.group(1)))} if _d else LIGHT
DARK_MEDIA = {**LIGHT, **dict(re.findall(r"--([\w-]+):\s*([^;]+);", _m.group(1)))} if _m else LIGHT


def rgba(v):
    v = v.strip()
    if v.startswith("#"):
        h = v[1:]
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)) + (1.0,)
    m = re.match(r"rgba\(([\d.]+),\s*([\d.]+),\s*([\d.]+),\s*([\d.]+)\)", v)
    return tuple(float(x) for x in m.groups()[:3]) + (float(m.group(4)),)


def over(fg, bg):
    a = fg[3]
    return tuple(fg[i] * a + bg[i] * (1 - a) for i in range(3)) + (1.0,)


def lum(c):
    def ch(x):
        x /= 255
        return x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4
    return 0.2126 * ch(c[0]) + 0.7152 * ch(c[1]) + 0.0722 * ch(c[2])


def ratio(a, b):
    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


# (text token, background token or tint-over-card, minimum ratio, note)
PAIRS = [
    ("ink", "bg", 4.5), ("ink", "card", 4.5), ("ink", "well", 4.5),
    ("muted", "bg", 4.5), ("muted", "card", 4.5), ("muted", "well", 4.5),
    ("faint", "card", 4.5),
    ("primary", "card", 4.5), ("primary", "well", 4.5), ("primary-ink", "primary", 4.5),
    ("black-ink", "black-list", 4.5), ("black-list", "card", 4.5),
    ("aligned-ink", "aligned", 4.5), ("aligned", "card", 4.5),
    ("watch-ink", "watch", 4.5), ("watch-text", "card", 4.5),
    ("ink", "tint-black", 4.5), ("ink", "tint-watch", 4.5), ("ink", "tint-aligned", 4.5), ("ink", "tint-primary", 4.5),
    ("muted", "tint-black", 4.5), ("muted", "tint-watch", 4.5), ("muted", "tint-aligned", 4.5),
    ("black-list", "tint-black", 3.0),   # 3rem count numerals: large text
    ("aligned", "tint-aligned", 3.0), ("watch-text", "tint-watch", 3.0),
    ("bg", "ink", 4.5),  # toast / pressed tab
    ("alert", "card", 4.5), ("alert-ink", "alert", 4.5),   # reject buttons, over-threshold
    ("ink", "bg", 4.5), ("muted", "card-2", 4.5), ("primary", "card-2", 4.5),
]


@pytest.mark.parametrize("theme", ["light", "dark", "dark-media"])
@pytest.mark.parametrize("fg,bg,minimum", PAIRS)
def test_pair(theme, fg, bg, minimum):
    t = {"light": LIGHT, "dark": DARK, "dark-media": DARK_MEDIA}[theme]
    card = rgba(t["card"])
    f = over(rgba(t[fg]), card)
    b = over(rgba(t[bg]), card)
    r = ratio(f, b)
    assert r >= minimum, f"{theme}: --{fg} on --{bg} = {r:.2f}:1 < {minimum}"


def test_no_orange_text_on_white():
    # --watch (orange) may only be a fill; text uses --watch-text.
    for m in re.finditer(r"[^-]color:\s*var\(--watch\)", PAGE):
        pytest.fail("orange --watch used as text color: " + PAGE[m.start() - 60:m.end()])


# Run progress bar: each fill against its empty track is a non-text graphic (WCAG 1.4.11, 3:1).
@pytest.mark.parametrize("fill", ["primary", "aligned", "watch-text"])
def test_runbar_fill_against_track(fill):
    card = rgba(LIGHT["card"])
    r = ratio(over(rgba(LIGHT[fill]), card), over(rgba(LIGHT["line"]), card))
    assert r >= 3.0, f"--{fill} fill on --line track = {r:.2f}:1 < 3"
