"""
Add letters to the bitmap fonts of the Steam release.

The game draws its text with two font sets in files/font_win32_1920/: FONT0 (sizes 16..44, the full
Japanese set; the Russian release added Cyrillic to it) and FONT1 (sizes 35, 37, 52, 56, 72, Latin
and kana only). Some interface labels use FONT1: the bottom bar of the options, save and load screens
(Defaults, Close, ...), the slider labels and the save date. Russian text there is drawn as blanks.
`add_glyphs` copies the letters a language needs from FONT0's largest size into every FONT1 size and
face, scaled to that size. `redraw_numero` replaces FONT0's numero sign, which has the Japanese
shape ("No."), with the Cyrillic one (the save and load screens show the slot number with it).

Files (one set per font group n):
  FONTn__INFO.PAK   "info<size>" for every size, shared by all faces:
      u16 size, u16 line height, u16 cells per row (100), u16 glyph count
      glyph count x (u8 left, u8 width, u8 ?): the drawn part of each cell (third byte: 0 for
          digits and punctuation, about size / 9 for letters)
      u16[65536] character -> glyph (0 = none)
      u16[65536] character -> width << 8 | left, for the characters with a width of their own
  FONTn_<FACE>.PAK  a CZ2 sheet per size and face ("明朝37"): glyph i in the cell at column i % 100,
      row i // 100; cells are size + 1 px square. The faces are GOTHIC1/2/3, MINCHO and MODERN.
"""

import math
import os
import struct

from . import cztool
from .lucapak import SEC_HASH, LucaPak, xxh64

FONT_DIR = "font_win32_1920"
FACES = ("GOTHIC1", "GOTHIC2", "GOTHIC3", "MINCHO", "MODERN")
SOURCE, TARGET = "FONT0", "FONT1"


def input_files():
    """The font archives add_glyphs reads, relative to the input set's files/ folder."""
    return [f"{FONT_DIR}/{g}__INFO.PAK" for g in (SOURCE, TARGET)] + [
        f"{FONT_DIR}/{g}_{face}.PAK" for g in (SOURCE, TARGET) for face in FACES
    ]


class FontInfo:
    def __init__(self, data):
        self.size, self.line, self.per_row, count = struct.unpack_from("<4H", data, 0)
        self.cells = [tuple(data[8 + 3 * i : 11 + 3 * i]) for i in range(count)]
        p = 8 + 3 * count
        if len(data) != p + 4 * 65536:
            raise ValueError("font info: unexpected size")
        self.glyph = list(struct.unpack_from("<65536H", data, p))
        self.width = list(struct.unpack_from("<65536H", data, p + 131072))

    def build(self):
        return (
            struct.pack("<4H", self.size, self.line, self.per_row, len(self.cells))
            + b"".join(bytes(c) for c in self.cells)
            + struct.pack("<65536H", *self.glyph)
            + struct.pack("<65536H", *self.width)
        )


def _cubic(x):
    x = abs(x)
    if x < 1:
        return (1.5 * x - 2.5) * x * x + 1
    return ((-0.5 * x + 2.5) * x - 4) * x + 2 if x < 2 else 0.0


def _weights(n_in, n_out, scale):
    """Bicubic weights for resampling n_in pixels to n_out (antialiased when shrinking); outside = 0."""
    filt = max(1.0, 1.0 / scale)
    out = []
    for i in range(n_out):
        center = (i + 0.5) / scale
        js = range(math.floor(center - 2 * filt), math.ceil(center + 2 * filt) + 1)
        ws = [(j, _cubic((j + 0.5 - center) / filt)) for j in js]
        total = sum(w for _, w in ws)
        out.append([(j, w / total) for j, w in ws if 0 <= j < n_in and w])
    return out


_WEIGHTS = {}


def resample(pixels, n_in, n_out, scale):
    """Scale a square n_in x n_in grey image (list of floats) by `scale` into n_out x n_out."""
    key = (n_in, n_out, scale)
    if key not in _WEIGHTS:
        _WEIGHTS[key] = _weights(n_in, n_out, scale)
    wts = _WEIGHTS[key]
    zero = [0.0] * n_out
    rows = []
    for y in range(n_in):
        line = pixels[y * n_in : (y + 1) * n_in]
        rows.append(
            [sum(line[j] * w for j, w in wt) for wt in wts] if any(line) else zero
        )
    out = []
    for wt in wts:
        used = [(rows[j], w) for j, w in wt if rows[j] is not zero]
        out += (
            [min(255.0, max(0.0, sum(r[x] * w for r, w in used))) for x in range(n_out)]
            if used
            else zero
        )
    return out


