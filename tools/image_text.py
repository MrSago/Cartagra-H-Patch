#!/usr/bin/env python3
"""
Render translated text into the interface pictures.

  python tools/image_text.py --language ru [--only SYSCG/title_menu1 ...] [--compare DIR]

Reads languages/<lang>/images_text.json and the exported originals (languages/_original_steam/en/images/,
made by `build.py --language <lang> --export-images`) and writes languages/<lang>/images/<picture>.png.
The build then puts the pictures that differ from the originals into the patch.

For each text item the original English text is rendered with the chosen font and fitted to the
original lettering (size, width, position). The look of the original (fill, outline, glow, shadow) is
then measured as a function of the distance to the letter edges and applied to the translated text at
the same size and baseline. The English text is erased first: the box is cleared on transparent
sheets ("bg": "clear") or the background is filled in from its surroundings ("bg": "inpaint").

Needs Pillow, numpy, scipy and opencv-python-headless (only this tool; the build does not use them),
and the fonts named in the json (searched in --fonts folders, then in the system font folder).

images_text.json:
  fonts     {name: {"file": "EBGaramond.ttf", "weight": 400}}
  images    list of pictures; each has "image" (path below images/ without .png) and either "items"
            (each with "box" [x0, y0, x1, y1], "en", "ru") or "grid" + "words". Any other key is a
            default for the items, and an item may override it:
    font      font name
    polarity  "dark" or "light": whether the letters are darker or lighter than what is around them
    thr       0..1, threshold of the letter detection (default 0.5)
    bg        "clear" or "inpaint" (default "clear")
    radius    how far the effect reaches beyond the letters, for "inpaint" (default 8)
    erase_thr lower threshold of the letter detection for what "inpaint" erases (darker letter parts)
    align     "left", "center" or "right" (default "left"); keeps that edge of the English text
    limit     [x0, x1]: where the translated letters may go (default: the box less the effect)
    uniform   true: all texts of the picture and its copy_to pictures get the same size (that of the
              one shrunk most) and each word the same squeeze in all of them; texts with a "group"
              key share the size only within their group
    same_fit  with "uniform": every text of a group starts from one size, horizontal scale and baseline,
              the medians of the English texts' fits (one text's fit can be off: Q's tail makes "Q.SAVE"
              look taller, so it was fitted smaller and stretched)
    max_sx    largest horizontal scale for "same_fit" (1.0: never wider than the font)
    keep_extent  true: the translated text (with its effect) stays within the columns the original
              covered in the box (for buttons the engine cuts to the original width)
    pad       least space between the translated letters and the sides of the box, px
    tighten   how much closer the letters may move, per letter gap and as a fraction of the size,
              before a text that is too wide is squeezed (default 0)
    min_sx    least horizontal scale relative to the fitted one before the size is reduced (0.85)
    size, sx  fixed size (px) and horizontal scale instead of fitting them to the English text
    fit       "height" (default): size from the height of the English letters, horizontal scale from
              their width; "width": size from the width, no scaling (for long lines of mixed case)
    size_scale  factor on the fitted size; with "fit": "width" letter spacing makes up the width
    fit_box   part of the box with the English letters, if the box holds other things too
    fit_from  [dx, dy]: fit the size and position on the same text that far away (another state of
              the button whose letters are easier to find)
    rotate    90 or -90: the text runs upwards (90) or downwards (-90); the box is turned back by
              that angle before rendering, so "left" is the start of the text
    dx, dy    shift of the translated text in px
    max_w     largest width of the translated letters in px
    fill      how the inside of the letters is coloured; by default by the distance to the edge only.
              "rows": measured row by row (a vertical gradient); "texture": the inside of the
              original letters spread over the box (a texture; "clear" background only)
  grid      {"x": [...], "y": [...], "box": [dx0, dy0, dx1, dy1]}: a cell at every x, y; the box is
            relative to the cell. An x or y may be {"at": x, overrides} to set keys for that column or row
            ("box_w"/"box_h" change the width/height of its boxes)
  words     [[en, ru] or {"en": ..., "ru": ..., overrides}], one per row ("by": "row", default) or per
            column ("by": "col"); every cell of that row or column gets the word
  menu      with "uniform" and "keep_extent", for a horizontal menu whose buttons the engine cuts to the
            original items' widths and lines up: {"rows": {group: [English words in screen order]},
            "gap": px between buttons, "width": screen width, "scale": {group: factor}}. Each word is
            placed in its button (the same place in every state) so that the gaps between the words are as
            even as the buttons allow; "scale" makes a group's words smaller to leave room for that
  copy_to   other pictures with the same layout that get the same items; an element may be
            {"image": ..., overrides} to change keys (such as "grid") for that picture
"""

