import os
import re
import glob
import statistics
from collections import defaultdict

# Configuration
ALGORITHMS = ["bfs", "sssp", "tc", "pagerank"]

ALL_GRAPHS = [
    # "cit-Patents",
     "belgium_osm",
    "rgg_n_2_22_s0",
     "soc-LiveJournal1",
     "amazon-2008",
    "roadNet-CA",
    "coPapersDBLP",
    ]

# Per-algorithm graph selection (defaults to ALL_GRAPHS)
GRAPHS_BY_ALGO = {
    "tc": ["belgium_osm", "rgg_n_2_22_s0", "roadNet-CA", "coPapersDBLP"],
}

RANKS = ["n1", "n2", "n3", "n4", "n5", "n6", 
         #"n8"
         ]

RESULTS_DIR = "results"


def extract_timers(filepath):
    """Collect per-run timers Timer_0..Timer_N (ms) from a result file."""
    try:
        with open(filepath, "r", errors="ignore") as f:
            content = f.read()
    except OSError:
        return None

    pattern = re.compile(
        r"^\s*STAT\s*,\s*\d+\s*,\s*[^,]+,\s*Timer_(\d+)\s*,\s*\w+\s*,\s*([0-9.]+)"
    )
    values = []
    for line in content.splitlines():
        m = pattern.match(line)
        if m:
            values.append(float(m.group(2)))
    return values


def extract_timer_total(filepath):
    try:
        with open(filepath, "r", errors="ignore") as f:
            content = f.read()
    except OSError:
        return None

    pattern = re.compile(
        r"^\s*STAT\s*,\s*\d+\s*,\s*[^,]+,\s*TimerTotal\s*,\s*\w+\s*,\s*([0-9.]+)"
    )
    for line in content.splitlines():
        m = pattern.match(line)
        if m:
            return float(m.group(1))
    return None


def extract_median(filepath):
    """Median over per-run timers; falls back to TimerTotal if no Timer_k found."""
    timers = extract_timers(filepath)
    if timers:
        return statistics.median(timers)
    return extract_timer_total(filepath)


def find_file(algo, graph, rank):
    candidates = [
        os.path.join(RESULTS_DIR, f"result_{algo}_{graph}_{rank}"),
        os.path.join(RESULTS_DIR, f"result_{algo}_{graph}_{rank}.txt"),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    matches = glob.glob(os.path.join(RESULTS_DIR, f"result_{algo}_{graph}_{rank}*"))
    return matches[0] if matches else None


def build_table(algo, graphs):
    table = defaultdict(dict)
    for graph in graphs:
        for rank in RANKS:
            path = find_file(algo, graph, rank)
            table[graph][rank] = extract_median(path) if path else None
    return table


def fmt_time(v):
    if v is None:
        return "N/A"
    return f"{int(v + 0.5)}"


def compute_ratio(table, graphs):
    """ratio = T_n1 / T_rank  (higher is better; n1 is 1.00)"""
    ratio = defaultdict(dict)
    for graph in graphs:
        base = table[graph].get("n1")
        for rank in RANKS:
            val = table[graph].get(rank)
            if base is None or val is None or val == 0:
                ratio[graph][rank] = None
            else:
                ratio[graph][rank] = base / val
    return ratio


def cell(time_val, ratio_val):
    if time_val is None:
        return "N/A"
    if ratio_val is None:
        return fmt_time(time_val)
    return f"{fmt_time(time_val)} ({ratio_val:.2f})"


def print_table(algo, graphs, table, ratio):
    col_w = 20
    graph_w = max(len(g) for g in graphs) + 2

    header = "Graph".ljust(graph_w) + "".join(r.rjust(col_w) for r in RANKS)
    line = "=" * len(header)

    print(line)
    print(f"Algorithm: {algo.upper()}  -  median of Timer_k (ms) [T_n1 / T_rank]")
    print("  ratio > 1 = faster than n1, < 1 = slower")
    print(line)
    print(header)
    print("-" * len(header))

    for graph in graphs:
        row = graph.ljust(graph_w)
        for rank in RANKS:
            row += cell(table[graph].get(rank), ratio[graph].get(rank)).rjust(col_w)
        print(row)
    print()


def main():
    for algo in ALGORITHMS:
        graphs = GRAPHS_BY_ALGO.get(algo, ALL_GRAPHS)
        table = build_table(algo, graphs)
        ratio = compute_ratio(table, graphs)
        print_table(algo, graphs, table, ratio)


if __name__ == "__main__":
    main()
