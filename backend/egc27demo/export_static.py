"""
Export the demo's data as static files, for hosting without a server
(GitHub Pages).

The demo only ever reads finished results, so every answer the API could give
can be written out once. The files mirror the API one to one:

    overview.json          GET /api/experiment
    gaps.json              GET /api/experiment/gaps        (all gaps; the
                                                            browser filters)
    gaps/<gap_id>.json     GET /api/experiment/gaps/<gap_id>
    export/<name>.csv      GET /api/experiment/export/<name>.csv

Usage, from backend/:  python -m egc27demo.export_static --out ../frontend/public/data
"""
import argparse
import json
import shutil
from pathlib import Path
from typing import Dict, Optional
from urllib.parse import quote

from .experiment_store import REPO_ROOT, ExperimentStore

DEFAULT_OUT = REPO_ROOT / "frontend" / "public" / "data"


def gap_file(gap_id: str) -> str:
    """The file name of one gap: its id, made safe for a path and a URL."""
    return f"{quote(gap_id, safe='')}.json"


def _write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


def export(store: ExperimentStore, out_dir: Path) -> Dict[str, int]:
    """Write every answer of the API under out_dir; return what was written."""
    out_dir = Path(out_dir)
    if out_dir.exists():
        shutil.rmtree(out_dir)  # a gap removed from the data must not linger here

    _write(out_dir / "overview.json", store.overview())
    gaps = store.gaps()
    _write(out_dir / "gaps.json", {"gaps": gaps})
    for g in gaps:
        _write(out_dir / "gaps" / gap_file(g["gap_id"]), store.gap(g["gap_id"]))

    exports = 0
    for name in ("summary", "tests"):
        path = store.export_path(name)
        if path is not None:
            (out_dir / "export").mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, out_dir / "export" / f"{name}.csv")
            exports += 1
    return {"gaps": len(gaps), "exports": exports}


def main(argv: Optional[list] = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m egc27demo.export_static", description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help=f"output folder (default: {DEFAULT_OUT})")
    parser.add_argument("--data", type=Path, default=None, help="experiment data folder (default: data/experiment)")
    args = parser.parse_args(argv)

    store = ExperimentStore(args.data)
    if not store.available():
        raise SystemExit(f"no experiment data in {store.data_dir}")
    written = export(store, args.out)
    print(f"{written['gaps']} gaps and {written['exports']} tables written to {args.out}")


if __name__ == "__main__":
    main()