import argparse
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SS = 4                                   # supersampling of the letter masks
BINS = np.arange(-30, 60.01, 0.25)       # signed distance to the letter edge, px (negative inside)
SYSTEM_FONTS = [os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"),
                "/usr/share/fonts", "/Library/Fonts", os.path.expanduser("~/.fonts")]


# ---------------------------------------------------------------- text masks

class Fonts:
    def __init__(self, spec, dirs):
        self.spec, self.dirs, self.cache = spec, dirs, {}

    def path(self, name):
        file = self.spec[name]["file"]
        for d in self.dirs:
            for root, _, files in os.walk(d):
                if file in files:
                    return os.path.join(root, file)
        raise SystemExit(f"font {file} not found in {', '.join(self.dirs)} (use --fonts)")

    def get(self, name, px):
        key = (name, round(px * 4))
        if key not in self.cache:
            f = ImageFont.truetype(self.path(name), max(1, round(px)))
            if "weight" in self.spec[name]:
                f.set_variation_by_axes([self.spec[name]["weight"]])
            self.cache[key] = f
        return self.cache[key]


def text_mask(fonts, font, text, size, sx, tracking=0.0):
    """Coverage of the text at SS x resolution and the position of its origin (left end of the baseline).
    tracking: extra space after each character, px."""
    f = fonts.get(font, size * SS)
    l, t, r, b = f.getbbox(text, anchor="ls")
    extra = tracking * SS * max(0, len(text) - 1)
    pad = 2 * SS + int(abs(extra)) * (extra < 0)
    w, h = int(r - l + 2 * pad + max(0, extra)), b - t + 2 * pad
    im = Image.new("L", (w, h))
    draw = ImageDraw.Draw(im)
    if tracking:
        for i, ch in enumerate(text):
            draw.text((pad - l + f.getlength(text[:i]) + i * tracking * SS, pad - t), ch, font=f, fill=255, anchor="ls")
    else:
        draw.text((pad - l, pad - t), text, font=f, fill=255, anchor="ls")
    ox, oy = pad - l, pad - t
    if sx != 1.0:
        nw = max(1, round(w * sx))
        im = im.resize((nw, h), Image.LANCZOS)
        ox *= nw / w
    return np.asarray(im, np.float32) / 255, (ox, oy)


def ink_box(cov):
    ys, xs = np.nonzero(cov > 0.5)
    return xs.min(), ys.min(), xs.max() + 1, ys.max() + 1


def place(cov, origin, H, W, x, y):
    """SS canvas of H x W px with the mask's origin at pixel position (x, y)."""
    can = np.zeros((H * SS, W * SS), np.float32)
    ox, oy = round(x * SS - origin[0]), round(y * SS - origin[1])
    h, w = cov.shape
    y0, y1, x0, x1 = max(0, oy), min(H * SS, oy + h), max(0, ox), min(W * SS, ox + w)
    if y0 < y1 and x0 < x1:
        can[y0:y1, x0:x1] = cov[y0 - oy:y1 - oy, x0 - ox:x1 - ox]
    return can


def down(a):
    h, w = a.shape[0] // SS, a.shape[1] // SS
    return a[:h * SS, :w * SS].reshape(h, SS, w, SS, *a.shape[2:]).mean((1, 3))


def signed_distance(can):
    inside = can > 0.5
    return (ndimage.distance_transform_edt(~inside) - ndimage.distance_transform_edt(inside)) / SS


# ---------------------------------------------------------------- fitting and effect

def letter_feature(img, polarity):
    lum = img[..., :3] @ np.array([0.299, 0.587, 0.114])
    return img[..., 3] * (lum if polarity == "light" else 1 - lum)


