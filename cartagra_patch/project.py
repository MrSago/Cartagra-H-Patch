"""
Project layout, configuration and input validation.

Every path is resolved from PROJECT_ROOT (the folder that contains build.py)
or from paths given explicitly on the command line, never from the current
working directory.
"""

import hashlib
import json
import os
import struct

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFINITIONS_DIR = os.path.join(PROJECT_ROOT, "definitions")  # shared patch definition (no game data)
LANGUAGES_DIR = os.path.join(PROJECT_ROOT, "languages")  # per-language resources
INPUTS_DIR = os.path.join(PROJECT_ROOT, "inputs")  # local copies of the original game files (not in git)
BUILD_DIR = os.path.join(PROJECT_ROOT, "build")  # intermediate files and reports (not in git)
DIST_DIR = os.path.join(PROJECT_ROOT, "dist")  # final patch files per language (not in git)

LANGUAGE_KEYS = ("code", "name", "target", "target_description", "status", "status_note", "placeholder")
STATUSES = ("complete", "incomplete", "untested")


class BuildError(Exception):
    """An expected failure with a message the user can act on."""


def load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        raise BuildError(f"missing project file: {path}")
    except json.JSONDecodeError as e:
        raise BuildError(f"invalid JSON in {path}: {e}")


def available_languages():
    """{code: config} for every languages/<code>/language.json."""
    out = {}
    if os.path.isdir(LANGUAGES_DIR):
        for code in sorted(os.listdir(LANGUAGES_DIR)):
            path = os.path.join(LANGUAGES_DIR, code, "language.json")
            if os.path.isfile(path):
                out[code] = load_json(path)
    return out


def load_language(code):
    langs = available_languages()
    if code not in langs:
        raise BuildError(f"unsupported language '{code}'. Available: {', '.join(langs) or 'none'}")
    cfg = langs[code]
    missing = [k for k in LANGUAGE_KEYS if k not in cfg]
    if missing:
        raise BuildError(f"languages/{code}/language.json lacks keys: {', '.join(missing)}")
    if cfg["code"] != code:
        raise BuildError(f"languages/{code}/language.json declares code '{cfg['code']}'")
    if cfg["status"] not in STATUSES:
        raise BuildError(f"languages/{code}/language.json: status must be one of {', '.join(STATUSES)}")
    cfg["translation_dir"] = os.path.join(LANGUAGES_DIR, code, "translation")
    cfg["interface_table"] = os.path.join(LANGUAGES_DIR, code, "interface.tsv")
    cfg["images_dir"] = os.path.join(LANGUAGES_DIR, code, "images")
    # originals of the target release's interface (interface.tsv, images.tsv, images/), e.g. "_original_steam/en"
    original = cfg.get("interface_original")
    cfg["interface_original_dir"] = os.path.join(LANGUAGES_DIR, *original.split("/")) if original else None
    return cfg


def interface_translated(lang):
    """True when languages/<code>/interface.tsv translates at least one string."""
    from .exe_text import load_table

    try:
        return any(r["translation"] for r in load_table(lang["interface_table"]))
    except ValueError as e:
        raise BuildError(str(e))


def needed_optional_inputs(lang):
    """Optional input files (keys of definitions/inputs.json) this language's build reads."""
    from .fonts import input_files
    from .images import changed_images

    needed = ["../CARTAGRA.exe"] if interface_translated(lang) else []
    needed += input_files() if lang.get("font_glyphs") else []
    return needed + [f"image/{arch}.PAK" for arch in changed_images(lang)]


def load_restoration():
    return load_json(os.path.join(DEFINITIONS_DIR, "restoration.json"))


def load_manifest():
    return load_json(os.path.join(DEFINITIONS_DIR, "inputs.json"))


def sha256_file(path, chunk=1 << 22):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def check_inputs(set_name, files_dir, manifest, verify_checksums=True, log=print, needed=()):
    """
    Check one input set (inputs/<set>/files) against the manifest.
    Optional files are checked when present and required when listed in `needed`.
    Returns a list of problems (empty when everything is in place).
    """
    sets = manifest["sets"]
    if set_name not in sets:
        return [f"input set '{set_name}' is not described in definitions/inputs.json"]
    spec = sets[set_name]
    if not os.path.isdir(files_dir):
        return [f"{files_dir} does not exist: copy the original files of input set '{set_name}' there"]
    problems = []
    for rel, info in spec["files"].items():
        path = os.path.normpath(os.path.join(files_dir, *rel.split("/")))
        if not os.path.isfile(path):
            if info.get("optional") and rel not in needed:
                continue
            problems.append(f"missing {path}" + (f" (needed for {info['needed_for']})" if info.get("optional") else ""))
            continue
        size = os.path.getsize(path)
        if "size" in info and size != info["size"]:
            problems.append(f"{path}: {size:,} bytes, expected {info['size']:,} (wrong release or a patched file?)")
            continue
        with open(path, "rb") as f:
            head = f.read(16)
        if not rel.upper().endswith(".PAK"):
            if head[:2] != b"MZ":
                problems.append(f"{path}: not a Windows executable")
            elif verify_checksums and "sha256" in info:
                log(f"  checking {set_name}/{rel} ...")
                if sha256_file(path) != info["sha256"]:
                    problems.append(f"{path}: SHA-256 differs from the original release (a patched or modified file?)")
            continue
        if len(head) < 16:
            problems.append(f"{path}: not a PAK archive")
            continue
        data_offset, entries, _, block = struct.unpack("<IIII", head)
        if not block or data_offset % block or data_offset > size:
            problems.append(f"{path}: not a PAK archive (bad header)")
            continue
        if "entries" in info and entries != info["entries"]:
            problems.append(f"{path}: {entries} entries, expected {info['entries']} (wrong release or a patched file?)")
            continue
        if verify_checksums and info["use"] == "data" and "sha256" in info:
            log(f"  checking {set_name}/{rel} ...")
            if sha256_file(path) != info["sha256"]:
                problems.append(f"{path}: SHA-256 differs from the original release (a patched or modified file?)")
    return problems
