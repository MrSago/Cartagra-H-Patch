#!/usr/bin/env python3
"""
Decoder for LucaSystem CZ1/CZ3/CZ4 images (Cartagra REBIRTH FHD), after
Cartagra_FHD_CHS/image/czximage/cz2image.cpp.

Header (little-endian):
  0x00 "CZ4\0" | u32 header_length | u16 width | u16 height | u16 bits (32)
  u16 ?(4) | u16 offset_x | u16 offset_y | u16 width | u16 height (again)
  u16 canvas_width | u16 canvas_height | ...
Variants ("k" images) are partial overlays placed at (offset_x, offset_y)
on their parent image (PAK section 0x01).

Data: u32 block count, block_count x (u32 code count, u32 raw size), then the
16-bit LZW codes of every block (dictionary starts with the 256 bytes). The
decompressed stream is RGB (CZ4) or RGBA (CZ3) rows followed (CZ4) by an
alpha plane; rows are delta-coded against the previous row except at the
start of each of 3 horizontal bands.

Usage:
  python -m cartagra_patch.cztool png <pak> <entry> <out.png> [--composite]
"""

import struct
import sys
import zlib


def header(data):
    magic = data[:4]
    hl, w, h, bits = struct.unpack_from("<IHHH", data, 4)
    ox, oy = struct.unpack_from("<HH", data, 0x10)
    cw, ch = struct.unpack_from("<HH", data, 0x18)
    return dict(magic=magic, header_length=hl, width=w, height=h, bits=bits, x=ox, y=oy, canvas=(cw, ch))


def _lzw_blocks(data, p):
    count = struct.unpack_from("<I", data, p)[0]
    p += 4
    sizes = []
    for _ in range(count):
        n, raw = struct.unpack_from("<II", data, p)
        sizes.append((n, raw))
        p += 8
    out = bytearray()
    for n, raw in sizes:
        codes = struct.unpack_from("<%dH" % n, data, p)
        p += 2 * n
        # as in cz2image.cpp: w starts as "\0" and every code (the first too) adds an entry
        table = [bytes([i]) for i in range(256)]
        w = b"\x00"
        for k in codes:
            if k < len(table):
                entry = table[k]
            elif k == len(table):
                entry = w + w[:1]
            else:
                raise ValueError("bad LZW code")
            out += entry
            table.append(w + entry[:1])
            w = entry
    return bytes(out)


def _undelta(plane, width, height, bpp):
    stride = width * bpp
    band = -(-height // 3)
    rows = bytearray(plane[: stride * height])
    for y in range(height):
        if y % band:
            cur = memoryview(rows)[y * stride : (y + 1) * stride]
            prev = rows[(y - 1) * stride : y * stride]
            cur[:] = bytes((a + b) & 0xFF for a, b in zip(cur, prev))
    return rows


def _decode_cz1(data, hd):
    """CZ1: LZW-compressed RGBA (32 bit) or 8-bit indices into a 256 x RGBA palette."""
    w, h, p = hd["width"], hd["height"], hd["header_length"]
    if hd["bits"] == 32:
        raw = _lzw_blocks(data, p)
        if len(raw) == 4 * w * h:
            return raw
    palette = [data[p + 4 * i : p + 4 * i + 4] for i in range(256)]
    idx = _lzw_blocks(data, p + 1024)
    if len(idx) < w * h:
        raise ValueError("CZ1: short index data")
    return b"".join(palette[i] for i in idx[: w * h])


def decode(data):
    """Return (header dict, RGBA bytes of width x height)."""
    hd = header(data)
    w, h = hd["width"], hd["height"]
    if hd["magic"] == b"CZ1\x00":
        return hd, _decode_cz1(data, hd)
    if hd["magic"] not in (b"CZ4\x00", b"CZ3\x00"):
        raise ValueError(f"unsupported {hd['magic']!r}")
    raw = _lzw_blocks(data, hd["header_length"])
    if hd["magic"] == b"CZ3\x00":
        return hd, bytes(_undelta(raw, w, h, 4))
    rgb = _undelta(raw, w, h, 3)
    alpha = _undelta(raw[3 * w * h :], w, h, 1)
    rgba = bytearray(4 * w * h)
    rgba[0::4], rgba[1::4], rgba[2::4] = rgb[0::3], rgb[1::3], rgb[2::3]
    rgba[3::4] = alpha
    return hd, bytes(rgba)


def composite(base_rgba, base_w, over_rgba, over_w, over_h, x, y):
    """Alpha-blend an overlay onto a copy of the base image."""
    out = bytearray(base_rgba)
    for row in range(over_h):
        for col in range(over_w):
            s = 4 * (row * over_w + col)
            a = over_rgba[s + 3]
            if not a:
                continue
            d = 4 * ((y + row) * base_w + x + col)
            for c in range(3):
                out[d + c] = (over_rgba[s + c] * a + out[d + c] * (255 - a)) // 255
            out[d + 3] = max(out[d + 3], a)
    return bytes(out)


def write_png(path, rgba, w, h):
    raw = b"".join(b"\x00" + rgba[y * 4 * w : (y + 1) * 4 * w] for y in range(h))

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)

    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


def main():
    if len(sys.argv) < 5 or sys.argv[1] != "png":
        print(__doc__)
        sys.exit(1)
    from .lucapak import LucaPak, SEC_PARENT

    pak = LucaPak.read(sys.argv[2])
    by = {e.name: e for e in pak.entries}
    e = by[sys.argv[3]]
    hd, rgba = decode(e.data)
    w, h = hd["width"], hd["height"]
    parent = int.from_bytes(e.sections.get(SEC_PARENT, b""), "little")
    if "--composite" in sys.argv and parent:
        ph, prgba = decode(by[pak.name_of(parent)].data)
        rgba = composite(prgba, ph["width"], rgba, w, h, hd["x"], hd["y"])
        w, h = ph["width"], ph["height"]
    write_png(sys.argv[4], rgba, w, h)
    print(f"{sys.argv[3]}: {hd['magic'][:3].decode()} {hd['width']}x{hd['height']} at ({hd['x']},{hd['y']}) -> {sys.argv[4]}")


if __name__ == "__main__":
    main()