def fit(fonts, it, img):
    """Size, horizontal scale, tracking and origin (in box pixels) of the English text in the box."""
    x0, y0, x1, y1 = it["fit_box"]
    feat = letter_feature(img, it.get("polarity", "dark"))
    sub = feat[y0:y1, x0:x1] > it.get("thr", 0.5)
    if not sub.any():
        raise ValueError(f"{it['where']}: no letters found (check polarity/thr/box)")
    ys, xs = np.nonzero(sub)
    gx0, gy0, gx1, gy1 = xs.min() + x0, ys.min() + y0, xs.max() + 1 + x0, ys.max() + 1 + y0
    font = it["font"]
    by_width = it.get("fit") == "width"
    if "size" in it:
        size = it["size"]
    else:
        cov, _ = text_mask(fonts, font, it["en"], 100, 1.0)
        bx0, by0, bx1, by1 = ink_box(cov)
        size = 100 * ((gx1 - gx0) / (bx1 - bx0) if by_width else (gy1 - gy0) / (by1 - by0)) * SS
        size *= it.get("size_scale", 1.0)
    cov, org = text_mask(fonts, font, it["en"], size, 1.0)
    bx0, by0, bx1, by1 = ink_box(cov)
    tracking = 0.0
    if by_width:
        sx = it.get("sx", 1.0)
        # a smaller size (size_scale) is brought to the width of the original with letter spacing
        tracking = ((gx1 - gx0) - (bx1 - bx0) / SS) / max(1, len(it["en"]) - 1)
    else:
        sx = it.get("sx", (gx1 - gx0) * SS / (bx1 - bx0))
    cov, org = text_mask(fonts, font, it["en"], size, sx, tracking)
    bx0, by0, bx1, by1 = ink_box(cov)
    # origin so that the ink boxes coincide (their middles, when fitted by width), then refine by
    # correlation with the letter feature
    x = gx0 + (org[0] - bx0) / SS
    y = gy0 + (org[1] - by0) / SS
    if by_width:
        y += ((gy1 - gy0) - (by1 - by0) / SS) / 2
    H, W = img.shape[:2]
    best = None
    for dy in np.arange(-4, 4.01, 0.25) if by_width else np.arange(-1.5, 1.51, 0.25):
        for dx in np.arange(-1.5, 1.51, 0.25):
            m = down(place(cov, org, H, W, x + dx, y + dy))
            score = (m * feat).sum() / np.sqrt((m * m).sum() + 1e-9)
            if best is None or score > best[0]:
                best = (score, x + dx, y + dy)
    return size, sx, tracking, best[1], best[2]


def original_letters(it, img, thr=None):
    """The original letters as an SS mask (the letter feature above thr, inside fit_box)."""
    H, W = img.shape[:2]
    feat = letter_feature(img, it.get("polarity", "dark")).astype(np.float32)
    up = np.asarray(Image.fromarray(feat, "F").resize((W * SS, H * SS), Image.BILINEAR))
    keep = np.zeros_like(up, bool)
    x0, y0, x1, y1 = it["fit_box"]
    keep[y0 * SS:y1 * SS, x0 * SS:x1 * SS] = True
    return ((up > (it.get("thr", 0.5) if thr is None else thr)) & keep).astype(np.float32)


def background(it, img, sd_en):
    """The box without the English text (premultiplied RGBA)."""
    if it.get("bg", "clear") == "clear":
        return np.zeros_like(img)
    import cv2
    mask = (sd_en < it.get("radius", 8)).astype(np.uint8)
    pm = img.copy()
    pm[..., :3] *= pm[..., 3:4]
    out = np.empty_like(pm)
    rgb = (pm[..., :3] * 255).round().astype(np.uint8)
    out[..., :3] = cv2.inpaint(rgb, mask, 5, cv2.INPAINT_TELEA) / 255
    a = (pm[..., 3] * 255).round().astype(np.uint8)
    out[..., 3] = cv2.inpaint(a, mask, 5, cv2.INPAINT_TELEA) / 255
    # where something opaque meets transparency the fill would be a half-transparent haze: inside the
    # filled area each pixel becomes one or the other
    alpha = out[..., 3]
    t = np.clip((alpha - 0.3) / 0.4, 0, 1)
    sharp = t * t * (3 - 2 * t)
    hole = mask.astype(bool)
    scale = np.where(alpha > 1e-6, sharp / np.maximum(alpha, 1e-6), 0)
    out[hole] *= scale[hole, None]
    return out


