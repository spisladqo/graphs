from pathlib import Path
import os
import subprocess

env = os.environ.copy()
env["GALOIS_DO_NOT_BIND_THREADS"] = "1"
env["PRINT_PER_HOST_STATS"] = "1"

curr_dir = Path(__file__).parent.resolve()
data_dir = curr_dir / "data"

galois_dir = curr_dir / "Galois/build/lonestar/analytics/distributed"

algos_paths = [
    galois_dir / "bfs/bfs-pull-dist",
]

def pick_median_vertex_from_edgelist(edgelist: Path) -> int:
    outdeg: dict[int, int] = {}
    with edgelist.open() as handle:
        for line in handle:
            parts = line.split()
            if len(parts) < 2:
                continue
            src_id = int(parts[0])
            dst_id = int(parts[1])
            if src_id == dst_id:
                continue
            outdeg[src_id] = outdeg.get(src_id, 0) + 1
    if not outdeg:
        return 0
    ranked = sorted(outdeg, key=lambda vertex: (outdeg[vertex], vertex))
    return ranked[len(ranked) // 2]


def cached_median_vertex(graph: str, graph_el: Path) -> int:
    cache_path = data_dir / graph / "median_vertex.txt"

    if cache_path.is_file():
        text = cache_path.read_text().strip()
        if text:
            try:
                vert = int(text)
                print(f"  median vertex (cached): {vert}")
                return vert
            except ValueError:
                print(f"  WARNING: bad cache in {cache_path}, recomputing")

    if not graph_el.is_file():
        raise FileNotFoundError(f"missing edgelist: {graph_el}")

    vert = pick_median_vertex_from_edgelist(graph_el)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(f"{vert}\n")
    print(f"  median vertex: {vert} (cached to {cache_path})")
    return vert


print(f"GALOIS_DO_NOT_BIND_THREADS={env["GALOIS_DO_NOT_BIND_THREADS"]}")
print(f"PRINT_PER_HOST_STATS={env["PRINT_PER_HOST_STATS"]}")

def run_cmd(cmd: list[str], output_file: Path) -> int:
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=env,
        cwd=curr_dir,
    )

    with output_file.open("w") as f:
        f.write(f"# command: {' '.join(cmd)}\n")
        f.write(f"# returncode: {result.returncode}\n")
        f.write(result.stdout)
        if result.stderr:
            f.write("\n# ---- STDERR ----\n")
            f.write(result.stderr)

    return result.returncode


graph_names = [
   #   "belgium_osm",
   #  "rgg_n_2_22_s0",
   # "soc-LiveJournal1",
#     "amazon-2008",
#     "roadNet-CA",
    "coPapersDBLP",
     ]

ns = [
    1,
    2,
    3,
    4,
    5,
    6,
   # 8
]
algos = [
   #  ("./Galois/build/lonestar/analytics/distributed/bfs/bfs-push-dist", "bfs"),
   # ("./Galois/build/lonestar/analytics/distributed/sssp/sssp-push-dist", "sssp"),
     ("./Galois/build/lonestar/analytics/distributed/triangle-counting/triangle-counting-dist", "tc"),
#     ("./Galois/build/lonestar/analytics/distributed/pagerank/pagerank-pull-dist", "pagerank")
]
runs = 10 
results_dir = curr_dir / "results"



def run_all():
    for algo, algo_name in algos:
        print("Algo: ", algo_name)

        for graph in graph_names:
            print(f"Graph: {graph}")
            if algo_name == "tc" and graph in ["soc-LiveJournal1", "amazon-2008", "cit-Patents"]:
                print(f"{graph} is directed, skipping")
                continue

            graph_el = data_dir / graph / (graph + ".el")
            graph_gr = data_dir / graph / (graph + ".gr")
            graph_tgr = data_dir / graph / (graph + ".tgr")
            graph_wgr = data_dir / graph / (graph + ".wgr")
            graph_twgr = data_dir / graph / (graph + ".twgr")

            if graph_gr.exists():
                print("  path: ", graph_gr)
            else:
                print("  graph not found!")
                return -1

            print(f"  Finding median vertex...")
            # vert = pick_median_vertex_from_edgelist(graph_el)
            vert = cached_median_vertex(graph, graph_el)

            for n in ns:
                print("n: ", n)

                if algo_name == "bfs":
                    cmd = [
                        "mpirun",
   #                     "--use-hwthread-cpus",
                        "-n", str(n),
                        # "--oversubscribe",
                        "--map-by", "core", "--bind-to", "core",
                        str(algo),
                        str(graph_gr),
                        f"-startNode={vert}",
                        f"-runs={runs}",
                        f"-graphTranspose={graph_tgr}",
                        "-maxIterations=10000",
                        "-t=1",
                        "-partition=oec",
                        "-exec=Sync",
                    ]
                elif algo_name == "sssp":
                    cmd = [
                        "mpirun",
                       #"--use-hwthread-cpus",
                        "-n", str(n),
                       # "--oversubscribe",
                        "--map-by", "core", "--bind-to", "core", 
                        str(algo),
                        str(graph_wgr),
                        f"-startNode={vert}",
                        f"-runs={runs}",
                        f"-graphTranspose={graph_twgr}",
                        "-maxIterations=10000",
                        "-t=1",
                        "-partition=oec",
                        "-exec=Sync",
                    ]
                elif algo_name == "tc":
                    cmd = [
                        "mpirun",
                       # "--use-hwthread-cpus",
                        "-n", str(n),
                       # "--oversubscribe",
                        "--map-by", "core", "--bind-to", "core", 
                        str(algo),
                        str(graph_gr),
                        f"-runs={runs}",
                        "-t=1",
                        "-symmetricGraph",
                        "-partition=oec",
                    ]
                else:
                    cmd = [
                        "mpirun",
                        # "--use-hwthread-cpus",
                        "-n", str(n),
                       # "--oversubscribe",
                        "--map-by", "core", "--bind-to", "core",
                        str(algo),
                        str(graph_gr),
                        f"-runs={runs}",
                        f"-graphTranspose={graph_tgr}",
                        "-t=1",
                        "-partition=oec",
                        "-exec=Sync",
                    ]

                result_file = results_dir / f"result_{algo_name}_{graph}_n{n}_hosts.txt" 

                print(f"Running: {' '.join(cmd)}")

                res = run_cmd(cmd, result_file)
                print("Return code: ", res)
                if res < 0:
                    print("Fail!")
                else:
                    print("Success!")
                print("Result written to: ", result_file)

run_all()
