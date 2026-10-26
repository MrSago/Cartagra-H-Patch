"""
Automated tests (standard library only):  python tests/test_core.py

The integration test builds the real ru patch twice from inputs/ (slow: a few
minutes, about 1.7 GB in a temporary folder). It runs only when
CARTAGRA_INTEGRATION=1 is set and the input files are present.
"""

import os
import random
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from cartagra_patch import cztool  # noqa: E402
from cartagra_patch import lucascript as ls  # noqa: E402
from cartagra_patch import project  # noqa: E402
from cartagra_patch import script_port as sp  # noqa: E402
from cartagra_patch.lucapak import Entry, LucaPak, SEC_HASH, SEC_PARENT, append_missing, replace_from, xxh64_pure  # noqa: E402

# SHA-256 of the ru patch made by the pre-refactoring build_patch.py (installed and tested in game),
# i.e. without translation tables; the tables only change SCRIPT.PAK
REFERENCE_RU = {
    "SCRIPT.PAK": "578b31f79f8d8a8b041bfa44e4e7b34c3b04dcf949ce8fc870ad877b2d5271ae",
    "image/EVENTCG.PAK": "a390601d1758eee655f632c55ecc6cf586a8e3ba62f3ea86981a6ec74e2774c4",
    "image/OTHCG.PAK": "46ddcb03fb3a6a904257c203fff4f28064313327f7f9dde0d50a9610a7aa74a6",
    "voice/VOICE.PAK": "d1ddf178abbee528c6e81b663d1d72b6e6e8b015ce3a6570dea475b5c5e390ae",
}


def quiet(_msg):
    pass


def make_pak(names, id_start=1001):
    pak = LucaPak()
    pak.id_start, pak.block_size, pak.flags = id_start, 2048, 0x06
    pak.section_types = [(SEC_PARENT, 2), (SEC_HASH, 8)]
    for n in names:
        pak.entries.append(Entry(n, n.encode() * 100, b"", {SEC_PARENT: b"\0\0", SEC_HASH: b"\0" * 8}))
    return pak


def lzw_encode(data):
    """Inverse of cztool's LZW: its decoder adds an entry for the first code too, so new codes start at 257."""
    table = {bytes([i]): i for i in range(256)}
    next_code, codes, w = 257, [], b""
    for c in data:
        wc = w + bytes([c])
        if wc in table:
            w = wc
            continue
        codes.append(table[w])
        table[wc] = next_code
        next_code += 1
        w = bytes([c])
    if w:
        codes.append(table[w])
    return codes


