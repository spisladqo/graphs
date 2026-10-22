#!/usr/bin/env python3
"""График «время по фазам при P = 1…6» в стиле графиков ускорения.

Фазы берутся из обычной статистики Galois (файлы results/result_*.txt):
  * общее время прогона  — Timer_k (HMAX), медиана по прогонам;
  * обмен (sync)         — Gluon Sync_<ALGO>_k (HMAX), медиана по прогонам;
  * вычисления и ожидание — общее время минус обмен.

Настоящий профилировщик фаз (как в референсном talk) требует пропатченного
Galois, поэтому здесь фазы огрублены до двух: обмен и всё остальное.
Таймеры Galois пишут целые миллисекунды, поэтому фазы меньше 1 мс не видны
(при P = 1 обмен не пишется вовсе).

Показываются только графы из talk/talk.pdf — по три на алгоритм, как на
слайдах «время по графам».

Рисунки:
  phases_<algo>.pdf/png   стековые столбцы по P, своя панель на каждый граф
  phases.csv              таблица времён и долей

Запуск:  python make_phases.py [каталог_результатов] [каталог_для_картинок]
"""
import csv
import glob
import os
import re
import statistics
import sys
from collections import defaultdict
from datetime import datetime

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from make_figs import (ALGOS, ALGO_TITLE, FAMILY_BY_ALGO, FAMILY_OVERRIDE,
                       RANKS, REGION, RESULT_RE, sweep_key)

# графы ровно как на слайдах talk/talk.pdf
GRAPHS_BY_ALGO = {
    "bfs": ["belgium_osm", "rgg_n_2_22_s0", "soc-LiveJournal1"],
    "sssp": ["belgium_osm", "rgg_n_2_22_s0", "soc-LiveJournal1"],
    "pagerank": ["rgg_n_2_22_s0", "roadNet-CA", "soc-LiveJournal1"],
    "tc": ["coPapersDBLP", "rgg_n_2_22_s0", "roadNet-CA"],
}

# короткие имена графов для заголовков панелей
PRETTY = {
    "belgium_osm": "belgium_osm",
    "rgg_n_2_22_s0": "RGG 2²²",
    "soc-LiveJournal1": "LiveJournal",
    "amazon-2008": "amazon-2008",
    "roadNet-CA": "roadNet-CA",
    "coPapersDBLP": "coPapersDBLP",
}

# как в make_speedup.py: две фазы — два цвета
COMPUTE_COLOR = "tab:blue"
SYNC_COLOR = "tab:orange"

plt.rcParams.update({
    "font.size": 9,
    "axes.grid": True,
    "grid.alpha": 0.25,
    "grid.linestyle": ":",
    "legend.frameon": False,
    "figure.dpi": 160,
    "savefig.bbox": "tight",
})


# --------------------------------------------------------------------------- разбор


def parse_file(path, region):
    """{прогон: (Timer_k, Sync_<region>_k)} и число раундов из файла статистики."""
    timers, syncs, iters = {}, {}, {}
    with open(path, "r", errors="ignore") as f:
        for line in f:
            if not line.startswith("STAT,"):
                continue
            p = [x.strip() for x in line.split(",")]
            if len(p) < 6:
                continue
            _, _, reg, cat, ttype, val = p[0], p[1], p[2], p[3], p[4], p[5]
            if ttype not in ("HMAX", "HOST_0"):
                continue
            try:
                v = float(val)
            except ValueError:
                continue
            m = re.fullmatch(r"Timer_(\d+)", cat)
            if m and reg == region:
                timers[int(m.group(1))] = v
                continue
            m = re.fullmatch(r"Sync_" + region + r"_(\d+)", cat)
            if m and reg == "Gluon":
                syncs[int(m.group(1))] = v
                continue
            m = re.fullmatch(r"NumIterations_(\d+)", cat)
            if m and reg == region:
                iters[int(m.group(1))] = v
    return timers, syncs, iters


def select(results_dir):
    """Выбирает для каждого (алгоритм, граф) последний полный свип n = 1…6.

    Рассматриваются оба семейства файлов: result_*_nP.txt (обычные прогоны)
    и result_*_nP_hosts.txt (прогоны с per-host статистикой). Семейство
    выбирается по FAMILY_OVERRIDE/FAMILY_BY_ALGO, внутри него берётся самая
    свежая серия с полным набором n = 1…6 и одной командой запуска.
    """
    # series[алгоритм][граф][семейство][ключ запуска] = {P: файл}
    series = defaultdict(lambda: defaultdict(lambda: defaultdict(dict)))
    for path in sorted(glob.glob(os.path.join(results_dir, "result_*.txt"))):
        m = RESULT_RE.match(os.path.basename(path))
        if not m:
            continue
        algo, graph, n, hosts = m.group(1), m.group(2), int(m.group(3)), m.group(4)
        if algo not in ALGOS or n not in RANKS:
            continue
        with open(path, "r", errors="ignore") as f:
            cmd = ""
            for line in f:
                if line.startswith("# command:"):
                    cmd = line.split("# command:", 1)[1].strip()
                    break
        if not cmd:
            continue
        family = "hosts" if hosts else "plain"
        by_key = series[algo][graph][family]
        by_rank = by_key.setdefault(sweep_key(cmd), {})
        if n not in by_rank or os.path.getmtime(path) > \
                os.path.getmtime(by_rank[n]):
            by_rank[n] = path

    chosen = {}
    for algo, by_graph in series.items():
        for graph, by_family in by_graph.items():
            complete = []
            for family, by_key in by_family.items():
                for key, by_rank in by_key.items():
                    if set(RANKS) <= set(by_rank):
                        complete.append((family, by_rank))
            if not complete:
                continue
            want = FAMILY_OVERRIDE.get((algo, graph),
                                       FAMILY_BY_ALGO.get(algo, "plain"))
            pool = [c for c in complete if c[0] == want] or complete
            _, by_rank = max(pool,
                             key=lambda c: max(os.path.getmtime(p)
                                               for p in c[1].values()))
            for n in RANKS:
                chosen[(algo, graph, n)] = by_rank[n]
    return chosen