def _cell(idx, width, cell, i):
    x0, y0 = (i % 100) * cell, (i // 100) * cell
    return [idx[(y0 + y) * width + x0 + x] for y in range(cell) for x in range(cell)]


def _sheets(pak):
    """{(face prefix, size): entry} of a font sheet archive."""
    out = {}
    for e in pak.entries:
        prefix = e.name.rstrip("0123456789")
        out[(prefix, int(e.name[len(prefix) :]))] = e
    return out


def _set(entry, data):
    entry.data = data
    entry.pad = None
    entry.sections[SEC_HASH] = xxh64(data)


def add_glyphs(files_dir, out_dir, chars, log=print):
    """
    Copy `chars` from FONT0 into every FONT1 size and face (those FONT1 lacks), writing FONT1__INFO.PAK
    and FONT1_<face>.PAK to out_dir/font_win32_1920/. Returns the number of characters added.
    """
    src_dir, dst_dir = os.path.join(files_dir, FONT_DIR), os.path.join(
        out_dir, FONT_DIR
    )
    src_infos = {
        int(e.name[4:]): (e.name, FontInfo(e.data))
        for e in LucaPak.read(os.path.join(src_dir, f"{SOURCE}__INFO.PAK")).entries
    }
    src_size = max(src_infos)
    src = src_infos[src_size][1]
    missing = [c for c in chars if not src.glyph[ord(c)]]
    if missing:
        raise ValueError(f"{SOURCE} has no glyph for {''.join(missing)!r}")
    info_pak = LucaPak.read(os.path.join(src_dir, f"{TARGET}__INFO.PAK"))
    infos = {e: FontInfo(e.data) for e in info_pak.entries}
    add = {
        e: [c for c in dict.fromkeys(chars) if not inf.glyph[ord(c)]]
        for e, inf in infos.items()
    }
    if not any(add.values()):
        return 0
    src_letter = src.cells[src.glyph[ord("A")]][2]
    first = {e: len(inf.cells) for e, inf in infos.items()}
    for e, inf in infos.items():
        scale = inf.size / src_size
        letter = inf.cells[inf.glyph[ord("A")]][2]
        for k, c in enumerate(add[e]):
            left, width, extra = src.cells[src.glyph[ord(c)]]
            left, width = round(left * scale), round(width * scale)
            extra = letter if extra == src_letter else round(extra * scale)
            inf.glyph[ord(c)] = first[e] + k
            inf.cells.append((left, min(width, inf.size + 1 - left), extra))
            if src.width[ord(c)]:
                inf.width[ord(c)] = width << 8 | left
        _set(e, inf.build())
    os.makedirs(dst_dir, exist_ok=True)
    info_pak.write(os.path.join(dst_dir, f"{TARGET}__INFO.PAK"))
    sizes = {inf.size: (e, inf) for e, inf in infos.items()}
    rows_needed = max(src.glyph[ord(c)] for c in chars) // src.per_row + 1
    src_cell = src_size + 1
    for face in FACES:
        src_sheet = _sheets(LucaPak.read(os.path.join(src_dir, f"{SOURCE}_{face}.PAK")))
        path = os.path.join(src_dir, f"{TARGET}_{face}.PAK")
        pak = LucaPak.read(path)
        prefix = next(p for p, s in src_sheet if s == src_size)
        _, palette, src_idx = cztool.decode_cz2(
            src_sheet[(prefix, src_size)].data, rows=rows_needed * src_cell
        )
        src_w = cztool.header(src_sheet[(prefix, src_size)].data)["width"]
        alpha = [palette[4 * i + 3] for i in range(256)]
        to_index = [
            min(range(256), key=lambda i: (abs(alpha[i] - a), i)) for a in range(256)
        ]
        glyphs = {
            c: [
                float(alpha[i])
                for i in _cell(src_idx, src_w, src_cell, src.glyph[ord(c)])
            ]
            for c in chars
        }
        for (pfx, size), entry in _sheets(pak).items():
            e, inf = sizes[size]
            if not add[e]:
                continue
            hd, pal, idx = cztool.decode_cz2(entry.data)
            w, cell = hd["width"], size + 1
            extra_rows = hd["height"] - (-(-first[e] // 100)) * cell
            h = (-(-len(inf.cells) // 100)) * cell + extra_rows
            out = bytearray(idx) + bytes(w * (h - hd["height"]))
            for k, c in enumerate(add[e]):
                px = resample(glyphs[c], src_cell, cell, size / src_size)
                i = first[e] + k
                x0, y0 = (i % 100) * cell, (i // 100) * cell
                for y in range(cell):
                    out[(y0 + y) * w + x0 : (y0 + y) * w + x0 + cell] = bytes(
                        to_index[round(v)] for v in px[y * cell : (y + 1) * cell]
                    )
            _set(entry, cztool.encode_cz2(entry.data, pal, w, h, bytes(out)))
        pak.write(os.path.join(dst_dir, f"{TARGET}_{face}.PAK"))
    added = max(len(a) for a in add.values())
    log(
        f"  {FONT_DIR}/{TARGET}: {added} letters added to {len(infos)} sizes x {len(FACES)} faces "
        f"(scaled from {SOURCE} size {src_size})"
    )
    return added


def _ink(px, cell):
    """(x0, x1, y0, y1) of the visible pixels of a cell."""
    xs = [x for x in range(cell) if any(px[y * cell + x] > 40 for y in range(cell))]
    ys = [y for y in range(cell) if any(px[y * cell + x] > 40 for x in range(cell))]
    return xs[0], xs[-1], ys[0], ys[-1]


def compose_numero(n_px, o_px, size):
    """
    A Cyrillic-style numero sign from a font's N and o cells (grey levels, (size + 1)² floats):
    N (narrowed when needed), a raised o of half the cap height and a bar under it.
    Returns (cell pixels, advance width).
    """
    cell = size + 1
    nx0, nx1, ny0, ny1 = _ink(n_px, cell)
    _, _, oy0, oy1 = _ink(o_px, cell)
    cap = ny1 - ny0 + 1
    small = resample(o_px, cell, cell, 0.5 * cap / (oy1 - oy0 + 1))
    sx0, sx1, sy0, sy1 = _ink(small, cell)
    gap = max(1, round(size * 0.05))
    k = min(1.0, (cell - 2 - gap - (sx1 - sx0 + 1)) / (nx1 + 1))
    out = []
    wts = _weights(cell, cell, k)
    for y in range(cell):
        line = n_px[y * cell : (y + 1) * cell]
        out += [min(255.0, max(0.0, sum(line[j] * w for j, w in wt))) for wt in wts]
    dx, dy = round((nx1 + 1) * k) + gap - sx0, ny0 - sy0
    for y in range(sy0, sy1 + 1):
        for x in range(sx0, sx1 + 1):
            p = (y + dy) * cell + x + dx
            out[p] = max(out[p], small[y * cell + x])
    bar = ny0 + sy1 - sy0 + 1 + max(1, round(cap * 0.1))
    for y in range(bar, bar + max(1, round(cap * 0.07))):
        for x in range(sx0 + dx, sx1 + dx + 1):
            out[y * cell + x] = 255.0
    return out, min(cell, sx1 + dx + 1 + max(1, round(size * 0.06)))


def redraw_numero(files_dir, out_dir, log=print):
    """
    Replace FONT0's numero sign (drawn the Japanese way, as "No.") with a Cyrillic-style one
    (compose_numero) in every size and face, writing FONT0__INFO.PAK and FONT0_<face>.PAK to
    out_dir/font_win32_1920/.
    """
    src_dir, dst_dir = os.path.join(files_dir, FONT_DIR), os.path.join(
        out_dir, FONT_DIR
    )
    info_pak = LucaPak.read(os.path.join(src_dir, f"{SOURCE}__INFO.PAK"))
    infos = {e: FontInfo(e.data) for e in info_pak.entries}
    sizes = {inf.size: (e, inf) for e, inf in infos.items()}
    numero = ord("№")
    if any(not inf.glyph[numero] for inf in infos.values()):
        raise ValueError(f"{SOURCE} has no glyph for '№'")
    advance = {}
    os.makedirs(dst_dir, exist_ok=True)
    for face in FACES:
        pak = LucaPak.read(os.path.join(src_dir, f"{SOURCE}_{face}.PAK"))
        for (pfx, size), entry in _sheets(pak).items():
            e, inf = sizes[size]
            hd, pal, idx = cztool.decode_cz2(entry.data)
            w, cell = hd["width"], size + 1
            alpha = [pal[4 * i + 3] for i in range(256)]
            to_index = [
                min(range(256), key=lambda i: (abs(alpha[i] - a), i))
                for a in range(256)
            ]
            glyph = lambda ch: [
                float(alpha[i]) for i in _cell(idx, w, cell, inf.glyph[ord(ch)])
            ]
            px, adv = compose_numero(glyph("N"), glyph("o"), size)
            advance[e] = max(advance.get(e, 0), adv)
            out = bytearray(idx)
            i = inf.glyph[numero]
            x0, y0 = (i % 100) * cell, (i // 100) * cell
            for y in range(cell):
                out[(y0 + y) * w + x0 : (y0 + y) * w + x0 + cell] = bytes(
                    to_index[round(v)] for v in px[y * cell : (y + 1) * cell]
                )
            _set(entry, cztool.encode_cz2(entry.data, pal, w, hd["height"], bytes(out)))
        pak.write(os.path.join(dst_dir, f"{SOURCE}_{face}.PAK"))
    for e, inf in infos.items():
        inf.cells[inf.glyph[numero]] = (
            0,
            advance[e],
            inf.cells[inf.glyph[ord("N")]][2],
        )
        inf.width[numero] = advance[e] << 8
        _set(e, inf.build())
    info_pak.write(os.path.join(dst_dir, f"{SOURCE}__INFO.PAK"))
    log(
        f"  {FONT_DIR}/{SOURCE}: '№' redrawn in {len(infos)} sizes x {len(FACES)} faces"
    )