def make_cz4(rgba, w, h, blocks=2):
    """CZ4 file for an RGBA image: delta-coded RGB plane + alpha plane, LZW in `blocks` blocks."""
    band = -(-h // 3)

    def delta(plane, bpp):
        stride = w * bpp
        out = bytearray(plane)
        for y in range(h):
            if y % band:
                for x in range(stride):
                    out[y * stride + x] = (plane[y * stride + x] - plane[(y - 1) * stride + x]) & 0xFF
        return bytes(out)

    rgb = bytes(b for i in range(0, len(rgba), 4) for b in rgba[i:i + 3])
    raw = delta(rgb, 3) + delta(rgba[3::4], 1)
    cut = len(raw) // blocks
    parts = [raw[k * cut:(k + 1) * cut if k < blocks - 1 else len(raw)] for k in range(blocks)]
    encoded = [lzw_encode(part) for part in parts]
    head = b"CZ4\0" + struct.pack("<IHHHHHHHHHH", 0x1C, w, h, 32, 4, 0, 0, w, h, w, h)
    sizes = b"".join(struct.pack("<II", len(c), len(p)) for c, p in zip(encoded, parts))
    return head + struct.pack("<I", blocks) + sizes + b"".join(struct.pack("<%dH" % len(c), *c) for c in encoded)


class LucaPakTests(unittest.TestCase):
    def test_xxh64_known_vectors(self):
        for data, want in ((b"", "ef46db3751d8e999"), (b"abc", "44bc2cf5ad770999"),
                           (b"Nobody inspects the spammish repetition", "fbcea83c8a378bf1")):
            self.assertEqual(int.from_bytes(xxh64_pure(data), "little").to_bytes(8, "big").hex(), want)

    def test_roundtrip_is_byte_identical(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "t.PAK")
            make_pak(["a", "b", "c"]).write(path)
            with open(path, "rb") as f:
                raw = f.read()
            back = LucaPak.read(path)
            self.assertEqual(back.build(), raw)
            self.assertEqual([e.name for e in back.entries], ["a", "b", "c"])
            self.assertEqual(back.id_of("b"), 1002)

    def test_append_keeps_ids_and_remaps_parent(self):
        base, donor = make_pak(["x", "a"]), make_pak(["a", "b", "b_k1"])
        donor.entries[2].sections[SEC_PARENT] = donor.id_of("b").to_bytes(2, "little")
        added = append_missing(base, donor)
        self.assertEqual([e.name for e in added], ["b", "b_k1"])
        self.assertEqual(base.id_of("x"), 1001)  # original entries keep their IDs
        self.assertEqual(int.from_bytes(base.entries[3].sections[SEC_PARENT], "little"), base.id_of("b"))

    def test_replace_in_place(self):
        base, donor = make_pak(["x", "a"]), make_pak(["a"])
        donor.entries[0].data = b"new"
        replace_from(base, donor, ["a"])
        self.assertEqual(base.id_of("a"), 1002)
        self.assertEqual(base.entries[1].data, b"new")


class LucaScriptTests(unittest.TestCase):
    def test_jump_relocation(self):
        target = ls.Instr(26, 0, None, b"", 0)
        goto = ls.Instr(ls.OP_GOTO, 0, None, (0).to_bytes(4, "little"), 4)
        data = ls.assemble([target, goto])
        instrs = ls.parse(data)
        extra = ls.Instr(41, 1, 7, b"\x01\x02\x03")  # odd length -> padded
        out = ls.assemble([extra] + instrs)
        parsed, bad = ls.check(out)
        self.assertEqual(bad, [])
        self.assertEqual(int.from_bytes(parsed[2].body[:4], "little"), parsed[1].offset)


class CzToolTests(unittest.TestCase):
    def test_cz4_decode(self):
        rnd = random.Random(1)
        w, h = 7, 8
        # few distinct values, so the codes reuse dictionary entries (including the code being defined)
        rgba = bytes(rnd.choice((0, 0, 0, 7, 255)) for _ in range(4 * w * h))
        hd, out = cztool.decode(make_cz4(rgba, w, h))
        self.assertEqual((hd["width"], hd["height"]), (w, h))
        self.assertEqual(out, rgba)

    def test_composite_alpha(self):
        base = bytes([10, 20, 30, 255]) * 4
        over = bytes([200, 200, 200, 255, 0, 0, 0, 0])
        out = cztool.composite(base, 2, over, 2, 1, 0, 1)
        self.assertEqual(out[:8], base[:8])
        self.assertEqual(out[8:12], bytes([200, 200, 200, 255]))
        self.assertEqual(out[12:16], bytes([10, 20, 30, 255]))


class TsvTests(unittest.TestCase):
    def test_roundtrip_and_legacy_columns(self):
        rows = [dict(row=0, kind="msg", voice="12", jp="a\tb", translation="x\ny", source="tsv"),
                dict(row=1, kind="msg", voice="0", jp="c", translation="", source="todo")]
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "t.tsv")
            sp.write_tsv(path, rows)
            with open(path, encoding="utf-8") as f:
                self.assertEqual(f.readline().rstrip("\n").split("\t"), ["row", "kind", "voice", "jp", "translation"])
                self.assertEqual(f.readline().rstrip("\n").split("\t"), ["0", "msg", "12", "a\\tb", "x\\ny"])
            self.assertEqual(sp.load_tsv(path), {(0, "a\tb"): "x\ny"})
            for header, row in (("row\tkind\tvoice\tsource\tjp\tru_existing\tru", "0\tmsg\t0\ttsv\tjp\t\tперевод"),
                                ("row\tkind\tvoice\tsource\tjp\texisting\ttranslation", "0\tmsg\t0\ttsv\tjp\tx\tперевод")):
                legacy = os.path.join(d, "legacy.tsv")
                with open(legacy, "w", encoding="utf-8") as f:
                    f.write(header + "\n" + row + "\n")
                self.assertEqual(sp.load_tsv(legacy), {(0, "jp"): "перевод"})
            self.assertEqual(sp.load_tsv(os.path.join(d, "absent.tsv")), {})


