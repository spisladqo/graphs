#!/usr/bin/env python3
"""Графики ускорения и времени в стиле talk.pdf.

Слайд «Ускорение всех алгоритмов»: 4 панели рядом (BFS, SSSP, PageRank,
подсчёт треугольников), пунктир — идеал S = P, в легенде — ускорение при P = 6.
Графики времени построены так же: панель на алгоритм, кривые по графам,
пунктир — идеал T(1)/P, над точками — медиана времени.

Рисунки:
  speedup_all.png      сводные 1 x 4 панели (ускорение)
  speedup_<algo>.png   отдельно по каждому алгоритму (ускорение)
  time_all.png         сводные 1 x 4 панели (время, лог. шкала)
  time_<algo>.png      отдельно по каждому алгоритму (время, линейная шкала)
  time_<algo>_log.png  то же в логарифмической шкале
  time_<algo>_graphs.png     панель на каждый граф алгоритма
  time_<algo>_graphs_log.png то же в логарифмической шкале
  speedup.csv          таблица времён и ускорений

Запуск:  python make_speedup.py [каталог_результатов] [каталог_для_картинок]
"""
import csv
import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from make_figs import ALGOS, ALGO_TITLE, GRAPHS, RANKS, load

# короткие имена графиов для легенды
PRETTY = {
    "belgium_osm": "belgium_osm",
    "rgg_n_2_22_s0": "RGG 2^22",
    "soc-LiveJournal1": "LiveJournal",
    "amazon-2008": "amazon-2008",
    "roadNet-CA": "roadNet-CA",
    "coAuthorsCiteseer": "coAuthors",
    "coPapersDBLP": "coPapersDBLP",
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

# какие графики показывать на слайде «время по графам» для каждого алгоритма
# (None — все доступные)
FIG_GRAPHS = {
    "bfs": ["belgium_osm", "rgg_n_2_22_s0", "soc-LiveJournal1"],
    "sssp": ["belgium_osm", "rgg_n_2_22_s0", "soc-LiveJournal1"],
    "pagerank": ["rgg_n_2_22_s0", "roadNet-CA", "soc-LiveJournal1"],
    "tc": ["coPapersDBLP", "rgg_n_2_22_s0", "roadNet-CA"],
}

plt.rcParams.update({
    "font.size": 9,
    "axes.grid": True,
    "grid.alpha": 0.25,
    "grid.linestyle": ":",
    "legend.frameon": False,
    "figure.dpi": 160,
    "savefig.bbox": "tight",
})


def series(res, algo, graph):
    """(P, T(P) мс, S(P), min мс, max мс) для одного графа.

    None, если нет полной серии P = 1..6.
    """
    base = res.get((algo, graph, 1))
    if not base or not base["med"]:
        return None
    xs, ts, ss, los, his = [], [], [], [], []
    for n in RANKS:
        d = res.get((algo, graph, n))
        if not d or not d["med"]:
            return None
        xs.append(n)
        ts.append(d["med"])
        ss.append(base["med"] / d["med"])
        los.append(d["lo"] if d["lo"] is not None else d["med"])
        his.append(d["hi"] if d["hi"] is not None else d["med"])
    return xs, ts, ss, los, his


def graphs_of(res, algo):
    out = []
    for g in GRAPHS:
        s = series(res, algo, g)
        if s:
            out.append((g, s))
    return out


def ymax(res):
    m = max(RANKS)
    for algo in ALGOS:
        for _, (_, _, ss, _, _) in graphs_of(res, algo):
            m = max(m, max(ss))
    return m * 1.12


def place_labels(ax, items, fs):
    """Разводит подписи значений, чтобы они не наезжали друг на друга.

    items: список (x, y, текст, цвет, сторона), сторона +1 — над точкой,
    -1 — под точкой. Порядок проб: своя сторона, противоположная, затем
    сбоку от точки; в последнюю очередь — отодвинуть подальше по вертикали.
    Так подпись остаётся рядом со своей точкой.
    """
    fig = ax.figure
    fig.canvas.draw()
    rend = fig.canvas.get_renderer()
    prop = matplotlib.font_manager.FontProperties(size=fs)
    ax_box = ax.get_window_extent(rend)
    placed = []  # прямоугольники (px, py, w, h) в пикселях экрана
    out = []

    legend = ax.get_legend()
    if legend is not None:
        lb = legend.get_window_extent(rend)
        placed.append((lb.x0, lb.y0, lb.width, lb.height))

    for x, y, text, color, side in sorted(items, key=lambda it: (it[0], -it[1])):
        w, h, _ = rend.get_text_width_height_descent(text, prop, ismath=False)
        h = h * 1.3 + 1  # запас: реальный extent текста чуть выше метрик
        xd, yd = ax.transData.transform((x, y))
        step = h + 1

        # кандидаты: (сдвиг по X, нижняя граница рамки, высота)
        cands = []
        for k in range(10):
            for s in (side, -side):
                if s > 0:
                    ybox = yd + 3 + k * step
                else:
                    ybox = yd - 3 - h - k * step
                cands.append((0, ybox, h))
                if k < 4:  # сбоку от точки — держим подпись рядом с кривой
                    cands.append((w / 2 + 5, ybox, h))
                    cands.append((-(w / 2 + 5), ybox, h))

        best = None
        for dx, ybox, bh in cands:
            x0 = xd + dx - w / 2
            if (ybox < ax_box.y0 + 1 or ybox + bh > ax_box.y1 - 1
                    or x0 < ax_box.x0 or x0 + w > ax_box.x1):
                continue
            clash = False
            for px, py, pw, ph in placed:
                if (x0 < px + pw and x0 + w > px
                        and ybox < py + ph and ybox + bh > py):
                    clash = True
                    break
            if not clash:
                best = (dx, ybox, bh)
                break
        if best is None:
            best = cands[0]
        dx, ybox, bh = best
        x0 = xd + dx - w / 2
        placed.append((x0, ybox, w, bh))
        x_data = ax.transData.inverted().transform((xd + dx, 0))[0]
        y_data = ax.transData.inverted().transform((0, ybox))[1]
        out.append((x_data, y_data, text, color))

    for x, y, text, color in out:
        ax.annotate(text, (x, y), ha="center", va="bottom", fontsize=fs,
                    color=color)


def draw_speedup_panel(ax, res, algo, label_fs=5.5, legend_fs=6.5,
                        title_fs=10, show_labels=True):
    """Панель ускорения: кривые по графам, пунктир — идеал S = P."""
    curves = graphs_of(res, algo)
    keep = FIG_GRAPHS.get(algo)
    if keep:
        by_g = dict(curves)
        curves = [(g, by_g[g]) for g in keep if g in by_g]
    labels = []
    for k, (g, (xs, _, ss, _, _)) in enumerate(curves):
        color = COLORS.get(g, "0.3")
        marker = MARKERS[GRAPHS.index(g) % len(MARKERS)]
        ax.plot(xs, ss, marker=marker, color=color, ms=3.5, lw=1.1,
                label=f"{PRETTY.get(g, g)}: {ss[-1]:.2f}")
        side = 1 if k % 2 == 0 else -1
        if not show_labels:
            continue
        for x, s in zip(xs, ss):
            if x == RANKS[0]:
                continue  # S(1) = 1 по построению
            labels.append((x, s, f"{s:.2f}", color, side))
    ax.plot(RANKS, RANKS, ls="--", color="0.45", lw=1.2, label="идеал")
    ax.set_xlabel("P, рангов")
    ax.set_ylabel("ускорение T(1)/T(P)")
    ax.set_title(ALGO_TITLE[algo], fontsize=title_fs)
    ax.set_xticks(RANKS)
    ax.set_ylim(0, ymax(res))
    ax.legend(fontsize=legend_fs, loc="upper left")
    place_labels(ax, labels, label_fs)


def draw_time_panel(ax, res, algo, logscale=False, label_fs=5.5,
                    legend_fs=6.5, title_fs=10):
    """Панель времени: ломаная по медианам, пунктир — идеал T(1)/P."""
    curves = graphs_of(res, algo)
    if not curves:
        ax.axis("off")
        return
    labels = []
    for k, (g, (xs, ts, _, _, _)) in enumerate(curves):
        color = COLORS.get(g, "0.3")
        marker = MARKERS[GRAPHS.index(g) % len(MARKERS)]
        med = [t / 1000 for t in ts]
        ax.plot(xs, med, marker=marker, color=color, ms=3.5, lw=1.1,
                label=f"{PRETTY.get(g, g)}: {med[-1]:.2f} с")
        ax.plot(xs, [med[0] / x for x in xs], ls="--", color=color, lw=0.9,
                alpha=0.45)
        side = 1 if k % 2 == 0 else -1
        for x, y in zip(xs, med):
            labels.append((x, y, f"{y:.2f}", color, side))
    ax.plot([], [], ls="--", color="0.45", lw=1.0, label="идеал T(1)/P")
    ax.set_xlabel("P, рангов")
    ax.set_ylabel("время, с")
    ax.set_title(ALGO_TITLE[algo], fontsize=title_fs)
    ax.set_xticks(RANKS)
    if logscale:
        ax.set_yscale("log")
    ax.legend(fontsize=legend_fs, loc="upper right")
    place_labels(ax, labels, label_fs)


def save(fig, out, name):
    """Сохраняет картинку в PNG (растр) и PDF (вектор) для отчёта."""
    fig.savefig(os.path.join(out, name + ".png"))
    fig.savefig(os.path.join(out, name + ".pdf"))
    print(f"  {name}.png / {name}.pdf")


def fig_speedup_all(res, out):
    fig, axes = plt.subplots(1, 4, figsize=(11.0, 2.9))
    for ax, algo in zip(axes, ALGOS):
        draw_speedup_panel(ax, res, algo, label_fs=8, legend_fs=8, title_fs=12,
                           show_labels=False)
    save(fig, out, "speedup_all")
    plt.close(fig)


def fig_speedup_algo(res, out, algo):
    if not graphs_of(res, algo):
        return
    fig, ax = plt.subplots(figsize=(10.5, 3.6))
    draw_speedup_panel(ax, res, algo, label_fs=8, legend_fs=8, title_fs=11)
    save(fig, out, f"speedup_{algo}")
    plt.close(fig)


def fig_time_all(res, out):
    fig, axes = plt.subplots(1, 4, figsize=(12.5, 3.2))
    for ax, algo in zip(axes, ALGOS):
        draw_time_panel(ax, res, algo, logscale=True)
    save(fig, out, "time_all")
    plt.close(fig)


def fig_time_algo(res, out, algo, logscale=False):
    if not graphs_of(res, algo):
        return
    fig, ax = plt.subplots(figsize=(10.5, 3.6))
    draw_time_panel(ax, res, algo, logscale=logscale, label_fs=8,
                    legend_fs=8, title_fs=11)
    save(fig, out, f"time_{algo}" + ("_log" if logscale else ""))
    plt.close(fig)


def fig_time_graphs(res, out, algo, logscale=False):
    """Время по процессам: отдельная панель на каждый граф алгоритма."""
    curves = graphs_of(res, algo)
    keep = FIG_GRAPHS.get(algo)
    if keep:
        by_g = dict(curves)
        curves = [(g, by_g[g]) for g in keep if g in by_g]
    if not curves:
        return
    ncols = min(3, len(curves))
    nrows = (len(curves) + ncols - 1) // ncols
    fig, axes = plt.subplots(nrows, ncols, figsize=(4.4 * ncols, 2.9 * nrows),
                             squeeze=False)
    for k, (g, (xs, ts, ss, _, _)) in enumerate(curves):
        ax = axes[k // ncols][k % ncols]
        color = COLORS.get(g, "0.3")
        marker = MARKERS[GRAPHS.index(g) % len(MARKERS)]
        med = [t / 1000 for t in ts]
        ax.plot(xs, med, marker=marker, color=color, ms=4, lw=1.2)
        ax.plot(xs, [med[0] / x for x in xs], ls="--", color="0.45", lw=1.1,
                label="идеал T(1)/P")
        ax.set_title(f"{PRETTY.get(g, g)}: ускорение {ss[-1]:.2f}", fontsize=10)
        ax.set_xlabel("P, рангов")
        ax.set_ylabel("время, с")
        ax.set_xticks(RANKS)
        if logscale:
            ax.set_yscale("log")
        ax.legend(fontsize=7, loc="upper right")
        place_labels(ax, [(x, y, f"{y:.2f}", color, 1)
                          for x, y in zip(xs, med)], 7)
    for k in range(len(curves), nrows * ncols):
        axes[k // ncols][k % ncols].axis("off")
    fig.tight_layout()
    save(fig, out, f"time_{algo}_graphs" + ("_log" if logscale else ""))
    plt.close(fig)


def dump_csv(res, out):
    path = os.path.join(out, "speedup.csv")
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["algo", "graph", "P", "T_ms", "T_min_ms", "T_max_ms",
                    "speedup"])
        for algo in ALGOS:
            for g, (xs, ts, ss, los, his) in graphs_of(res, algo):
                for x, t, s, lo, hi in zip(xs, ts, ss, los, his):
                    w.writerow([algo, g, x, f"{t:.1f}", f"{lo:.1f}",
                                f"{hi:.1f}", f"{s:.3f}"])
    return path


def main():
    results_dir = sys.argv[1] if len(sys.argv) > 1 else "results"
    out = sys.argv[2] if len(sys.argv) > 2 else "figs"
    os.makedirs(out, exist_ok=True)
    res, _ = load(results_dir)

    print("\nускорение S(P) = T(1)/T(P):")
    for algo in ALGOS:
        curves = graphs_of(res, algo)
        if not curves:
            continue
        print(f"  {ALGO_TITLE[algo]}")
        for g, (xs, ts, ss, _, _) in curves:
            cells = " ".join(f"P{x}={s:.2f}" for x, s in zip(xs, ss))
            print(f"    {PRETTY.get(g, g):14} {cells}")

    print("\nвремя, с:")
    for algo in ALGOS:
        curves = graphs_of(res, algo)
        if not curves:
            continue
        print(f"  {ALGO_TITLE[algo]}")
        for g, (xs, ts, _, _, _) in curves:
            cells = " ".join(f"P{x}={t/1000:.2f}" for x, t in zip(xs, ts))
            print(f"    {PRETTY.get(g, g):14} {cells}")

    fig_speedup_all(res, out)
    for algo in ALGOS:
        fig_speedup_algo(res, out, algo)
    fig_time_all(res, out)
    for algo in ALGOS:
        fig_time_algo(res, out, algo)
        fig_time_algo(res, out, algo, logscale=True)
        fig_time_graphs(res, out, algo)
        fig_time_graphs(res, out, algo, logscale=True)
    print(f"\nкартинки записаны в {os.path.abspath(out)}/")
    print(f"таблица: {dump_csv(res, out)}")


if __name__ == "__main__":
    main()
