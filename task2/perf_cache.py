#!/usr/bin/env python3
"""Промахи кэшей для BFS и SSSP на всех графах.

Каждый ранг MPI оборачивается в `perf stat`, поэтому счётчики снимаются
отдельно для каждого ранга (обычный `perf stat mpirun ...` измерял бы только
сам mpirun).

Пишутся два файла:
  perf_cache.csv          — algo, graph, n, rank, event, value
                            (rank = -1 означает сумму по рангам);
  perf_raw/<algo>_<graph>_n<N>/rank<R>.txt — сырые отчёты perf stat;
  perf_raw/<algo>_<graph>_n<N>/run.log     — stdout/stderr прогона.

Запуск:
  python3 perf_cache.py
  python3 perf_cache.py --graphs belgium_osm rgg_n_2_22_s0 --ns 1 2 3
"""
from pathlib import Path
import argparse
import csv
import os
import re
import shlex
import subprocess
import sys

CURR_DIR = Path(__file__).parent.resolve()
DATA_DIR = CURR_DIR / "data"
GALOIS_DIR = CURR_DIR / "Galois/build/lonestar/analytics/distributed"

ALGOS = {
    "bfs": {
        "bin": GALOIS_DIR / "bfs/bfs-push-dist",
        "graph": ".gr",
        "transpose": ".tgr",
        "extra": ["-maxIterations=10000", "-t=1", "-partition=oec", "-exec=Sync"],
    },
    "sssp": {
        "bin": GALOIS_DIR / "sssp/sssp-push-dist",
        "graph": ".wgr",
        "transpose": ".twgr",
        "extra": ["-maxIterations=10000", "-t=1", "-partition=oec", "-exec=Sync"],
    },
}

EVENTS = "L1-dcache-load-misses,LLC-load-misses"
NS = [1, 2, 3, 4, 5, 6]

COUNTER_RE = re.compile(r"^([0-9][0-9,]*)\s+([A-Za-z][A-Za-z0-9:._-]*)\s*(\(.*\))?$")
UNSUPPORTED_RE = re.compile(r"^<(not supported|not counted)>\s+([A-Za-z][A-Za-z0-9:._-]*)\s*$")


def all_graphs() -> list[str]:
    return sorted(
        d.name for d in DATA_DIR.iterdir()
        if d.is_dir() and (d / (d.name + ".gr")).is_file() and (d / (d.name + ".wgr")).is_file()
    )


