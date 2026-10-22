# Масштабируемость распределённого Galois (D-Galois)

Задача 2 «Распределённая обработка графов»: как ускоряются BFS, SSSP, PageRank
и подсчёт треугольников в D-Galois при росте числа MPI-процессов от 1 до 6.

```
task2/          скрипты запусков и обработки, графики
task2/Galois/   клон апстрима Galois (master, b67f9420) и каталог сборки build/
task2/figs/     графики (pdf и png) и таблицы csv
```

Датасеты в `task2/data/` и логи запусков в `task2/results/` в git не хранятся:
они появляются после запуска скриптов.

## Сборка

Нужны CMake, GCC, Boost, LLVM, Open MPI, Python 3 с matplotlib и numpy.

```bash
cd task2
git clone https://github.com/IntelligentSoftwareSystems/Galois.git Galois
cmake -S Galois -B Galois/build -DCMAKE_BUILD_TYPE=Release -DGALOIS_ENABLE_DIST=ON
cmake --build Galois/build -j12
```

После сборки в `Galois/build/lonestar/analytics/distributed/` лежат нужные
бинарники: `bfs-push-dist`, `sssp-push-dist`, `sssp-pull-dist`,
`pagerank-pull-dist` и `triangle-counting-dist`. Конвертер графиков собирается
в `Galois/build/tools/graph-convert/graph-convert`.

В опытах брались push-варианты BFS и SSSP, pull-вариант PageRank и
`triangle-counting-dist`.

## Данные

```bash
cd task2
./convert.sh
```

Скрипт скачивает 8 датасетов и конвертирует их из MTX в бинарный формат
Galois: `.el` со списком рёбер, `.gr` и `.tgr` с графом и его транспонированной
копией, `.wgr` и `.twgr` с тем же, но с весами для SSSP.

## Условия экспериментов

Стенд: Intel Core i7-10750H (6 ядер, 12 потоков, 8 ГБ DDR4), Ubuntu 24.04,
GCC 13.3, Open MPI 4.1.6, Galois `b67f9420` в режиме Release.

* от 1 до 6 MPI-рангов, по одному потоку Galois на ранг, ранги привязаны к своим ядрам;
* режим `--exec=Sync`: раунд со счётом, обменом зеркал и Allreduce, один поток,
  разбиение `-partition=oec`;
* время берётся из таймеров Galois `Timer_N` внутри алгоритма: медиана по
  10 прогонам для BFS и SSSP и по 15 для PageRank и TC;
* в BFS и SSSP обход начинается с вершины медианной исходящей степени;
* промахи кэшей снимаются через `perf stat`: `L1-dcache-load-misses`
  и `LLC-load-misses`;
* граф не меняется, растёт только число рангов, ускорение считается как
  `S(P) = T(1)/T(P)`.

Графы:

| Граф | Вершин | Рёбер | Ср. исх. степень | Тип | RF при P = 6 |
| --- | ---: | ---: | ---: | --- | ---: |
| `belgium_osm` | 1 441 295 | 3 099 940 | 2.15 | дорожный | 1.18 |
| `roadNet-CA` | 1 971 281 | 5 533 214 | 2.81 | дорожный | 1.02 |
| `rgg_n_2_22_s0` | 4 194 304 | 60 718 396 | 14.48 | случайный геометрический | 1.01 |
| `soc-LiveJournal1` | 4 847 571 | 68 993 773 | 14.23 | соцсеть | 3.05 |
| `coPapersDBLP` | 540 486 | 30 491 458 | 56.4 | соавторство | 1.82 |
| `amazon-2008` | 735 323 | 5 158 388 | 7.02 | копулярный | |
| `cit-Patents` | 3 774 768 | 16 518 948 | 4.38 | копулярный | |
| `coAuthorsCiteseer` | 227 320 | 1 628 268 | 7.16 | копулярный | |

