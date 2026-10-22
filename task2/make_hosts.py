#!/usr/bin/env python3
"""График «время фаз каждого ранга при P = 6» по логам *_hosts.txt.

Данные берутся из results/result_<algo>_<graph>_n6_hosts.txt: в этих файлах
для каждой статистики есть строка HostValues со значением на каждый ранг.
Все числа — медиана по прогонам, выполненным в этом файле.

Фазы на ранге:
  * вычисления       — время do_all ядра (регион <ALGO>_k, статистика Time;
                       у PageRank два цикла: PageRank_k и PageRank_delta_k);
  * обмен            — Gluon Sync_<ALGO>_k;
  * остальное        — остаток до Timer_k (Allreduce, терминация и
    ожидание самого медленного ранга).

Рисунки:
  bfs_hosts.pdf/png      BFS: панель на каждый граф
  pagerank_hosts.pdf/png PageRank: панель на каждый граф

Запуск:  python make_hosts.py [каталог_результатов] [каталог_для_картинок]
"""
import os
import re
import statistics
import sys
from collections import defaultdict

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
ALGOS = {
    "bfs": {
        "graphs": ["rgg_n_2_22_s0", "soc-LiveJournal1"],
        "region": "BFS",                       # регион с Timer_k и NumWorkItems_k
        "compute": ["BFS"],                   # регионы с таймером do_all
        "sync": ("Gluon", "Sync_BFS"),
        "work": ("BFS", "NumWorkItems"),       # объём работы по рангам
    },
    "pagerank": {
        "graphs": ["soc-LiveJournal1", "rgg_n_2_22_s0"],
        "region": "PageRank",
        "compute": ["PageRank", "PageRank_delta"],
        "sync": ("Gluon", "Sync_PageRank"),
        "work": ("PageRank", "NumWorkItems"),     # объём работы (одинаков на всех рангах)
    },
}

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
    """Медиана по прогонам времени do_all ядра (регион <ALGO>_k, Time).

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


def per_rank_sync(vals, region, prefix, nranks):
    """Время обмена по рангам.

    Galois пишет таймер только если он ненулевой, поэтому на быстрых
    графах часть рангов в статистике отсутствует. Если значений не
    nranks, обмен не привязывается к рангам (считаем нулевым), и он
    попадает в остаток.
    """
    series = []
    run = 0
    while (region, f"{prefix}_{run}") in vals:
        series.append(vals[(region, f"{prefix}_{run}")])
        run += 1
    if not series:
        return [0.0] * nranks, True
    if len(series[0]) != nranks:
        return [0.0] * nranks, True
    return ([statistics.median(s[r] for s in series if len(s) == nranks)
             for r in range(nranks)], False)


def fig_hosts(results_dir, out, algo):
    """Столбцы по рангам: вычисления, обмен, остальное — панель на каждый граф."""
    spec = ALGOS[algo]
    graphs = spec["graphs"]
    ncols = len(graphs)
    fig, axes = plt.subplots(1, ncols, figsize=(4.4 * ncols, 2.9), squeeze=False)
    for k, g in enumerate(graphs):
        ax = axes[0][k]
        path = os.path.join(results_dir, f"result_{algo}_{g}_n{P}_hosts.txt")
        if not os.path.isfile(path):
            print(f"  нет файла {path}")
            ax.axis("off")
            continue
        vals = parse_hosts(path)
        # время do_all хранится как Time в регионе <ALGO>_k, т.е. регион меняется
        # от прогона к прогону, поэтому собираем серию вручную
        comp = [v / 1000 for v in per_rank_time(vals, spec["compute"][0])]
        for extra in spec["compute"][1:]:
            part = [v / 1000 for v in per_rank_time(vals, extra)]
            comp = [c + p for c, p in zip(comp, part)]
        nranks = len(comp)
        sync, lost = per_rank_sync(vals, *spec["sync"], nranks)
        if lost:
            print(f"  {algo} {g}: таймер обмена записан не для всех рангов "
                  f"(меньше 1 мс) — обмен отнесён к остатку")
        sync = [s / 1000 for s in sync]
        total = per_rank_median(vals, spec["region"], "Timer")
        total = [t / 1000 for t in total]
        ranks = list(range(nranks))
        wait = [max(0.0, t - c - s) for t, c, s in zip(total, comp, sync)]
        height = [c + s + w for c, s, w in zip(comp, sync, wait)]

        ax.bar(ranks, comp, width=0.65, color=COMPUTE_COLOR)
        ax.bar(ranks, sync, bottom=comp, width=0.65, color=SYNC_COLOR)
        bottom = [c + s for c, s in zip(comp, sync)]
        ax.bar(ranks, wait, bottom=bottom, width=0.65, color=WAIT_COLOR)
        if spec["work"]:
            work = per_rank_median(vals, *spec["work"])
            ticks = [f"{r}\n{w / 1e6:.0f} М" for r, w in zip(ranks, work)]
            ax.set_xlabel("ранг; млн обработок за прогон", labelpad=5)
        else:
            ticks = [f"{r}" for r in ranks]
            ax.set_xlabel("ранг", labelpad=5)
        ax.set_xticks(ranks, ticks, fontsize=8)
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
        fig.savefig(os.path.join(out, f"{algo}_hosts.{ext}"))
    plt.close(fig)


def main():
    results_dir = sys.argv[1] if len(sys.argv) > 1 else "results"
    out = sys.argv[2] if len(sys.argv) > 2 else "figs"
    os.makedirs(out, exist_ok=True)
    for algo in ALGOS:
        fig_hosts(results_dir, out, algo)
    print(out)


if __name__ == "__main__":
    main()
