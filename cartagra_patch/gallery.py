"""
The Extras CG gallery: entry _cggallery of PARAM.PAK (the JP release calls it _cgmode; same format).

Read by CARTAGRA.exe at RVA 0x22970 (Steam build). All values are little-endian u16 unless noted:

  head        3 words (0 0 0 in both releases)
  lists       number of slot lists (1)
  unknown     1 word (1)
  per list    count, `count` slot words, `count` UTF-16 strings ending in 0 (empty in both releases)
              slot word: an image ID (one picture) or 0x10000 - k (picture group k, counted from 1)
  groups      count, then per group: n, n image IDs
  per range   base image ID (u32), n, n seen-flag numbers of the images base .. base+n-1 (0xFFFF = none)
              (the reader stops at n = 0 or at the end of the data)

The gallery shows 15 slots per page. A slot is unlocked when one of its pictures has its seen flag set (the
script instruction "mark CG as seen" sets it by image ID through the ranges); the flags are the bits
0..SEEN_FLAGS-1 of the system save.

The previews are SYSCG2.PAK: one picture per slot, image ID = the archive's id_start + slot number.
"""

import struct

from . import cztool
from .lucapak import Entry, SEC_HASH, xxh64

ENTRY = "_cggallery"
JP_ENTRY = "_cgmode"
NONE = 0xFFFF
SEEN_FLAGS = 1000  # size of the seen-flag array in CARTAGRA.exe (dword at RVA 0x5859F0)
PER_PAGE = 15


class Gallery:
    def __init__(self, head, unknown, slots, strings, ranges):
        self.head = head  # the 3 leading words
        self.unknown = unknown
        self.slots = slots  # [[image ID, ...]]: one picture or a group
        self.strings = strings  # one string per slot
        self.ranges = ranges  # [[base, [seen-flag numbers]]]

    @classmethod
    def parse(cls, data):
        pos = 0

        def u16():
            nonlocal pos
            if pos + 2 > len(data):
                raise ValueError("gallery table ends early")
            pos += 2
            return struct.unpack_from("<H", data, pos - 2)[0]

        head = tuple(u16() for _ in range(3))
        lists, unknown = u16(), u16()
        if lists != 1:
            raise ValueError(f"gallery table has {lists} slot lists, expected 1")
        words = [u16() for _ in range(u16())]
        strings = []
        for _ in words:
            end = pos
            while struct.unpack_from("<H", data, end)[0]:
                end += 2
            strings.append(data[pos:end].decode("utf-16-le"))
            pos = end + 2
        groups = []
        for _ in range(u16()):
            groups.append([u16() for _ in range(u16())])
        slots = []
        for w in words:
            if w > 0x8000:
                k = 0x10000 - w
                if not 1 <= k <= len(groups):
                    raise ValueError(
                        f"slot refers to group {k}, the table has {len(groups)}"
                    )
                slots.append(list(groups[k - 1]))
            else:
                slots.append([w])
        ranges = []
        while pos + 6 <= len(data):
            base = struct.unpack_from("<I", data, pos)[0]
            pos += 4
            n = u16()
            if not n:
                break
            ranges.append([base, [u16() for _ in range(n)]])
        return cls(head, unknown, slots, strings, ranges)

    def build(self):
        out = list(self.head) + [1, self.unknown, len(self.slots)]
        groups = []
        for s in self.slots:
            if len(s) == 1:
                out.append(s[0])
            else:
                groups.append(s)
                out.append(0x10000 - len(groups))
        data = struct.pack(f"<{len(out)}H", *out)
        data += b"".join(s.encode("utf-16-le") + b"\0\0" for s in self.strings)
        words = [len(groups)]
        for g in groups:
            words += [len(g)] + g
        data += struct.pack(f"<{len(words)}H", *words)
        for base, flags in self.ranges:
            data += struct.pack(f"<IH{len(flags)}H", base, len(flags), *flags)
        return data

    def pictures(self):
        return [i for s in self.slots for i in s]

    def seen_flag(self, image):
        for base, flags in self.ranges:
            if base <= image < base + len(flags):
                return flags[image - base]
        return NONE


def image_map(jp_images, out_images, aliases=None):
    """
    {JP image ID: [output image IDs]} by archive and name. jp_images/out_images: [(ARCHIVE, id_start, [names])];
    aliases: {(ARCHIVE, JP name): output name} for JP pictures stored under another name, whose output
    picture of the JP name (a substitute) then follows the JP picture.
    """
    where = {
        (a, n): start + i for a, start, names in out_images for i, n in enumerate(names)
    }
    out = {}
    for a, start, names in jp_images:
        for i, n in enumerate(names):
            keys = ([(a, aliases[(a, n)])] if (a, n) in (aliases or {}) else []) + [
                (a, n)
            ]
            out[start + i] = [where[k] for k in keys if k in where]
    return out