def learn(img, bg, sd):
    """Layer (premultiplied colour, alpha) per distance bin so that img = layer over bg."""
    pm = img.copy()
    pm[..., :3] *= pm[..., 3:4]
    idx = np.clip(np.searchsorted(BINS, sd), 0, len(BINS) - 1).ravel()
    O, B = pm.reshape(-1, 4), bg.reshape(-1, 4)
    layer = np.full((len(BINS), 4), np.nan)
    for i in np.unique(idx):
        sel = idx == i
        o, b = O[sel], B[sel]
        n = len(o)
        if n < 8:       # too few pixels to say; the neighbouring bins decide
            continue
        # unknowns c_r, c_g, c_b, a:  o_k - b_k = c_k - a b_k ;  o_a - b_a = a (1 - b_a)
        A = np.zeros((4 * n, 4))
        rhs = np.zeros(4 * n)
        for k in range(3):
            A[k * n:(k + 1) * n, k] = 1
            A[k * n:(k + 1) * n, 3] = -b[:, k]
            rhs[k * n:(k + 1) * n] = o[:, k] - b[:, k]
        A[3 * n:, 3] = 1 - b[:, 3]
        rhs[3 * n:] = o[:, 3] - b[:, 3]
        reg = 1e-3 * n
        x = np.linalg.solve(A.T @ A + reg * np.eye(4), A.T @ rhs)
        # over a black background the alpha is free; it must still cover the colour (premultiplied)
        a = np.clip(max(x[3], x[:3].max()), 0, 1)
        layer[i] = [*np.clip(x[:3], 0, a), a]
    ok = ~np.isnan(layer[:, 3])
    for c in range(4):
        layer[:, c] = np.interp(BINS, BINS[ok], layer[ok, c])
    far = BINS > BINS[ok].max()
    layer[far] = 0
    return layer


def reach(layer):
    """Distance beyond the letter edge where the effect has faded."""
    vis = np.nonzero(layer[:, 3] > 0.03)[0]
    return max(0.0, BINS[vis.max()]) if len(vis) else 0.0


def learn_rows(img, bg, sd):
    """Fill of the letters per row (premultiplied), from the inside of the original letters."""
    pm = img.copy()
    pm[..., :3] *= pm[..., 3:4]
    inside = sd < -0.75
    rows = np.full((img.shape[0], 4), np.nan)
    for r in range(img.shape[0]):
        sel = inside[r]
        if sel.sum() >= 3:
            o, b = pm[r, sel], bg[r, sel]
            if b[:, 3].max() < 1:
                a = np.mean(o[:, 3] - b[:, 3]) / max(1e-6, np.mean(1 - b[:, 3]))
            else:
                a = 1 - np.mean(o[:, :3]) / max(1e-6, np.mean(b[:, :3]))
            a = float(np.clip(a, 0, 1))
            rows[r] = [*np.clip((o[:, :3] - (1 - a) * b[:, :3]).mean(0), 0, a), a]
    ok = ~np.isnan(rows[:, 3])
    if not ok.any():
        return None
    for c in range(4):
        rows[:, c] = np.interp(np.arange(len(rows)), np.nonzero(ok)[0], rows[ok, c])
    return rows


def learn_texture(img, sd):
    """Fill of the letters at every pixel: the inside of the original letters spread over the box."""
    import cv2
    pm = img.copy()
    pm[..., :3] *= pm[..., 3:4]
    inside = sd < -0.75
    if not inside.any():
        return None
    u8 = (pm * 255).round().astype(np.uint8)
    hole = (~inside).astype(np.uint8)
    out = np.empty(pm.shape)
    out[..., :3] = cv2.inpaint(u8[..., :3], hole, 3, cv2.INPAINT_TELEA) / 255
    out[..., 3] = cv2.inpaint(u8[..., 3], hole, 3, cv2.INPAINT_TELEA) / 255
    return out


def apply(layer, can, shift=0.0, fill=None):
    sd = signed_distance(can) - shift
    pm = np.stack([np.interp(sd, BINS, layer[:, c]) for c in range(4)], -1)
    if fill is not None:
        # inside the letters the measured fill (per row or per pixel), blended in over the edge band
        t = np.clip(-sd - 0.5, 0, 1)[..., None]
        f = np.repeat(fill, SS, 0)[:pm.shape[0]]
        f = f[:, None, :] if f.ndim == 2 else np.repeat(f, SS, 1)[:, :pm.shape[1]]
        pm = pm * (1 - t) + f * t
    return down(pm)