Для TC берутся симметричные графы без петель: `rgg_n_2_22_s0`, `belgium_osm`,
`coAuthorsCiteseer`, `roadNet-CA`, `coPapersDBLP`. Ориентированные
`soc-LiveJournal1`, `amazon-2008` и `cit-Patents` в TC пропускаются.

Флаги запуска:

| Алгоритм | Бинарник | Файлы графа | Флаги |
| --- | --- | --- | --- |
| BFS | `bfs-push-dist` | `.gr` и `.tgr` | `-startNode`, `-maxIterations=10000` |
| SSSP | `sssp-push-dist` | `.wgr` и `.twgr` | `-startNode`, `-maxIterations=10000` |
| PageRank | `pagerank-pull-dist` | `.gr` и `.tgr` | `-maxIterations=10000` |
| TC | `triangle-counting-dist` | `.gr` | `-symmetricGraph` |

## Запуск экспериментов

```bash
cd task2
python3 run.py
```

Графы, числа рангов, алгоритмы и число прогонов задаются в начале `run.py`:
`graph_names`, `ns`, `algos` и `runs`. В `algos` оставлен `triangle-counting-dist`,
остальные варианты закомментированы. Каждый запуск выглядит так:

```bash
mpirun -n P --map-by core --bind-to core \
  ./Galois/build/lonestar/analytics/distributed/bfs/bfs-push-dist \
  data/<граф>/<граф>.gr -startNode=<вершина> -runs=10 \
  -graphTranspose=data/<граф>/<граф>.tgr \
  -maxIterations=10000 -t=1 -partition=oec -exec=Sync
```

Логи пишутся в `results/result_<algo>_<graph>_n<P>.txt`, а с `_hosts` на конце,
если прогон шёл с `PRINT_PER_HOST_STATS=1`. Сводка по всем логам:

```bash
cd task2
python3 show_results.py
```

## Графики

Скрипты запускаются из `task2/` и принимают каталог с результатами и каталог
для картинок.

```bash
cd task2
python3 make_speedup.py [results] [figs]   # ускорение и время по числу рангов
python3 make_phases.py  [results] [figs]   # вычисления и обмен по фазам
python3 make_hosts.py   [results] [figs]   # время по рангам при P = 6
python3 make_cache.py   [csv ...] [-o figs]   # промахи кэшей
```

| Скрипт | Рисунки | Таблица |
| --- | --- | --- |
| `make_speedup.py` | `speedup_all`, `speedup_<algo>`, `time_all`, `time_<algo>`, `time_<algo>_log`, `time_<algo>_graphs` | `speedup.csv`: `algo,graph,P,T_ms,T_min_ms,T_max_ms,speedup` |
| `make_phases.py` | `phases_<algo>` | `phases.csv`: `algo,graph,P,total_ms,sync_ms,compute_ms,sync_share_%,rounds,runs` |
| `make_hosts.py` | `bfs_hosts`, `pagerank_hosts` | |
| `make_cache.py` | `cache_bfs`, `cache_sssp`, `cache_tc`, `cache_pagerank` | `cache.csv`: `algo,graph,event,P,total,per_rank_mean,max_over_min` |

## Промахи кэшей

Счётчики `perf stat` снимаются по каждому рангу отдельно: каждый ранг
запускается обёрткой `sh -c 'exec perf stat ... -- "$@"'`.

```bash
cd task2
python3 perf_cache.py --graphs belgium_osm rgg_n_2_22_s0 soc-LiveJournal1 \
                       --ns 1 2 3 4 5 6 --algos bfs sssp
python3 perf_cache.py --graphs coPapersDBLP rgg_n_2_22_s0 soc-LiveJournal1 \
                       --ns 1 2 3 4 5 6 --algos tc pagerank --out perf_cache_tc_pr.csv
```

Счётчики складываются в `perf_cache.csv` и `perf_cache_tc_pr.csv`, сырые отчёты
лежат в `perf_raw/`.

Подробности в `task2/experiments_graphs.txt`.