class ProjectTests(unittest.TestCase):
    def test_languages_and_manifest(self):
        langs = project.available_languages()
        self.assertIn("ru", langs)
        self.assertIn("en", langs)
        manifest = project.load_manifest()
        for code in langs:
            cfg = project.load_language(code)
            self.assertIn(cfg["target"], manifest["sets"])
            self.assertIn(cfg["status"], project.STATUSES)
        self.assertNotEqual(langs["en"]["status"], "complete")
        with self.assertRaises(project.BuildError):
            project.load_language("xx")

    def test_paths_do_not_depend_on_cwd(self):
        for path in (project.DEFINITIONS_DIR, project.LANGUAGES_DIR, project.INPUTS_DIR, project.BUILD_DIR,
                     project.DIST_DIR):
            self.assertTrue(os.path.isabs(path))
            self.assertEqual(os.path.dirname(path), ROOT)

    def test_output_names(self):
        from cartagra_patch.pipeline import BuildOptions
        lang = {"code": "ru"}
        self.assertEqual(BuildOptions(lang, "j", "t").output_name, "ru")
        self.assertEqual(BuildOptions(lang, "j", "t", scenes=["a1-7-2h"]).output_name, "ru-partial")
        self.assertEqual(BuildOptions(lang, "j", "t", test_start="a1-7-2h").output_name, "ru-test")

    def test_check_inputs_reports_missing(self):
        with tempfile.TemporaryDirectory() as d:
            problems = project.check_inputs("ru-steam", os.path.join(d, "none"), project.load_manifest())
            self.assertTrue(problems and "does not exist" in problems[0])
            os.makedirs(os.path.join(d, "files"))
            problems = project.check_inputs("ru-steam", os.path.join(d, "files"), project.load_manifest())
            self.assertTrue(any("missing" in p for p in problems))

    def test_check_inputs_detects_wrong_files(self):
        files = {"A.PAK": {"use": "data"}, "image/B.PAK": {"use": "index", "entries": 2},
                 "C.PAK": {"use": "data", "size": 5}}
        manifest = {"sets": {"s": {"description": "test", "files": files}}}
        with tempfile.TemporaryDirectory() as d:
            make_pak(["a"]).write(os.path.join(d, "A.PAK"))
            os.makedirs(os.path.join(d, "image"))
            make_pak(["a", "b", "c"]).write(os.path.join(d, "image", "B.PAK"))
            with open(os.path.join(d, "C.PAK"), "wb") as f:
                f.write(b"123")
            files["A.PAK"]["sha256"] = project.sha256_file(os.path.join(d, "A.PAK"))
            problems = project.check_inputs("s", d, manifest, log=quiet)
            self.assertEqual(len(problems), 2)
            self.assertIn("3 entries, expected 2", problems[0])
            self.assertIn("3 bytes, expected 5", problems[1])
            with open(os.path.join(d, "A.PAK"), "r+b") as f:
                f.seek(-1, 2)
                f.write(b"!")
            problems = project.check_inputs("s", d, manifest, log=quiet)
            self.assertTrue(any("SHA-256 differs" in p for p in problems))
            self.assertEqual(len(project.check_inputs("s", d, manifest, verify_checksums=False, log=quiet)), 2)


