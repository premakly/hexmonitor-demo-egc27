# Hex Monitor — Demo EGC27

Interactive replay of an experiment on **completing gaps in AIS vessel tracks
with a language model**, submitted to the demonstration session of
EGC 2027. Two LLM methods are compared on the same 120 gaps:

- **VISTA** (Liu et al., PVLDB 2026), which builds a knowledge graph of vessel
  behaviours and has the model write an interpolation function per gap;
- **Hexa**, from Hex Monitor, which walks the gap cell by cell on an H3 grid,
  the model scoring each of the seven possible moves at every step;

against three references without a model: straight-line interpolation, a
density-weighted A\* on the grid, and a *cell oracle* that converts the true
path of cells the way Hexa does (the floor of any cell-based method).

The demo only **reads** the experiment's results: no database, no language
model, no GPU. Everything shown was produced beforehand by the scripts in
`EGC27/`.

## What the demo shows

- every gap, filterable by size (2, 4, 8 cells) and difficulty (cargo and
  tankers on straight routes; fishing, towing and leisure craft on winding ones);
- on the map: the ground truth, each method's completion in its own colour,
  the cells walked by the cell-based methods, and the H3 grid around the gap;
- **the reasoning of each LLM method**: Hexa's chosen moves with the model's
  reason for each, and the tree of every branch it explored; VISTA's chosen
  behaviour with its support in the knowledge graph, the function it selected
  with its generated code, and its written explanation;
- per-gap errors and costs, then the aggregated results with bootstrap
  confidence intervals and paired Wilcoxon tests, exportable as CSV.

## Online

The demo is published on GitHub Pages: **https://premakly.github.io/hexmonitor-demo-egc27/**.
Pages serves static files only, so the workflow in `.github/workflows/pages.yml`
exports every answer of the backend as JSON (`python -m egc27demo.export_static`)
and builds the interface to read them (`VITE_STATIC=1`). It runs the tests, then
publishes, at each push to `main`.

## Running it locally

Python 3.11+ and Node.js 20+.

**Backend** (from `backend/`):

```
pip install -r requirements.txt
uvicorn egc27demo.main:create_app --factory --port 8000
```

**Frontend, development** (from `frontend/`):

```
npm install
npm run dev
```

then open http://localhost:5173 (the dev server forwards `/api` to port 8000;
set `DEMO_BACKEND` to point elsewhere).

**Single process**: after `npm run build` in `frontend/`, the backend serves the
built interface itself at http://localhost:8000.

**As on GitHub Pages**, without the backend:

```
cd backend && python -m egc27demo.export_static
cd ../frontend && VITE_STATIC=1 npm run build && npm run preview
```

The data folder defaults to `data/experiment/`; set `EGC27_DEMO_DATA` to use
another one (see `data/README.md` for its layout).

## Tests

```
cd backend && pip install -r requirements-dev.txt && pytest
cd frontend && npm test
```

## The experiment

40 AIS trajectories of 200 points (North-East Atlantic and western
Mediterranean, 1–12 January 2023), 20 per difficulty level; in each, one gap
of 2, 4 and 8 observed H3 cells, every removed cell holding at least one real
AIS point. Both LLM methods ran on the same local model (Ollama, 12,288-token
context, temperature 0). Errors are measured on tracks resampled every 300 s;
the protocol, its parameters and its limits are described in the paper.

The scripts in `EGC27/` (dataset extraction, gap generation, method adapters,
metrics) document the protocol. Running them again needs what this repository
does not ship: the AIS database, Hex Monitor's walking engine, a VISTA
installation and a language model server.

## VISTA

VISTA is not included. Its code is available at
https://github.com/hyLiu1994/VISTA under the Apache 2.0 licence; it was run
unmodified in its imputation logic, through an adapter that imposes the gaps
(see `EGC27/vista_adapter.py`).

> H. Liu, T. Li, H. Wang, K. Torp, T. Zhang, Y. Li, C. S. Jensen.
> *VISTA: Knowledge-Driven Vessel Trajectory Imputation with Repair Provenance.*
> PVLDB 19(1), 2026. arXiv:2601.06940.

## Licence

Code: MIT (see `LICENSE`). The AIS-derived data in `data/` are provided by the
authors with this demonstration.