# ---------------------------------------------------------------- items

def expand(entry):
    """Items of a picture entry with the defaults filled in."""
    defaults = {k: v for k, v in entry.items() if k not in ("image", "items", "grid", "words", "copy_to", "by")}
    items = []
    for it in entry.get("items", []):
        items.append({**defaults, **it})
    if "grid" in entry:
        g = entry["grid"]
        by_col = entry.get("by", "row") == "col"
        cell = lambda v: v if isinstance(v, dict) else {"at": v}
        xs, ys = [cell(v) for v in g["x"]], [cell(v) for v in g["y"]]
        for wi, word in enumerate(entry["words"]):
            word = word if isinstance(word, dict) else {"en": word[0], "ru": word[1]}
            for other in (ys if by_col else xs):
                cx, cy = (xs[wi], other) if by_col else (other, ys[wi])
                bx0, by0, bx1, by1 = g["box"]
                over = {k: v for c in (cx, cy) for k, v in c.items() if k != "at"}
                bx1 = bx0 + over.pop("box_w", bx1 - bx0)
                by1 = by0 + over.pop("box_h", by1 - by0)
                cx, cy = cx["at"], cy["at"]
                items.append({**defaults, **over, **word, "box": [cx + bx0, cy + by0, cx + bx1, cy + by1]})
    for it in items:
        it["where"] = f"{entry['image']} {it['en']!r} {it['box']}"
    return items


