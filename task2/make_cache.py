#!/usr/bin/env python3
"""Промахи кэшей при росте числа рангов — графики в стиле slides «время по фазам».

Данные берутся из perf_cache.csv, который делает perf_cache.py:
  algo, graph, n, rank, event, value
где rank = -1 — сумма счётчиков по всем рангам, остальные строки — счётчики
отдельных рангов. События: L1-dcache-load-misses и LLC-load-misses.

Рисунки повторяют график фаз (make_phases.py): своя панель на каждый граф,
столбцы по P, две фазы сложены друг на друга, подпись итога над столбцом,
в заголовке — сводка по P = 6. Здесь фазами служат сами промахи: тёмная
(L1) и светлая (LLC) части столбца, слева — миллионы промахов.

Рисунки:
  cache_bfs.pdf/png   промахи кэшей в BFS
  cache_sssp.pdf/png  промахи кэшей в SSSP
  cache.csv           таблица промахов и коэффициента роста

Запуск:  python make_cache.py [perf_cache.csv] [каталог_для_картинок]
"""
import csv
import os
import sys
from collections import defaultdict

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from make_speedup import PRETTY

ALGOS = ["bfs", "sssp"]
ALGO_TITLE = {"bfs": "BFS", "sssp": "SSSP"}
# графы ровно как на слайдах talk/talk.pdf
GRAPHS_BY_ALGO = {
    "bfs": ["belgium_osm", "rgg_n_2_22_s0", "soc-LiveJournal1"],
    "sssp": ["belgium_osm", "rgg_n_2_22_s0", "soc-LiveJournal1"],
}
EVENTS = [
    ("L1-dcache-load-misses", "промахи L1", "tab:green"),
    ("LLC-load-misses", "промахи LLC", "tab:red"),
]
RANKS = [1, 2, 3, 4, 5, 6]

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


def load(path):
    """total[(algo, graph, n, event)] — сумма счётчиков по рангам."""
    total = {}
    per_rank = defaultdict(dict)
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            algo, graph = r["algo"], r["graph"]
            if algo not in ALGOS or graph not in GRAPHS_BY_ALGO[algo]:
                continue
            n, rank, event = int(r["n"]), int(r["rank"]), r["event"]
            if n not in RANKS:
                continue
            val = float(r["value"])
            if rank < 0:
                total[(algo, graph, n, event)] = val
            else:
                per_rank[(algo, graph, n, event)][rank] = val
    # сумма из отдельных рангов — если строки с rank = -1 нет
    for key, ranks in per_rank.items():
        total.setdefault(key, sum(ranks.values()))
    return total, per_rank


def value_of(total, algo, graph, n, event):
    return total.get((algo, graph, n, event))


def fmt(v):
    """Подпись итога над столбцом."""
    return f"{v:.0f}" if v >= 100 else f"{v:.1f}"


def growth(total, algo, graph, event):
    """Во сколько раз выросли промахи от P = 1 до P = 6."""
    base = value_of(total, algo, graph, RANKS[0], event)
    last = value_of(total, algo, graph, RANKS[-1], event)
    if not base or not last:
        return None
    return last / base


# --------------------------------------------------------------------------- графики


def fig_cache(total, out, algo):
    """Столбцы по P: промахи L1 и LLC сложены друг на друга, панель на граф."""
    graphs = GRAPHS_BY_ALGO[algo]
    ncols = min(3, len(graphs))
    nrows = (len(graphs) + ncols - 1) // ncols
    fig, axes = plt.subplots(nrows, ncols, figsize=(4.4 * ncols, 2.9 * nrows),
                             squeeze=False)
    for k, g in enumerate(graphs):
        ax = axes[k // ncols][k % ncols]
        ps = [n for n in RANKS
              if value_of(total, algo, g, n, EVENTS[0][0]) is not None]
        if not ps:
            ax.axis("off")
            continue

        bottom = [0.0] * len(ps)
        for event, label, color in EVENTS:
            vals = [value_of(total, algo, g, n, event) / 1e6 for n in ps]
            ax.bar(ps, vals, bottom=bottom, width=0.65, color=color, label=label)
            bottom = [b + v for b, v in zip(bottom, vals)]
        total_mln = bottom

        for p, y in zip(ps, total_mln):
            ax.annotate(fmt(y), (p, y), xytext=(0, 3),
                        textcoords="offset points", ha="center", va="bottom",
                        fontsize=7)

        mult = growth(total, algo, g, EVENTS[0][0])
        ax.set_title(f"{PRETTY.get(g, g)}: $\\times${mult:.2f} при P = 6",
                     fontsize=10)
        ax.set_xlabel("P, рангов")
        ax.set_ylabel("промахи, млн")
        ax.set_xticks(RANKS)
        ax.set_ylim(0, max(total_mln) * 1.40)
        ax.legend(fontsize=7, loc="upper right")
    for k in range(len(graphs), nrows * ncols):
        axes[k // ncols][k % ncols].axis("off")
    fig.tight_layout()
    for ext in ("pdf", "png"):
        fig.savefig(os.path.join(out, f"cache_{algo}.{ext}"))
    plt.close(fig)


def dump_csv(total, per_rank, out):
    path = os.path.join(out, "cache.csv")
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["algo", "graph", "event", "P", "total", "per_rank_mean",
                    "max_over_min"])
        for algo in ALGOS:
            for g in GRAPHS_BY_ALGO[algo]:
                for event, _, _ in EVENTS:
                    for n in RANKS:
                        tot = value_of(total, algo, g, n, event)
                        if tot is None:
                            continue
                        ranks = per_rank.get((algo, g, n, event), {})
                        mean = sum(ranks.values()) / len(ranks) if ranks else 0.0
                        spread = (max(ranks.values()) / min(ranks.values())
                                  if ranks and min(ranks.values()) else 0.0)
                        w.writerow([algo, g, event, n, f"{tot:.0f}", f"{mean:.0f}",
                                    f"{spread:.2f}"])
    return path


def main():
    csv_path = sys.argv[1] if len(sys.argv) > 1 else "perf_cache.csv"
    out = sys.argv[2] if len(sys.argv) > 2 else "figs"
    os.makedirs(out, exist_ok=True)
    total, per_rank = load(csv_path)
    if not total:
        sys.exit(f"в {csv_path} нет подходящих данных")

    print("промахи (млн, сумма по рангам):")
    for algo in ALGOS:
        print(f"  {ALGO_TITLE[algo]}")
        for g in GRAPHS_BY_ALGO[algo]:
            for event, _, _ in EVENTS:
                cells = []
                for n in RANKS:
                    v = value_of(total, algo, g, n, event)
                    cells.append(f"P{n}:{v/1e6:.1f}" if v is not None else f"P{n}:-")
                print(f"    {PRETTY.get(g, g):14} {event:22} "
                      + "  ".join(cells)
                      + f"   рост x{growth(total, algo, g, event):.2f}")

    for algo in ALGOS:
        fig_cache(total, out, algo)
    print(f"\nкартинки записаны в {os.path.abspath(out)}/")
    print(f"таблица: {dump_csv(total, per_rank, out)}")


if __name__ == "__main__":
    main()