def collect(results_dir):
    """{(алгоритм, граф, P): {total, sync, compute, iters, runs, mtime}}."""
    chosen = select(results_dir)
    out = {}
    for (algo, graph, n), path in sorted(chosen.items()):
        timers, syncs, iters = parse_file(path, REGION[algo])
        if not timers:
            continue
        total = statistics.median(timers.values())
        sync = statistics.median(syncs.values()) if syncs else 0.0
        sync = min(sync, total)
        out[(algo, graph, n)] = dict(
            total=total,
            sync=sync,
            compute=total - sync,
            iters=statistics.median(iters.values()) if iters else None,
            runs=len(timers),
            mtime=os.path.getmtime(path),
        )
    return out


# --------------------------------------------------------------------------- графики


def graphs_of(data, algo):
    return [g for g in GRAPHS_BY_ALGO.get(algo, []) if any(
        (algo, g, n) in data for n in RANKS)]


def fig_phases(data, out, algo):
    """Столбцы по P: вычисления с ожиданием и обмен, панель на каждый граф."""
    graphs = graphs_of(data, algo)
    if not graphs:
        return
    ncols = min(3, len(graphs))
    nrows = (len(graphs) + ncols - 1) // ncols
    fig, axes = plt.subplots(nrows, ncols, figsize=(4.4 * ncols, 2.9 * nrows),
                             squeeze=False)
    for k, g in enumerate(graphs):
        ax = axes[k // ncols][k % ncols]
        ps = [n for n in RANKS if (algo, g, n) in data]
        if not ps:
            ax.axis("off")
            continue
        total = [data[(algo, g, n)]["total"] / 1000 for n in ps]
        sync = [data[(algo, g, n)]["sync"] / 1000 for n in ps]
        comp = [data[(algo, g, n)]["compute"] / 1000 for n in ps]

        ax.bar(ps, comp, width=0.65, color=COMPUTE_COLOR, label="вычисления и ожидание")
        if any(v > 0 for v in sync):
            ax.bar(ps, sync, bottom=comp, width=0.65, color=SYNC_COLOR,
                   label="обмен")
        for p, y in zip(ps, total):
            label = f"{y:.2f}" if y >= 1 else f"{y:.3f}"
            ax.annotate(label, (p, y), xytext=(0, 3),
                        textcoords="offset points", ha="center", va="bottom",
                        fontsize=7)

        base = data[(algo, g, ps[0])]["total"]
        last = data[(algo, g, ps[-1])]["total"]
        ax.set_title(f"{PRETTY.get(g, g)}: ускорение {base / last:.2f}",
                     fontsize=10)
        ax.set_xlabel("P, рангов")
        ax.set_ylabel("время, с")
        ax.set_xticks(RANKS)
        ax.set_ylim(0, max(total) * 1.30)
        ax.legend(fontsize=7, loc="upper right")
    for k in range(len(graphs), nrows * ncols):
        axes[k // ncols][k % ncols].axis("off")
    fig.tight_layout()
    for ext in ("pdf", "png"):
        fig.savefig(os.path.join(out, f"phases_{algo}.{ext}"))
    plt.close(fig)


def dump_csv(data, out):
    with open(os.path.join(out, "phases.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["algo", "graph", "P", "total_ms", "sync_ms", "compute_ms",
                    "sync_share_%", "rounds", "runs"])
        for algo in ALGOS:
            for graph in graphs_of(data, algo):
                for n in RANKS:
                    d = data.get((algo, graph, n))
                    if not d:
                        continue
                    w.writerow([algo, graph, n, f"{d['total']:.0f}",
                                f"{d['sync']:.0f}", f"{d['compute']:.0f}",
                                f"{100 * d['sync'] / d['total']:.1f}" if d["total"] else "",
                                f"{d['iters']:.0f}" if d["iters"] else "", d["runs"]])


def main():
    results_dir = sys.argv[1] if len(sys.argv) > 1 else "results"
    out = sys.argv[2] if len(sys.argv) > 2 else "figs"
    os.makedirs(out, exist_ok=True)
    data = collect(results_dir)
    if not data:
        sys.exit(f"в {results_dir} нет подходящих result-файлов")

    print("выбранные данные (граф, P -> всего / обмен (доля)):")
    for algo in ALGOS:
        for g in graphs_of(data, algo):
            parts = []
            for n in RANKS:
                d = data.get((algo, g, n))
                if not d:
                    continue
                parts.append(f"P{n}:{d['total']:.0f}/{d['sync']:.0f}"
                             f"({100 * d['sync'] / d['total']:.0f}%)")
            stamp = datetime.fromtimestamp(max(data[(algo, g, n)]["mtime"]
                                               for n in RANKS if (algo, g, n) in data))
            print(f"  {algo:9} {g:20} " + "  ".join(parts)
                  + f"   [свип {stamp:%d.%m %H:%M}]")

    for algo in ALGOS:
        fig_phases(data, out, algo)
    dump_csv(data, out)
    print(f"\nкартинки записаны в {os.path.abspath(out)}/")


if __name__ == "__main__":
    main()