def render_item(fonts, it, out, orig, report):
    x0, y0, x1, y1 = it["box"]
    if it.get("rotate"):
        # vertical text: turn the box so that the text runs left to right, render, turn it back
        k = -it["rotate"] // 90
        sub = np.ascontiguousarray(np.rot90(orig[y0:y1, x0:x1], k))
        res = sub.copy()
        flat = {key: v for key, v in it.items() if key not in ("rotate", "fit_box", "fit_from")}
        inner = {**flat, "box": [0, 0, sub.shape[1], sub.shape[0]]}
        render_item(fonts, inner, res, sub, report)
        out[y0:y1, x0:x1] = np.rot90(res, -k)
        it.update({key: v for key, v in inner.items() if key.startswith("_")})
        report[-1] = (it, *report[-1][1:])
        return
    img = orig[y0:y1, x0:x1].astype(np.float64)
    H, W = img.shape[:2]
    fb = it.get("fit_box")
    it["fit_box"] = [fb[0] - x0, fb[1] - y0, fb[2] - x0, fb[3] - y0] if fb else [0, 0, W, H]
    fdx, fdy = it.get("fit_from", (0, 0))
    fimg = orig[y0 + fdy:y1 + fdy, x0 + fdx:x1 + fdx]
    size, sx, tracking, x, y = fit(fonts, it, fimg)
    cov_en, org_en = text_mask(fonts, it["font"], it["en"], size, sx, tracking)
    can_en = place(cov_en, org_en, H, W, x, y)
    # the look is measured against the original letters; the font's letters are made as heavy as those
    can_orig = original_letters(it, fimg)
    sd_orig = down(signed_distance(can_orig))
    sd_en_ss = signed_distance(can_en)
    shift = float(np.clip(np.sort(sd_en_ss.ravel())[int(can_orig.sum())], -1.5, 1.5))
    shift = it.get("force_shift", shift)
    erase = np.minimum(sd_orig, down(sd_en_ss))
    if "erase_thr" in it:
        # the darker parts of the letters: below thr, but next to what is above it
        near = signed_distance(original_letters(it, img)) < 3
        low = original_letters(it, img, it["erase_thr"]) * near
        erase = np.minimum(erase, down(signed_distance(low)))
    bg = background(it, img, erase)
    layer = learn(img, bg, sd_orig)
    if it.get("bg", "clear") == "inpaint":
        # only what was erased can belong to the effect; differences further out are the filled-in
        # background, not glow
        layer[BINS > it.get("radius", 8)] = 0
    fill = {"rows": lambda: learn_rows(img, bg, sd_orig), "texture": lambda: learn_texture(img, sd_orig),
            None: lambda: None}[it.get("fill")]()
    margin = reach(layer)

    def composite(can, scale=1.0):
        # the weight correction is relative to the letter size
        lay = apply(layer, can, shift * scale, fill)
        o = lay + (1 - lay[..., 3:4]) * bg
        a = o[..., 3:4]
        o[..., :3] = np.where(a > 1e-6, o[..., :3] / np.maximum(a, 1e-6), 0)
        return np.clip(o, 0, 1)

    # translated text: same size and baseline, the chosen edge kept, squeezed or shrunk to fit
    ex0, _, ex1, _ = ink_box(cov_en)
    en_l = x + (ex0 - org_en[0]) / SS
    en_r = x + (ex1 - org_en[0]) / SS
    lim = it.get("limit")
    pad = max(margin, it.get("pad", 0))
    lim = [lim[0] - x0, lim[1] - x0] if lim else [pad, W - pad]
    if it.get("keep_extent"):
        # the engine shows only as much of the button as the original picture covered
        cols = np.nonzero((img[..., 3] > 0.01).any(0))[0]
        lim = [max(lim[0], cols[0] + margin), min(lim[1], cols[-1] + 1 - margin)]
    # how much the translation must shrink to fit (for "uniform"), with the letter spacing tightened
    room = min(lim[1] - lim[0], it.get("max_w", 1e9))
    it["_size"], it["_sx"] = size, sx
    # the translation starts from the fitted size and scale, or from those given for a whole group
    size_ru, sx_ru = it.get("ru_size", size), it.get("ru_sx", sx)
    trk_ru = tracking * size_ru / size
    tight = trk_ru - it.get("tighten", 0.0) * size_ru
    cov, _ = text_mask(fonts, it["font"], it["ru"], size_ru, sx_ru, tight)
    rx0, _, rx1, _ = ink_box(cov)
    it["_fit"] = room / ((rx1 - rx0) / SS)
    rsize, rsx = size_ru * it.get("start_scale", 1.0), sx_ru * it.get("start_sx", 1.0)
    rtrk = tight if it.get("start_tight") else trk_ru
    gaps = max(1, len(it["ru"]) - 1)
    while True:
        cov, org = text_mask(fonts, it["font"], it["ru"], rsize, rsx, rtrk * rsize / size_ru)
        rx0, _, rx1, _ = ink_box(cov)
        w = (rx1 - rx0) / SS
        if w <= room + 0.01:
            break
        if rtrk > tight + 1e-6:
            # first closer letters, then narrower ones, then smaller ones
            rtrk = max(tight, rtrk - (w - room) / gaps / max(rsx, 1e-6) * size_ru / rsize - 0.01)
        elif rsx > sx_ru * it.get("min_sx", 0.85) + 1e-6:
            rsx = max(sx_ru * it.get("min_sx", 0.85), rsx * room / w)
        else:
            rsize *= 0.98
    align = it.get("align", "left")
    left = {"left": en_l, "center": (en_l + en_r - w) / 2, "right": en_r - w}[align]
    left = min(max(it.get("ink_left", left), lim[0]), lim[1] - w)
    it["_w"], it["_lim"] = w, lim
    if it.get("keep_extent"):
        it["_cut"] = int(cols[-1]) + 1
    rx = left - (rx0 - org[0]) / SS + it.get("dx", 0)
    it["_y"] = y
    ry = it.get("ru_y", y) + it.get("dy", 0)
    can_ru = place(cov, org, H, W, rx, ry)
    out[y0:y1, x0:x1] = composite(can_ru, rsize / size)
    it["_shift"] = shift
    report.append((it, img, composite(can_en), out[y0:y1, x0:x1].copy(), size, sx, rsize, rsx))


def to_u8(a):
    return (np.clip(a, 0, 1) * 255).round().astype(np.uint8)


def compare_sheet(report, path):
    """Rows of: original | English as fitted and re-rendered | translation, over grey."""
    rows = []
    for it, orig, en, ru, *_ in report:
        h, w = orig.shape[:2]
        row = np.zeros((h, 3 * w + 8, 4))
        row[:, :w], row[:, w + 4:2 * w + 4], row[:, 2 * w + 8:] = orig, en, ru
        rows.append(row)
    W = max(r.shape[1] for r in rows)
    can = np.zeros((sum(r.shape[0] + 2 for r in rows), W, 4))
    y = 0
    for r in rows:
        can[y:y + r.shape[0], :r.shape[1]] = r
        y += r.shape[0] + 2
    im = Image.fromarray(to_u8(can), "RGBA")
    bg = Image.new("RGBA", im.size, (90, 90, 110, 255))
    bg.alpha_composite(im)
    bg.convert("RGB").save(path)


