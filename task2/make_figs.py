#!/usr/bin/env python3
"""Построение графиков по результатам D-Galois (results/*.txt).

Рисунки повторяют структуру презентации:
  fig1_speedup.png        ускорение S(P)=T(1)/T(P) для BFS/SSSP/PageRank/TC
  fig2_<algo>_time.png    время vs P (медиана, отрезок min-max, пунктир T(1)/P)
  fig3_rf.png             RF (replication factor) vs P
  fig4_sync_share.png     доля фазы синхронизации в времени прогона (P=6)
  fig5_comm.png           объём и число сообщений обмена на раунд
  fig6_rounds.png         число раундов и работа на раунд
  fig7_front.png          прокси ширины фронта BFS

Запуск:  python make_figs.py [каталог_результатов] [каталог_для_картинок]
"""
import os
import re
import sys
import glob
import statistics
import collections
from datetime import datetime

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ALGOS = ["bfs", "sssp", "pagerank", "tc"]
ALGO_TITLE = {
    "bfs": "BFS",
    "sssp": "SSSP",
    "pagerank": "PageRank",
    "tc": "Подсчёт треугольников",
}
REGION = {"bfs": "BFS", "sssp": "SSSP", "pagerank": "PageRank", "tc": "TC"}
GRAPHS = ["belgium_osm", "rgg_n_2_22_s0", "soc-LiveJournal1", "amazon-2008",
          "roadNet-CA", "coAuthorsCiteseer", "coPapersDBLP"]
RANKS = [1, 2, 3, 4, 5, 6]

# Файлы результатов бывают двух семейств:
#   "plain" — result_<algo>_<graph>_n<P>.txt         (обычный прогон)
#   "hosts" — result_<algo>_<graph>_n<P>_hosts.txt    (тот же прогон с
#              per-host статистикой: значения по каждому рангу)
# Семейство выбирается по алгоритму; внутри семейства берётся самая
# свежая серия с полным набором P = 1..6.
FAMILY_BY_ALGO = {
    "bfs": "hosts",
    "sssp": "hosts",
    "pagerank": "plain",
    "tc": "plain",
}
# исключения: (алгоритм, граф) -> семейство
FAMILY_OVERRIDE = {
    ("tc", "coPapersDBLP"): "hosts",
}

RESULT_RE = re.compile(r"result_(\w+?)_(.+)_n(\d)(_hosts)?\.txt$")

# размеры графов: |V| и |E| посчитаны по data/<graph>/<graph>.el
# (число строк = |E|, max id + 1 = |V|); совпадает со статистикой dGraph_Mining
GRAPH_SIZE = {
    "belgium_osm": (1441295, 3099940),
    "rgg_n_2_22_s0": (4194304, 60718396),
    "soc-LiveJournal1": (4847571, 68993773),
    "amazon-2008": (735323, 5158388),
    "roadNet-CA": (1971281, 5533214),
    "coPapersDBLP": (540486, 30491458),
}

COLORS = {
    "belgium_osm": "#1f77b4",
    "rgg_n_2_22_s0": "#d62728",
    "soc-LiveJournal1": "#2ca02c",
    "amazon-2008": "#ff7f0e",
    "roadNet-CA": "#9467bd",
    "coAuthorsCiteseer": "#8c564b",
    "coPapersDBLP": "#e377c2",
}
MARKERS = ["o", "s", "^", "D", "v", "P"]

plt.rcParams.update({
    "font.size": 9,
    "axes.grid": True,
    "grid.alpha": 0.3,
    "grid.linestyle": ":",
    "legend.frameon": False,
    "figure.dpi": 160,
    "savefig.bbox": "tight",
})


# --------------------------------------------------------------------------- разбор


def sweep_key(cmd):
    """Ключ конфигурации запуска: бинарник и путь к графу обобщены."""
    cmd = re.sub(r"-n\s+\d+", "-n N", cmd)
    cmd = re.sub(r"-startNode=\d+", "-startNode=N", cmd)
    cmd = re.sub(r"/data/[^/\s]+/[^/\s]+", "/data/G/G", cmd)
    cmd = re.sub(r"[\w./-]*?/(\w[\w-]*)-(push|pull)-dist", "BIN", cmd)
    return cmd.strip()