def merge(target, jp, jp_to_out, archives):
    """
    Add the JP gallery's pictures to the target gallery, keeping the target's slots and order.

    jp_to_out: {JP image ID: [output image IDs]} (a JP picture missing from the output has none);
    archives: [(id_start, number of entries)] of the output image archives, to extend the ranges of
    archives that got new pictures.

    A JP slot that shares a picture with a target slot adds its other pictures to that slot. A JP slot
    with only new pictures becomes a new slot after the slot that holds the JP gallery's previous slot.
    New gallery pictures get the next free seen-flag numbers, in image ID order. Returns
    (new Gallery, pictures added, origins, JP image IDs left out); origins has one entry per slot:
    ("target", target slot number) or ("jp", JP slot number) for a new slot.
    """
    slots = [list(s) for s in target.slots]
    index = {id(s): k for k, s in enumerate(slots)}
    home_of = {i: s for s in slots for i in s}  # picture -> its slot
    after = {}  # target slot index (-1 = before the first) -> new slots placed after it
    anchor, added, left_out = -1, 0, []
    for jk, jslot in enumerate(jp.slots):
        ids = []
        for j in jslot:
            out = jp_to_out.get(j, [])
            if not out:
                left_out.append(j)
            ids += [i for i in out if i not in ids]
        homes = [home_of[i] for i in ids if i in home_of]
        new = [i for i in ids if i not in home_of]
        if homes:
            home = homes[0]
            anchor = index.get(
                id(home), anchor
            )  # a new slot keeps the anchor of the slot before it
            home += new
        elif new:
            home = new
            after.setdefault(anchor, []).append((home, jk))
        for i in new:
            home_of[i] = home
        added += len(new)
    merged, origins = [], []
    for k in range(-1, len(slots)):
        if k >= 0:
            merged.append(slots[k])
            origins.append(("target", k))
        for s, jk in after.get(k, []):
            merged.append(s)
            origins.append(("jp", jk))
    strings = list(target.strings) + [""] * (len(merged) - len(slots))

    ranges = [[base, list(flags)] for base, flags in target.ranges]
    for start, count in archives:
        for r in ranges:
            if r[0] == start and len(r[1]) < count:
                r[1] += [NONE] * (count - len(r[1]))
    result = Gallery(target.head, target.unknown, merged, strings, ranges)
    used = {f for _, flags in ranges for f in flags if f != NONE}
    free = (f for f in range(SEEN_FLAGS) if f not in used)
    for image in sorted(set(result.pictures())):
        if result.seen_flag(image) != NONE:
            continue
        r = next((r for r in ranges if r[0] <= image < r[0] + len(r[1])), None)
        if r is None:
            raise ValueError(f"image {image} is in no range of the gallery table")
        f = next(free, None)
        if f is None:
            raise ValueError(f"more than {SEEN_FLAGS} gallery pictures")
        r[1][image - r[0]] = f
    return result, added, origins, left_out


def build_previews(target, jp, origins):
    """
    Put the previews (SYSCG2.PAK, LucaPak objects) in the merged slot order: the target's preview of a
    target slot, the JP preview of a new slot scaled to the target's visible size (stored as CZ0 with the
    target's header, black margin). Entries are renamed in order (CGGALLERY_CH01_001, ...). Changes and
    returns `target`.
    """
    model = target.entries[0]
    hd = cztool.header(model.data)
    w, h, (vw, vh) = hd["width"], hd["height"], hd["canvas"]
    prefix = model.name.rstrip("0123456789")
    old, entries = list(target.entries), []
    for n, (source, k) in enumerate(origins, 1):
        if source == "target":
            e = old[k]
        else:
            jh, rgba = cztool.decode(jp.entries[k].data)
            jw, (jvw, jvh) = jh["width"], jh["canvas"]
            visible = b"".join(
                rgba[4 * jw * y : 4 * (jw * y + jvw)] for y in range(jvh)
            )
            small = cztool.resize(visible, jvw, jvh, vw, vh)
            margin = b"\0\0\0\xff"  # opaque black
            pixels = b"".join(
                small[4 * vw * y : 4 * vw * (y + 1)] + margin * (w - vw)
                for y in range(vh)
            )
            data = cztool.encode_cz0(model.data, pixels + margin * (w * (h - vh)))
            e = Entry(None, data, model.meta, dict(model.sections))
            e.sections[SEC_HASH] = xxh64(data)
        e.name = f"{prefix}{n:03d}"
        entries.append(e)
    target.entries = entries
    return target


def pages(gallery):
    return -(-len(gallery.slots) // PER_PAGE)