def pick_median_vertex_from_edgelist(edgelist: Path) -> int:
    outdeg: dict[int, int] = {}
    with edgelist.open() as handle:
        for line in handle:
            parts = line.split()
            if len(parts) < 2:
                continue
            src, dst = int(parts[0]), int(parts[1])
            if src == dst:
                continue
            outdeg[src] = outdeg.get(src, 0) + 1
    if not outdeg:
        return 0
    ranked = sorted(outdeg, key=lambda v: (outdeg[v], v))
    return ranked[len(ranked) // 2]


def median_vertex(graph: str) -> int:
    cache = DATA_DIR / graph / "median_vertex.txt"
    if cache.is_file() and cache.read_text().strip():
        try:
            return int(cache.read_text().strip())
        except ValueError:
            pass
    el = DATA_DIR / graph / (graph + ".el")
    if not el.is_file():
        raise FileNotFoundError(f"missing edgelist: {el}")
    vert = pick_median_vertex_from_edgelist(el)
    cache.write_text(f"{vert}\n")
    return vert


def parse_counters(text: str) -> dict[str, float]:
    values: dict[str, float] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or UNSUPPORTED_RE.match(stripped):
            continue
        m = COUNTER_RE.match(stripped)
        if m:
            values[m.group(2)] = float(m.group(1).replace(",", ""))
    return values


def run_one(algo: str, graph: str, n: int, raw_dir: Path) -> tuple[list[list], list[str]]:
    """Прогон под perf; возвращает строки CSV и список проблем."""
    spec = ALGOS[algo]
    run_dir = raw_dir / f"{algo}_{graph}_n{n}"
    run_dir.mkdir(parents=True, exist_ok=True)

    vert = median_vertex(graph)
    app = [
        str(spec["bin"]),
        str(DATA_DIR / graph / (graph + spec["graph"])),
        f"-startNode={vert}",
        "-runs=1",
        f"-graphTranspose={DATA_DIR / graph / (graph + spec['transpose'])}",
        *spec["extra"],
    ]
    script = ('exec perf stat -e "$PERF_EVENTS" '
              '-o "${PERF_OUT_PREFIX}${OMPI_COMM_WORLD_RANK}.txt" -- "$@"')
    cmd = [
        "mpirun", "-n", str(n),
        "--map-by", "core", "--bind-to", "core",
        "sh", "-c", script, "perf-run", *app,
    ]

    e = os.environ.copy()
    e["GALOIS_DO_NOT_BIND_THREADS"] = "1"
    e["PRINT_PER_HOST_STATS"] = "1"
    e["PERF_EVENTS"] = EVENTS
    e["PERF_OUT_PREFIX"] = str(run_dir / "rank")

    print(f"  {' '.join(cmd)}", flush=True)
    proc = subprocess.run(cmd, capture_output=True, text=True, env=e, cwd=CURR_DIR)

    with (run_dir / "run.log").open("w") as f:
        f.write(f"# command: {shlex.join(cmd)}\n")
        f.write(f"# returncode: {proc.returncode}\n")
        f.write(proc.stdout)
        if proc.stderr:
            f.write("\n# ---- STDERR ----\n")
            f.write(proc.stderr)

    problems = []
    if proc.returncode != 0:
        problems.append(f"mpirun returncode {proc.returncode}")

    ranks: dict[int, dict[str, float]] = {}
    for rank_file in sorted(run_dir.glob("rank*.txt")):
        m = re.search(r"rank(\d+)\.txt$", rank_file.name)
        if not m:
            continue
        ranks[int(m.group(1))] = parse_counters(rank_file.read_text(errors="ignore"))
    for rank in range(n):
        if rank not in ranks:
            problems.append(f"rank {rank}: нет отчёта perf")
        elif not ranks[rank]:
            problems.append(f"rank {rank}: счётчики не посчитаны")

    rows = []
    for rank in sorted(ranks):
        for event, value in ranks[rank].items():
            rows.append([algo, graph, n, rank, event, f"{value:.0f}"])
    for event in EVENTS.split(","):
        rows.append([algo, graph, n, -1, event,
                     f"{sum(r.get(event, 0.0) for r in ranks.values()):.0f}"])
    return rows, problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--graphs", nargs="+", default=None,
                        help="графы из data/ (по умолчанию: все)")
    parser.add_argument("--ns", nargs="+", type=int, default=NS,
                        help="число рангов MPI (по умолчанию: 1 2 3 4 5 6)")
    parser.add_argument("--algos", nargs="+", default=["bfs", "sssp"], choices=list(ALGOS))
    parser.add_argument("--out", default="perf_cache.csv", help="файл с результатами")
    parser.add_argument("--raw-dir", default="perf_raw", help="каталог с сырыми отчётами")
    args = parser.parse_args()

    graphs = args.graphs if args.graphs else all_graphs()
    raw_dir = CURR_DIR / args.raw_dir
    raw_dir.mkdir(parents=True, exist_ok=True)
    out_file = CURR_DIR / args.out

    print(f"graphs: {', '.join(graphs)}")
    print(f"ns: {args.ns}")
    print(f"algos: {args.algos}")
    print(f"events: {EVENTS}")

    rows = []
    with out_file.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["algo", "graph", "n", "rank", "event", "value"])
        for algo in args.algos:
            for graph in graphs:
                for n in args.ns:
                    print(f"=== {algo} {graph} n={n} ===", flush=True)
                    try:
                        run_rows, problems = run_one(algo, graph, n, raw_dir)
                    except Exception as exc:
                        print(f"  ERROR: {exc}", file=sys.stderr)
                        continue
                    for p in problems:
                        print(f"  WARNING: {p}")
                    w.writerows(run_rows)
                    f.flush()
                    rows.extend(run_rows)

    print(f"\n{len(rows)} строк -> {out_file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