def parse_file(path):
    """Достаёт из result-файла все нужные величины."""
    algo = region = None
    timers, iters, work, sync, sync_run = [], [], [], [], []
    rf = bytes_sent = msgs = None
    cmd = ""
    with open(path, "r", errors="ignore") as f:
        for line in f:
            if line.startswith("# command:"):
                cmd = line.split("# command:", 1)[1].strip()
                continue
            if not line.startswith("STAT,"):
                continue
            p = [x.strip() for x in line.split(",")]
            if len(p) < 6:
                continue
            _, _, reg, cat, ttype, val = p[0], p[1], p[2], p[3], p[4], p[5]
            try:
                v = float(val)
            except ValueError:
                continue
            if reg == "Gluon" and cat == "ReplicationFactor":
                rf = v
            elif reg == "Gluon" and cat.startswith("ReduceSendBytes_"):
                bytes_sent = v
            elif reg == "Gluon" and cat.startswith("ReduceNumMessages_"):
                msgs = v
            elif reg == "Gluon" and cat.startswith("Sync_"):
                sync_run.append(v)
            else:
                m = re.match(r"Timer_(\d+)$", cat)
                if m and reg in ("BFS", "SSSP", "PageRank", "TC"):
                    timers.append(v)
                    continue
                m = re.match(r"NumIterations_(\d+)$", cat)
                if m and reg in ("BFS", "SSSP", "PageRank"):
                    iters.append(v)
                    continue
                m = re.match(r"NumWorkItems_(\d+)$", cat)
                if m and reg in ("BFS", "SSSP", "PageRank"):
                    work.append(v)
    return dict(timers=timers, iters=iters, work=work, sync=sync_run,
                rf=rf, bytes=bytes_sent, msgs=msgs, cmd=cmd)


def load(results_dir, extra=None):
    """Для каждого (алгоритм, граф) выбирает серию прогонов P = 1..6.

    Рассматриваются оба семейства файлов (см. FAMILY_BY_ALGO): обычные
    result_*_nP.txt и result_*_nP_hosts.txt. Серия подходит, только если
    в ней есть все P = 1..6 с одной и той же командой запуска (sweep_key).
    Предпочтительное семейство берётся из FAMILY_OVERRIDE, иначе из
    FAMILY_BY_ALGO; если такого семейства нет — берётся любое доступное.

    extra: список пар (алгоритм, граф), для которых всё равно берётся самая
    свежая серия из любого семейства.
    """
    # (алгоритм, граф) -> список серий (семейство, время, {P: (путь, данные)})
    cand = collections.defaultdict(list)
    for path in sorted(glob.glob(os.path.join(results_dir, "result_*.txt"))):
        m = RESULT_RE.match(os.path.basename(path))
        if not m:
            continue
        algo, graph, n, hosts = m.group(1), m.group(2), int(m.group(3)), m.group(4)
        if algo not in ALGOS or n not in RANKS:
            continue
        data = parse_file(path)
        if not data["cmd"]:
            continue
        family = "hosts" if hosts else "plain"
        key = (algo, graph, family, sweep_key(data["cmd"]))
        series = cand.setdefault(key, {"by_rank": {}, "t": 0.0})
        if n not in series["by_rank"] or \
                os.path.getmtime(path) > os.path.getmtime(series["by_rank"][n][0]):
            series["by_rank"][n] = (path, data)
        series["t"] = max(series["t"], os.path.getmtime(path))

    series_by_graph = collections.defaultdict(list)
    for (algo, graph, family, _), series in cand.items():
        if set(RANKS) <= set(series["by_rank"]):
            series_by_graph[(algo, graph)].append((family, series))

    if not series_by_graph:
        sys.exit(f"в {results_dir} нет подходящих result-файлов")

    extra = set(extra or [])
    res = {}
    files = []
    for (algo, graph), series in sorted(series_by_graph.items()):
        if (algo, graph) in extra:
            family, sel = max(series, key=lambda s: s[1]["t"])
        else:
            want = FAMILY_OVERRIDE.get((algo, graph),
                                       FAMILY_BY_ALGO.get(algo, "plain"))
            same = [s for s in series if s[0] == want]
            family, sel = max(same or series, key=lambda s: s[1]["t"])
        by_rank = sel["by_rank"]
        print(f"{algo:9} {graph:20} {family:5} "
              f"{datetime.fromtimestamp(sel['t']):%d.%m %H:%M}")
        for n in RANKS:
            path, data = by_rank[n]
            med = statistics.median(data["timers"]) if data["timers"] else None
            res[(algo, graph, n)] = dict(
                med=med,
                lo=min(data["timers"]) if data["timers"] else None,
                hi=max(data["timers"]) if data["timers"] else None,
                nruns=len(data["timers"]),
                iters=statistics.median(data["iters"]) if data["iters"] else None,
                work=statistics.median(data["work"]) if data["work"] else None,
                sync=statistics.median(data["sync"]) if data["sync"] else 0.0,
                rf=data["rf"], bytes=data["bytes"], msgs=data["msgs"],
                mtime=os.path.getmtime(path),
            )
            files.append(path)
    return res, files


