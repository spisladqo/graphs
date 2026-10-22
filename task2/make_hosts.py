#!/usr/bin/env python3
"""График «время фаз каждого ранга при P = 6» по логам *_hosts.txt.

Данные берутся из results/result_bfs_<graph>_n6_hosts.txt: в этих файлах
для каждой статистики есть строка HostValues со значением на каждый ранг.
Все числа — медиана по прогонам, выполненным в этом файле.

Фазы на ранге:
  * вычисления       — время do_all ядра BFS (BFS_k Time);
  * обмен            — Gluon Sync_BFS_k;
  * остальное       — остаток до Timer_k (Allreduce, терминация и
    ожидание самого медленного ранга).

Рисунок:
  bfs_hosts.pdf/png   две панели (RGG, LiveJournal)

Запуск:  python make_hosts.py [каталог_результатов] [каталог_для_картинок]
"""
import os
import re
import statistics
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

P = 6
PRETTY = {
    "belgium_osm": "belgium_osm",
    "rgg_n_2_22_s0": "RGG 2²²",
    "soc-LiveJournal1": "LiveJournal",
}
BFS_GRAPHS = ["rgg_n_2_22_s0", "soc-LiveJournal1"]

COMPUTE_COLOR = "tab:blue"
SYNC_COLOR = "tab:orange"
WAIT_COLOR = "0.78"

plt.rcParams.update({
    "font.size": 9,
    "axes.grid": True,
    "grid.alpha": 0.25,
    "grid.linestyle": ":",
    "legend.frameon": False,
    "figure.dpi": 160,
    "savefig.bbox": "tight",
})


def parse_hosts(path):
    """{(регион, статистика): [значение на каждый ранг]} из строк HostValues."""
    vals = {}
    with open(path, "r", errors="ignore") as f:
        for line in f:
            if not line.startswith("STAT,"):
                continue
            p = [x.strip() for x in line.split(",")]
            if len(p) < 6 or p[4] != "HostValues":
                continue
            try:
                vals[(p[2], p[3])] = [float(x) for x in p[5].split(";")]
            except ValueError:
                pass
    return vals


def per_rank_median(vals, region, prefix):
    """Медиана по прогонам значения prefix_k на каждом ранге."""
    nruns = 0
    while (region, f"{prefix}_{nruns}") in vals:
        nruns += 1
    series = [vals[(region, f"{prefix}_{run}")] for run in range(nruns)]
    nranks = len(series[0])
    return [statistics.median(s[r] for s in series if len(s) == nranks)
            for r in range(nranks)]


def per_rank_time(vals, prefix):
    """Медиана по прогонам времени do_all ядра (регион <ALGO>_<run>, Time).

    Регион меняется от прогона к прогону, поэтому серия собирается вручную;
    число прогонов берётся из файла, а не задаётся константой.
    """
    runs = []
    for (reg, cat), v in vals.items():
        if cat != "Time":
            continue
        m = re.fullmatch(re.escape(prefix) + r"_(\d+)", reg)
        if m:
            runs.append((int(m.group(1)), v))
    runs.sort()
    nranks = len(runs[0][1])
    return [statistics.median(s[r] for _, s in runs if len(s) == nranks)
            for r in range(nranks)]


def fig_bfs(results_dir, out):
    ncols = len(BFS_GRAPHS)
    fig, axes = plt.subplots(1, ncols, figsize=(4.4 * ncols, 2.9), squeeze=False)
    for k, g in enumerate(BFS_GRAPHS):
        ax = axes[0][k]
        path = os.path.join(results_dir, f"result_bfs_{g}_n{P}_hosts.txt")
        vals = parse_hosts(path)
        # время do_all хранится как Time в регионе BFS_k, т.е. регион меняется
        # от прогона к прогону, поэтому собираем серию вручную
        comp = [v / 1000 for v in per_rank_time(vals, "BFS")]
        sync = [v / 1000 for v in per_rank_median(vals, "Gluon", "Sync_BFS")]
        total = per_rank_median(vals, "BFS", "Timer")
        total = [t / 1000 for t in total]
        work = per_rank_median(vals, "BFS", "NumWorkItems")
        ranks = list(range(len(comp)))
        wait = [max(0.0, t - c - s) for t, c, s in zip(total, comp, sync)]
        height = [c + s + w for c, s, w in zip(comp, sync, wait)]

        ax.bar(ranks, comp, width=0.65, color=COMPUTE_COLOR)
        ax.bar(ranks, sync, bottom=comp, width=0.65, color=SYNC_COLOR)
        bottom = [c + s for c, s in zip(comp, sync)]
        ax.bar(ranks, wait, bottom=bottom, width=0.65, color=WAIT_COLOR)
        ticks = [f"{r}\n{w / 1e6:.0f} М" for r, w in zip(ranks, work)]
        ax.set_xticks(ranks, ticks, fontsize=8)
        ax.set_xlabel("ранг; млн обработок за прогон", labelpad=5)
        ax.set_ylabel("время, с")
        ax.set_title(f"{PRETTY.get(g, g)}, $P = 6$", fontsize=10)
        ax.set_ylim(0, max(height) * 1.08)

    handles = [
        Patch(color=COMPUTE_COLOR, label="вычисления (do_all)"),
        Patch(color=SYNC_COLOR, label="обмен (sync)"),
        Patch(color=WAIT_COLOR, label="остальное"),
    ]
    fig.legend(handles=handles, loc="upper center", ncol=3, fontsize=8)
    fig.tight_layout(rect=(0, 0, 1, 0.90))
    for ext in ("pdf", "png"):
        fig.savefig(os.path.join(out, f"bfs_hosts.{ext}"))
    plt.close(fig)


def main():
    results_dir = sys.argv[1] if len(sys.argv) > 1 else "results"
    out = sys.argv[2] if len(sys.argv) > 2 else "figs"
    os.makedirs(out, exist_ok=True)
    fig_bfs(results_dir, out)
    print(out)


if __name__ == "__main__":
    main()
