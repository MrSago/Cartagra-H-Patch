#!/usr/bin/env python3
"""
Build the Cartagra cut-content patch for one target language.

Examples:
  python build.py --language ru            build dist/ru/
  python build.py --language ru --check    only check the input files
  python build.py --list-languages

The original game files are read from inputs/<set>/files/ (see README.md, "Building the Patch")
or from the folders given with --jp-files / --target-files. Nothing is written
outside build/ and dist/, and the game installation is never touched.
"""

import argparse
import os
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cartagra_patch import project  # noqa: E402
from cartagra_patch.project import BuildError  # noqa: E402

EXIT_OK, EXIT_FAILED, EXIT_USAGE = 0, 1, 2


def parse_args(argv):
    langs = project.available_languages()
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Languages: " + ", ".join(f"{c} ({l.get('name')}, {l.get('status')})" for c, l in langs.items()))
    ap.add_argument("-l", "--language", help="target language code (see --list-languages)")
    ap.add_argument("--list-languages", action="store_true", help="show the available languages and their status")
    ap.add_argument("--check", action="store_true", help="only check that the input files are present and original")
    ap.add_argument("--export-images", action="store_true",
                    help="export the interface pictures with text as PNG to the language's interface originals "
                         "(languages/_original_steam/en/images/) and copy the missing ones to languages/<lang>/images/")
    ap.add_argument("--inputs", metavar="DIR", help="folder with the input sets (default: <project>/inputs)")
    ap.add_argument("--jp-files", metavar="DIR", help="Japanese FHD 2023 files/ folder (default: <inputs>/jp-fhd/files)")
    ap.add_argument("--target-files", metavar="DIR", help="target release files/ folder (default: <inputs>/<target>/files)")
    ap.add_argument("--skip-checksums", action="store_true", help="skip the SHA-256 check of the input archives (faster)")
    ap.add_argument("--no-voice", action="store_true", help="do not build VOICE.PAK (restored lines play silently)")
    ap.add_argument("--scenes", nargs="+", metavar="SCENE", help="port only these scenes (debugging; output goes to dist/<lang>-partial/)")
    ap.add_argument("--test-start", metavar="SCENE",
                    help="TEST BUILD: New Game jumps straight into SCENE; output goes to dist/<lang>-test/")
    ap.add_argument("--test-set", nargs="+", default=[], metavar="VAR=VALUE",
                    help="TEST BUILD: variables the stub sets first (e.g. 6021=5 to enter a route branch)")
    args = ap.parse_args(argv)
    if not args.list_languages and not args.language:
        ap.error("choose a language with --language (" + ", ".join(langs) + ")")
    if args.test_set and not args.test_start:
        ap.error("--test-set needs --test-start")
    return args


def print_languages():
    for code, cfg in project.available_languages().items():
        print(f"{code}  {cfg['name']:8s} {cfg['status']:10s} target: {cfg['target']}")
        print(f"    {cfg['status_note']}")


def export_images(lang, target_dir):
    """--export-images: originals to <interface_original>/images/, missing copies to languages/<lang>/images/."""
    from cartagra_patch import images

    if not lang["interface_original_dir"]:
        print(f"error: languages/{lang['code']}/language.json has no interface_original", file=sys.stderr)
        return EXIT_FAILED
    out = os.path.join(lang["interface_original_dir"], "images")
    print(f"Exporting interface pictures from {target_dir}")
    try:
        rows = images.load_list(os.path.join(lang["interface_original_dir"], "images.tsv"))
        n = images.export(target_dir, rows, out, log=lambda m: print(m, flush=True))
    except (ValueError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_FAILED
    copied = images.copy_missing(out, lang["images_dir"])
    print(f"{n} pictures written to {out}")
    print(f"{copied} copied to {lang['images_dir']} ({n - copied} were there already and were kept)")
    print("Edit the copies; the build replaces only pictures that differ from the originals.")
    return EXIT_OK


def main(argv=None):
    sys.stdout.reconfigure(line_buffering=True)  # keep progress and errors (stderr) in order
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.list_languages:
        print_languages()
        return EXIT_OK

    try:
        lang = project.load_language(args.language)
    except BuildError as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_USAGE

    try:
        test_set = [tuple(int(x) for x in a.split("=", 1)) for a in args.test_set]
    except ValueError:
        print("error: --test-set values must look like 6021=5", file=sys.stderr)
        return EXIT_USAGE

    inputs = os.path.abspath(args.inputs) if args.inputs else project.INPUTS_DIR
    jp_dir = os.path.abspath(args.jp_files) if args.jp_files else os.path.join(inputs, "jp-fhd", "files")
    target_dir = os.path.abspath(args.target_files) if args.target_files else os.path.join(inputs, lang["target"], "files")

    if args.export_images:
        return export_images(lang, target_dir)

    print(f"Cartagra patch build: {lang['code']} ({lang['name']}) - status: {lang['status']}")
    if lang["status"] != "complete":
        print(f"  NOTE: {lang['status_note']}")
    try:
        manifest = project.load_manifest()
        restoration = project.load_restoration()
        print("Checking inputs" + (" (sizes and entry counts only)" if args.skip_checksums else ""))
        needed = project.needed_optional_inputs(lang, restoration)
        sets = (("jp-fhd", jp_dir, ()), (lang["target"], target_dir, needed))
        for set_name, folder, _ in sets:
            print(f"  {set_name}: {folder}")
        # cheap checks of every set first, so a missing folder is reported before minutes of hashing
        problems = [p for name, folder, nd in sets
                    for p in project.check_inputs(name, folder, manifest, False, needed=nd)]
        if not problems and not args.skip_checksums:
            problems = [p for name, folder, nd in sets
                        for p in project.check_inputs(name, folder, manifest, True, needed=nd)]
        if problems:
            print("Input check failed:", file=sys.stderr)
            for p in problems:
                print(f"  - {p}", file=sys.stderr)
            print("README.md, 'Building the Patch', shows how to copy them; definitions/inputs.json lists every file.",
                  file=sys.stderr)
            return EXIT_FAILED
        print("  inputs OK")
        if args.check:
            return EXIT_OK

        from cartagra_patch import pipeline

        opt = pipeline.BuildOptions(lang, jp_dir, target_dir, voice=not args.no_voice, scenes=args.scenes,
                                    test_start=args.test_start, test_set=test_set)
        t0 = time.time()
        dist = pipeline.run_build(opt, restoration, log=lambda m: print(m, flush=True))
    except BuildError as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_FAILED
    except Exception:
        traceback.print_exc()
        print("error: the build failed with an unexpected error (traceback above)", file=sys.stderr)
        return EXIT_FAILED

    print(f"Done in {time.time() - t0:.0f} s. Patch files: {dist}")
    print(f"  see {os.path.join(dist, 'BUILD_INFO.txt')} for the destination of each file")
    print(f"  translation tables: {os.path.join(project.BUILD_DIR, opt.output_name, 'translation')}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