# --------------------------------------------------------------------------- графики


def fig_speedup(res, out):
    graphs = [g for g in GRAPHS if any((a, g, 1) in res for a in ALGOS)]
    fig, axes = plt.subplots(1, 4, figsize=(12.5, 3.1))
    for ax, algo in zip(axes, ALGOS):
        for g in graphs:
            xs = [n for n in RANKS if (algo, g, n) in res and res[(algo, g, n)]["med"]]
            if not xs or (algo, g, 1) not in res:
                continue
            base = res[(algo, g, 1)]["med"]
            ys = [base / res[(algo, g, n)]["med"] for n in xs]
            ax.plot(xs, ys, marker=MARKERS[graphs.index(g) % len(MARKERS)],
                    color=COLORS.get(g), label=f"{g}: {ys[-1]:.2f} при P={xs[-1]}")
        ax.plot(RANKS, RANKS, ls="--", color="0.45", lw=1.2, label="идеал S = P")
        ax.set_xlabel("P, рангов")
        ax.set_ylabel("ускорение T(1)/T(P)")
        ax.set_title(ALGO_TITLE[algo], fontsize=10)
        ax.set_xticks(RANKS)
        ax.legend(fontsize=6.5, loc="upper left")
    fig.suptitle("Ускорение всех алгоритмов", y=1.04, fontsize=11)
    fig.savefig(os.path.join(out, "fig1_speedup.png"))
    plt.close(fig)