def menu_positions(items, menu):
    """
    Where each word of a horizontal menu goes in its button, so that the gaps between the words are as
    even as possible. The engine cuts every button to the width of the original item and lines the
    buttons up, `gap` apart and centred on a `width`-wide screen. Returns {(group, en): ink left in the box}.
    """
    from scipy.optimize import linprog
    out = {}
    for group, order in menu["rows"].items():
        mine = [[it for it in items if it.get("group") == group and it["en"] == en] for en in order]
        if not all(mine):
            missing = [en for en, m in zip(order, mine) if not m]
            raise SystemExit(f"menu: no item {missing} in group {group!r}")
        cut = [max(it["_cut"] for it in m) for m in mine]
        w = [max(it["_w"] for it in m) for m in mine]
        lo = [max(it["_lim"][0] for it in m) for m in mine]
        hi = [min(it["_lim"][1] for it in m) - wk for m, wk in zip(mine, w)]
        # a word that was sized to fill its button exactly has no choice (rounding may leave lo > hi)
        lo, hi = [min(a, (a + c) / 2) for a, c in zip(lo, hi)], [max(c, (a + c) / 2) for a, c in zip(lo, hi)]
        n = len(order)
        x = (menu.get("width", 1920) - sum(cut) - menu.get("gap", 26) * (n - 1)) / 2
        cells = []
        for c in cut:
            cells.append(x)
            x += c + menu.get("gap", 26)
        # variables: ink left of each word on the screen, smallest gap, largest gap, margin to the limits
        bounds = [(cells[k] + lo[k], cells[k] + hi[k]) for k in range(n)] + [(None, None)] * 2 + [(0, None)]
        A, b = [], []
        for k in range(n - 1):
            row = np.zeros(n + 3); row[k + 1], row[k], row[n + 1] = 1, -1, -1; A.append(row); b.append(w[k])
            row = np.zeros(n + 3); row[k + 1], row[k], row[n] = -1, 1, 1; A.append(row); b.append(-w[k])
        for k in range(n):
            row = np.zeros(n + 3); row[k], row[n + 2] = -1, 1; A.append(row); b.append(-(cells[k] + lo[k]))
            row = np.zeros(n + 3); row[k], row[n + 2] = 1, 1; A.append(row); b.append(cells[k] + hi[k])
        spread = np.zeros(n + 3); spread[n], spread[n + 1] = -1, 1
        first = linprog(spread, A_ub=A, b_ub=b, bounds=bounds)
        if not first.success:
            raise SystemExit(f"menu {group!r}: the words do not fit their buttons")
        # among the most even layouts, the one with the most room to the button edges
        roomy = np.zeros(n + 3); roomy[n + 2] = -1
        second = linprog(roomy, A_ub=A + [spread], b_ub=b + [first.fun + 0.25], bounds=bounds)
        p = (second if second.success else first).x
        for k, en in enumerate(order):
            out[(group, en)] = float(p[k] - cells[k])
        gaps = [p[k + 1] - p[k] - w[k] for k in range(n - 1)]
        print(f"  menu {group}: gaps {', '.join(f'{g:.0f}' for g in gaps)} px")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-l", "--language", required=True)
    ap.add_argument("--only", nargs="+", metavar="PICTURE", help="render only these pictures")
    ap.add_argument("--fonts", nargs="+", default=[], metavar="DIR", help="folders with the fonts")
    ap.add_argument("--compare", metavar="DIR", help="also write comparison sheets to DIR")
    args = ap.parse_args(argv)

    lang_dir = os.path.join(ROOT, "languages", args.language)
    spec = json.load(open(os.path.join(lang_dir, "images_text.json"), encoding="utf-8"))
    cfg = json.load(open(os.path.join(lang_dir, "language.json"), encoding="utf-8"))
    src_dir = os.path.join(ROOT, "languages", *cfg["interface_original"].split("/"), "images")
    out_dir = os.path.join(lang_dir, "images")
    fonts = Fonts(spec["fonts"], [os.path.abspath(d) for d in args.fonts] + SYSTEM_FONTS)
    if args.compare:
        os.makedirs(args.compare, exist_ok=True)

    for entry in spec["images"]:
        pictures = []
        for copy in [{}] + entry.get("copy_to", []):
            copy = {"image": copy} if isinstance(copy, str) else copy
            name = copy.get("image", entry["image"])
            if args.only and name not in args.only:
                continue
            src = os.path.join(src_dir, *name.split("/")) + ".png"
            if not os.path.isfile(src):
                raise SystemExit(f"{src} not found: run build.py --language {args.language} --export-images first")
            orig = np.asarray(Image.open(src).convert("RGBA"), np.float64) / 255
            merged = {**entry, **copy, "copy_to": []}
            out, report = orig.copy(), []
            for it in expand(merged):
                render_item(fonts, it, out, orig, report)
            pictures.append([name, merged, orig, out, report])
        if entry.get("uniform") and pictures:
            # again, all pictures of the entry: one size per group (that of the text that has to shrink
            # most, after squeezing it to min_sx) and one squeeze per word, the same in every state
            items = [r[0] for p in pictures for r in p[4]]
            fixed = {}
            if entry.get("same_fit"):
                # one size, horizontal scale and baseline (in the box) per group: the median of the English
                # texts' fits (a tail like that of Q makes a single text look larger), the scale at most max_sx
                for g in {it.get("group") for it in items}:
                    mine = [it for it in items if it.get("group") == g]
                    fixed[g] = (float(np.median([it["_size"] for it in mine])),
                                min(float(np.median([it["_sx"] for it in mine])), entry.get("max_sx", 1e9)),
                                float(np.median([it["_y"] for it in mine])))
                for it in items:
                    size_g, sx_g, _ = fixed[it.get("group")]
                    it["_fit"] *= it["_size"] * it["_sx"] / (size_g * sx_g)
            scale, squeeze = {}, {}
            for it in items:
                g = it.get("group")
                scale[g] = min(scale.get(g, 1.0), it["_fit"] / it.get("min_sx", 0.85))
            for it in items:
                key = (it.get("group"), it["ru"])
                squeeze[key] = min(squeeze.get(key, 1.0), it["_fit"] / scale[it.get("group")])
            for g, factor in entry.get("menu", {}).get("scale", {}).items():
                # smaller words (each squeezed as before) leave room to even out the gaps of a menu
                scale[g] *= factor
            for p in pictures:
                name, merged, orig = p[:3]
                # one letter weight per column of a sheet (one button state), so that no word looks bolder
                weight = {}
                for r in p[4]:
                    weight.setdefault(r[0]["box"][0], []).append(r[0]["_shift"])
                p[3], p[4] = orig.copy(), []
                p.append(weight)
                for it in expand(merged):
                    key = (it.get("group"), it["ru"])
                    extra = dict(zip(("ru_size", "ru_sx", "ru_y"), fixed[key[0]])) if fixed else {}
                    render_item(fonts, {**it, **extra, "start_scale": scale[key[0]], "start_sx": squeeze[key],
                                        "start_tight": squeeze[key] < 1,
                                        "force_shift": float(np.median(weight[it["box"][0]]))}, p[3], orig, p[4])
            if entry.get("menu"):
                # once more, with every word placed for even gaps between the buttons
                where = menu_positions([r[0] for p in pictures for r in p[4]], entry["menu"])
                for p in pictures:
                    name, merged, orig, weight = p[0], p[1], p[2], p[5]
                    p[3], p[4] = orig.copy(), []
                    for it in expand(merged):
                        key = (it.get("group"), it["ru"])
                        extra = dict(zip(("ru_size", "ru_sx", "ru_y"), fixed[key[0]])) if fixed else {}
                        if (key[0], it["en"]) in where:
                            extra["ink_left"] = where[(key[0], it["en"])]
                        render_item(fonts, {**it, **extra, "start_scale": scale[key[0]], "start_sx": squeeze[key],
                                            "start_tight": squeeze[key] < 1,
                                            "force_shift": float(np.median(weight[it["box"][0]]))}, p[3], orig, p[4])
            for p in pictures:
                del p[5:]
        for name, merged, orig, out, report in pictures:
            dst = os.path.join(out_dir, *name.split("/")) + ".png"
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            Image.fromarray(to_u8(out), "RGBA").save(dst)
            print(f"{name}: {len(report)} texts")
            if args.compare:
                compare_sheet(report, os.path.join(args.compare, name.replace("/", "_") + ".png"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
