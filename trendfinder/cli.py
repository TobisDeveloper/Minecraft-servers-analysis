from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import __version__
from .config import DEFAULT, load


def main(argv=None):
    parser = argparse.ArgumentParser(description="CZ/SK Minecraft Trendfinder - evidence-led hosting research")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name, help_text in [("scan", "Collect live signals and generate an English PDF"),
                            ("demo", "Generate a clearly synthetic offline report"),
                            ("serve", "Start the local dither dashboard")]:
        p = sub.add_parser(name, help=help_text)
        p.add_argument("--data-dir", type=Path, default=Path("data"))
        p.add_argument("--config", type=Path, default=None)
        if name == "serve":
            p.add_argument("--port", type=int, default=8765)
            p.add_argument("--open", action="store_true", help="Open the dashboard in your default browser")
    init = sub.add_parser("init-config", help="Write the example configuration, without credentials")
    init.add_argument("path", type=Path, nargs="?", default=Path("config.local.json"))
    args = parser.parse_args(argv)
    if args.command == "init-config":
        if args.path.exists(): parser.error("Configuration already exists; refusing to overwrite it")
        args.path.write_text(json.dumps(DEFAULT, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print("Created " + str(args.path)); return 0
    try:
        cfg = load(args.config)
        # Imports default to the data folder; explicit paths resolve beside config.
        root = args.config.resolve().parent if args.config else args.data_dir.resolve()
        cfg["import_dir"] = str((root / cfg["import_dir"]).resolve())
        if args.command == "serve":
            from .server import serve
            serve(cfg, args.data_dir.resolve(), args.port, args.open)
            return 0
        from .engine import scan
        run = scan(cfg, args.data_dir, demo=args.command == "demo", progress=print)
        print(f'{len(run["observations"])} observations; {len(run["rankings"])} hypotheses; mode={run["mode"]}')
        for r in run["rankings"][:5]:
            print(f'{r["score"]:5.1f}  {r["candidate"]["name"]:<35} {r["stage"]}')
        return 2 if run["outcome"] == "no_evidence" else 0
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(1, f"Trendfinder: {type(exc).__name__}: check configuration, filesystem permissions and source settings.\n")


if __name__ == "__main__":
    raise SystemExit(main())