class CliTests(unittest.TestCase):
    def run_cli(self, *args):
        with tempfile.TemporaryDirectory(prefix="cwd with spaces ") as cwd:
            return subprocess.run([sys.executable, os.path.join(ROOT, "build.py"), *args], cwd=cwd,
                                  capture_output=True, text=True, encoding="utf-8")

    def test_help_and_errors(self):
        self.assertEqual(self.run_cli("--help").returncode, 0)
        self.assertEqual(self.run_cli().returncode, 2)
        self.assertEqual(self.run_cli("--language", "xx").returncode, 2)
        self.assertEqual(self.run_cli("--language", "ru", "--test-set", "1=2").returncode, 2)

    def test_list_languages_marks_status(self):
        r = self.run_cli("--list-languages")
        self.assertEqual(r.returncode, 0)
        self.assertRegex(r.stdout, r"ru +Russian +incomplete")
        self.assertRegex(r.stdout, r"en +English +untested")

    def test_missing_inputs_fail_cleanly(self):
        with tempfile.TemporaryDirectory(prefix="inputs with spaces ") as empty:
            r = self.run_cli("--language", "ru", "--check", "--inputs", empty)
        self.assertEqual(r.returncode, 1)
        self.assertIn("does not exist", r.stderr)


def tree_hashes(folder):
    out = {}
    for dirpath, _, names in os.walk(folder):
        for n in names:
            path = os.path.join(dirpath, n)
            out[os.path.relpath(path, folder).replace(os.sep, "/")] = project.sha256_file(path)
    return out


@unittest.skipUnless(os.environ.get("CARTAGRA_INTEGRATION") == "1", "set CARTAGRA_INTEGRATION=1 to run")
class IntegrationTests(unittest.TestCase):
    """
    Builds ru from the real inputs into a temporary folder (not the project's build/ or dist/):
    once without translation tables (must equal the reference), twice with them (must be identical).
    """

    def test_ru_build_is_reproducible_and_leaves_inputs_alone(self):
        from cartagra_patch import pipeline
        lang = project.load_language("ru")
        manifest = project.load_manifest()
        dirs = {"jp-fhd": os.path.join(project.INPUTS_DIR, "jp-fhd", "files"),
                lang["target"]: os.path.join(project.INPUTS_DIR, lang["target"], "files")}
        for set_name, folder in dirs.items():
            if project.check_inputs(set_name, folder, manifest, verify_checksums=False, log=quiet):
                self.skipTest(f"inputs/{set_name} is not complete")
        mtimes = {d: os.path.getmtime(os.path.join(d, "SCRIPT.PAK")) for d in dirs.values()}
        hashes = []
        with tempfile.TemporaryDirectory(prefix="cartagra build ") as tmp:
            saved = pipeline.BUILD_DIR, pipeline.DIST_DIR
            try:
                pipeline.BUILD_DIR = os.path.join(tmp, "build")
                pipeline.DIST_DIR = os.path.join(tmp, "dist")
                for tables in (os.path.join(tmp, "no tables"), lang["translation_dir"], lang["translation_dir"]):
                    opt = pipeline.BuildOptions(dict(lang, translation_dir=tables), dirs["jp-fhd"], dirs[lang["target"]])
                    dist = pipeline.run_build(opt, project.load_restoration(), log=quiet)
                    hashes.append(tree_hashes(dist))
                    shutil.rmtree(os.path.join(tmp, "build"))
            finally:
                pipeline.BUILD_DIR, pipeline.DIST_DIR = saved
        files = [{k[len("files/"):]: v for k, v in h.items() if k.startswith("files/")} for h in hashes]
        self.assertEqual(files[0], REFERENCE_RU)
        self.assertEqual(hashes[1], hashes[2])
        self.assertEqual({k: v for k, v in files[1].items() if k != "SCRIPT.PAK"},
                         {k: v for k, v in REFERENCE_RU.items() if k != "SCRIPT.PAK"})
        for set_name, folder in dirs.items():
            self.assertEqual(project.check_inputs(set_name, folder, manifest, log=quiet), [])
        self.assertEqual(mtimes, {d: os.path.getmtime(os.path.join(d, "SCRIPT.PAK")) for d in dirs.values()})


if __name__ == "__main__":
    unittest.main()