def fig_time(res, out, algo, logscale=False):
    graphs = [g for g in GRAPHS if any((algo, g, n) in res for n in RANKS)]
    if not graphs:
        return
    ncols = min(3, len(graphs))
    nrows = (len(graphs) + ncols - 1) // ncols
    fig, axes = plt.subplots(nrows, ncols, figsize=(4.2 * ncols, 3.2 * nrows),
                             squeeze=False)
    for k, g in enumerate(graphs):
        ax = axes[k // ncols][k % ncols]
        xs = [n for n in RANKS if (algo, g, n) in res]
        med = [res[(algo, g, n)]["med"] / 1000 for n in xs]
        lo = [res[(algo, g, n)]["lo"] / 1000 for n in xs]
        hi = [res[(algo, g, n)]["hi"] / 1000 for n in xs]
        ax.errorbar(xs, med, yerr=[[m - l for m, l in zip(med, lo)],
                                   [h - m for m, h in zip(med, hi)]],
                    fmt="o", color=COLORS.get(g), capsize=3, lw=1.2, ms=4)
        if xs:
            ideal = med[0] / xs[0]          # T(1) при xs[0] == 1
            ax.plot(xs, [ideal / n for n in xs], ls="--", color="0.45", lw=1.1,
                    label="идеал T(1)/P")
            ax.legend(fontsize=7)
        if logscale:
            ax.set_yscale("log")
        ax.set_title(g, fontsize=9)
        ax.set_xlabel("P, рангов")
        ax.set_ylabel("время, с")
        ax.set_xticks(RANKS)
    for k in range(len(graphs), nrows * ncols):
        axes[k // ncols][k % ncols].axis("off")
    fig.suptitle(f"{ALGO_TITLE[algo]}: время по процессам (медиана, отрезок min-max)",
                 y=1.02, fontsize=11)
    fig.tight_layout()
    suffix = "_log" if logscale else ""
    fig.savefig(os.path.join(out, f"fig2_{algo}_time{suffix}.png"))
    plt.close(fig)


def fig_rf(res, out):
    graphs = [g for g in GRAPHS if any(res.get((a, g, n), {}).get("rf")
                                       for a in ALGOS for n in RANKS)]
    if not graphs:
        return
    fig, ax = plt.subplots(figsize=(5.6, 3.6))
    for g in graphs:
        xs, ys = [], []
        for n in RANKS:
            vals = [res[(a, g, n)]["rf"] for a in ALGOS
                    if (a, g, n) in res and res[(a, g, n)]["rf"]]
            if vals:
                xs.append(n)
                ys.append(max(vals))
        ax.plot(xs, ys, marker=MARKERS[graphs.index(g) % len(MARKERS)],
                color=COLORS.get(g), label=g)
    ax.set_xlabel("P, рангов")
    ax.set_ylabel("RF (среднее число копий вершины)")
    ax.set_title("RF по графам", fontsize=10)
    ax.set_xticks(RANKS)
    ax.legend(fontsize=7)
    fig.savefig(os.path.join(out, "fig3_rf.png"))
    plt.close(fig)


def fig_sync_share(res, out):
    rows = []
    for algo in ALGOS:
        if algo == "tc":          # у TC нет фазы синхронизации
            continue
        for g in GRAPHS:
            d = res.get((algo, g, 6))
            if not d or not d["med"]:
                continue
            share = 100.0 * d["sync"] / d["med"]
            rows.append((f"{ALGO_TITLE[algo]} · {g}", min(share, 100.0), d["med"]))
    if not rows:
        return
    fig, ax = plt.subplots(figsize=(8.0, 0.45 * len(rows) + 1.6))
    for k, (name, share, med) in enumerate(rows):
        ax.barh(k, 100 - share, left=0, color="#c9d6e3",
                edgecolor="none", label="вне синхронизации" if k == 0 else None)
        ax.barh(k, share, left=100 - share, color="#d62728",
                edgecolor="none", label="синхронизация" if k == 0 else None)
        ax.text(2, k, name, va="center", ha="left", fontsize=8)
        ax.text(99, k, f"{share:.0f}%  ({med/1000:.2f} с)", va="center",
                ha="right", fontsize=8, color="white" if share > 25 else "black")
    ax.set_xlim(0, 100)
    ax.set_yticks([])
    ax.set_xlabel("доля времени прогона, %")
    ax.set_title("На что уходит время: фаза синхронизации при P = 6", fontsize=10)
    ax.legend(fontsize=8, loc="lower right", ncol=2)
    ax.grid(axis="y", visible=False)
    fig.savefig(os.path.join(out, "fig4_sync_share.png"))
    plt.close(fig)


def fig_comm(res, out):
    graphs = [g for g in GRAPHS if any(res.get(("bfs", g, n), {}).get("bytes")
                                       for n in RANKS)]
    if not graphs:
        return
    fig, axes = plt.subplots(1, 2, figsize=(9.2, 3.4))
    for g in graphs:
        xs = [n for n in RANKS if res.get(("bfs", g, n), {}).get("bytes")]
        if not xs:
            continue
        kb = [res[("bfs", g, n)]["bytes"] / res[("bfs", g, n)]["iters"] / 1024
              for n in xs]
        mm = [res[("bfs", g, n)]["msgs"] / res[("bfs", g, n)]["iters"] for n in xs]
        axes[0].plot(xs, kb, marker="o", ms=4, color=COLORS.get(g), label=g)
        axes[1].plot(xs, mm, marker="o", ms=4, color=COLORS.get(g), label=g)
    axes[0].set_ylabel("КБ на раунд")
    axes[1].set_ylabel("сообщений на раунд")
    for ax in axes:
        ax.set_xlabel("P, рангов")
        ax.set_yscale("log")
        ax.set_xticks(RANKS)
        ax.legend(fontsize=7)
    axes[0].set_title("Объём обмена на раунд (BFS)", fontsize=9)
    axes[1].set_title("Число сообщений на раунд (BFS)", fontsize=9)
    fig.tight_layout()
    fig.savefig(os.path.join(out, "fig5_comm.png"))
    plt.close(fig)


def fig_rounds(res, out):
    graphs = [g for g in GRAPHS if any(res.get(("bfs", g, n), {}).get("iters")
                                       for n in RANKS)]
    if not graphs:
        return
    fig, axes = plt.subplots(1, 2, figsize=(9.2, 3.4))
    for g in graphs:
        xs = [n for n in RANKS if res.get(("bfs", g, n), {}).get("iters")]
        rounds = [res[("bfs", g, n)]["iters"] for n in xs]
        edges = [res[("bfs", g, n)]["work"] / res[("bfs", g, n)]["iters"]
                 for n in xs]
        axes[0].plot(xs, rounds, marker="o", ms=4, color=COLORS.get(g), label=g)
        axes[1].plot(xs, edges, marker="o", ms=4, color=COLORS.get(g), label=g)
    axes[0].set_ylabel("раундов")
    axes[1].set_ylabel("рёбер просмотрено за раунд")
    for ax in axes:
        ax.set_xlabel("P, рангов")
        ax.set_xticks(RANKS)
        ax.legend(fontsize=7)
    axes[0].set_title("Число раундов BFS от P не зависит", fontsize=9)
    axes[1].set_title("Работа на раунд (суммарно по процессам)", fontsize=9)
    fig.tight_layout()
    fig.savefig(os.path.join(out, "fig6_rounds.png"))
    plt.close(fig)


def fig_round_time(res, out):
    """Время одного раунда: T(P) / число раундов."""
    graphs = [g for g in GRAPHS if any(res.get(("bfs", g, n), {}).get("iters")
                                       and res.get(("bfs", g, n), {}).get("med")
                                       for n in RANKS)]
    if not graphs:
        return
    fig, ax = plt.subplots(figsize=(5.6, 3.4))
    for g in graphs:
        xs = [n for n in RANKS if res.get(("bfs", g, n), {}).get("iters")]
        ys = [res[("bfs", g, n)]["med"] / res[("bfs", g, n)]["iters"] for n in xs]
        ax.plot(xs, ys, marker="o", ms=4, color=COLORS.get(g), label=g)
    ax.set_xlabel("P, рангов")
    ax.set_ylabel("время раунда, мс")
    ax.set_title("BFS: время одного раунда", fontsize=10)
    ax.set_xticks(RANKS)
    ax.legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(os.path.join(out, "fig8_round_time.png"))
    plt.close(fig)


def fig_front(res, out):
    """Прокси ширины фронта: рёбер на раунд -> вершин -> % от графа."""
    rows = []
    for g in GRAPHS:
        for n in (1, 6):
            d = res.get(("bfs", g, n))
            if not d or not d["iters"] or not d["work"] or g not in GRAPH_SIZE:
                continue
            V, E = GRAPH_SIZE[g]
            deg = 2.0 * E / V
            edges_round = d["work"] / d["iters"]
            rows.append((g, n, edges_round / deg, 100.0 * edges_round / deg / V))
    if not rows:
        return
    names = []
    for g, _, _, _ in rows:
        if g not in names:
            names.append(g)
    fig, axes = plt.subplots(1, 2, figsize=(9.6, 3.5))
    w = 0.38
    for k, n in enumerate((1, 6)):
        xs = [i + (k - 0.5) * w for i in range(len(names))]
        vals = [next((r[2] for r in rows if r[0] == g and r[1] == n), 0)
                for g in names]
        axes[0].bar(xs, vals, width=w, color=["#4c72b0", "#c44e52"][k],
                    label=f"P = {n}")
        axes[1].bar(xs, [100 * v / GRAPH_SIZE[g][0] for v, g in zip(vals, names)],
                    width=w, color=["#4c72b0", "#c44e52"][k], label=f"P = {n}")
    for ax in axes:
        ax.set_xticks(range(len(names)))
        ax.set_xticklabels(names, rotation=20, fontsize=8)
        ax.legend(fontsize=8)
    axes[0].set_yscale("log")
    axes[0].set_ylabel("активных вершин на раунд (прокси)")
    axes[1].set_ylabel("% от |V|")
    axes[0].set_title("Прокси ширины фронта BFS", fontsize=9)
    axes[1].set_title("Доля графа в работе за раунд", fontsize=9)
    fig.tight_layout()
    fig.savefig(os.path.join(out, "fig7_front.png"))
    plt.close(fig)


def main():
    results_dir = sys.argv[1] if len(sys.argv) > 1 else "results"
    out = sys.argv[2] if len(sys.argv) > 2 else "figs"
    os.makedirs(out, exist_ok=True)
    res, files = load(results_dir)

    # сводка по выбранным файлам
    print("\nвыбранные данные (граф, P -> медиана мс, раундов, sync мс):")
    for algo in ALGOS:
        for g in GRAPHS:
            line = []
            for n in RANKS:
                d = res.get((algo, g, n))
                if d and d["med"]:
                    line.append(f"P{n}:{d['med']:.0f}")
            if line:
                print(f"  {algo:9} {g:20} " + " ".join(line))

    fig_speedup(res, out)
    for algo in ALGOS:
        fig_time(res, out, algo)
        fig_time(res, out, algo, logscale=True)
    fig_rf(res, out)
    fig_sync_share(res, out)
    fig_comm(res, out)
    fig_rounds(res, out)
    fig_round_time(res, out)
    fig_front(res, out)
    print(f"\nкартинки записаны в {os.path.abspath(out)}/")


if __name__ == "__main__":
    main()
