# Масштабируемость распределённого Galois (D-Galois)

Задача 2 «Распределённая обработка графов»: оценка сильной масштабируемости BFS,
SSSP, PageRank и подсчёта треугольников (TC) в [D-Galois](https://github.com/IntelligentSoftwareSystems/Galois/tree/master/lonestar/analytics/distributed)
по числу MPI-процессов P = 1...6 и разбор того, от чего ускорение зависит.

```
task2/          скрипты запусков и обработки, графики
task2/Galois/   клон апстрима Galois (master, b67f9420) + каталог сборки build/
task2/figs/     графики (pdf + png) и таблицы csv
```

Каталоги `task2/data/` (датасеты) и `task2/results/` (логи запусков) появляются
после запуска скриптов и в git не хранятся.

## Сборка

Зависимости: CMake, GCC, Boost, LLVM, Open MPI, Python 3 с `matplotlib` и `numpy`.

```bash
cd task2
git clone https://github.com/IntelligentSoftwareSystems/Galois.git Galois
cmake -S Galois -B Galois/build -DCMAKE_BUILD_TYPE=Release -DGALOIS_ENABLE_DIST=ON
cmake --build Galois/build -j12
```

Собранные бинарники (`Galois/build/lonestar/analytics/distributed/`):

```
bfs/bfs-push-dist              sssp/sssp-push-dist
sssp/sssp-pull-dist            pagerank/pagerank-pull-dist
                               triangle-counting/triangle-counting-dist
```

и `Galois/build/tools/graph-convert/graph-convert`, конвертер форматов
(используется в `convert.sh`).

В экспериментах использовались push-варианты BFS и SSSP, pull-вариант PageRank
и `triangle-counting-dist`. Варианта `pagerank-push-dist` в этой сборке нет.

## Данные

```bash
cd task2
./convert.sh     # скачать 8 датасетов и сконвертировать MTX в бинарный формат Galois
```

Для каждого графа получаются `.el` (список рёбер), `.gr`/`.tgr` (граф и его
транспонированная копия) и `.wgr`/`.twgr` (то же с весами, для SSSP).

## Что тестировалось

**Стенд:** Intel Core i7-10750H (6 ядер / 12 потоков, 8 ГБ DDR4), Ubuntu 24.04,
GCC 13.3, Open MPI 4.1.6, Galois `b67f9420` (`Release`).

**Методика:**

* P = 1...6 MPI-рангов, по одному потоку Galois на ранк, каждый ранг привязан к
  своему ядру: `--map-by core --bind-to core`;
* режим `--exec=Sync` (раунд BSP: счёт, sync зеркал, Allreduce), `-t=1`,
  разбиение `-partition=oec`;
* время: медиана таймеров Galois (`Timer_N`) внутри алгоритма, без чтения и
  разбиения графа; `-runs=10` для BFS/SSSP, `-runs=15` для PageRank/TC;
* для BFS и SSSP источник обхода: вершина медианной исходящей степени;
* промахи кэшей: `perf stat` (`L1-dcache-load-misses`, `LLC-load-misses`);
* граф фиксирован, растёт число рангов P: ускорение `S(P) = T(1)/T(P)`, идеал `S(P) = P`.

**Графы:**

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

Для TC нужны симметричные графы без петель: `rgg_n_2_22_s0`, `belgium_osm`,
`coAuthorsCiteseer`, `roadNet-CA`, `coPapersDBLP` (при конвертации
симметризуются). Ориентированные `soc-LiveJournal1`, `amazon-2008`,
`cit-Patents` в TC пропускаются.

**Алгоритмы и флаги:**

| Алгоритм | Бинарник | Файлы графа | Особые флаги |
| --- | --- | --- | --- |
| BFS | `bfs-push-dist` | `.gr` + `.tgr` | `-startNode`, `-maxIterations=10000` |
| SSSP | `sssp-push-dist` | `.wgr` + `.twgr` | `-startNode`, `-maxIterations=10000` |
| PageRank | `pagerank-pull-dist` | `.gr` + `.tgr` | `-maxIterations=10000` |
| TC | `triangle-counting-dist` | `.gr` | `-symmetricGraph` (стартовый узел не принимается) |

## Запуск экспериментов

```bash
cd task2
python3 run.py
```

Список графов, числа рангов, алгоритмы и число прогонов задаются в коде
(`graph_names`, `ns`, `algos`, `runs`), путь к бинарнику тоже в `algos`
(`run.py:100-105`). В `algos` оставлен `triangle-counting-dist`, варианты
`bfs-push-dist`, `sssp-push-dist` и `pagerank-pull-dist` закомментированы.
Под каждым запуском:

```bash
mpirun -n P --map-by core --bind-to core \
  ./Galois/build/lonestar/analytics/distributed/bfs/bfs-push-dist \
  data/<граф>/<граф>.gr -startNode=<вершина> -runs=10 \
  -graphTranspose=data/<граф>/<граф>.tgr \
  -maxIterations=10000 -t=1 -partition=oec -exec=Sync
```

Логи пишутся в `results/result_<algo>_<graph>_n<P>[_hosts].txt`, суффикс
`_hosts` означает прогон с `PRINT_PER_HOST_STATS=1` (значения по каждому рангу).
Сводка по всем результатам:

```bash
cd task2
python3 show_results.py       # таблица: время в мс и отношение T(1)/T(P)
```

## Анализ и графики

Скрипты принимают каталог результатов и каталог для картинок позиционно
(по умолчанию `results` и `figs`), запускать из `task2/`.

```bash
cd task2
python3 make_speedup.py [results] [figs]   # ускорение и время по P
python3 make_phases.py  [results] [figs]   # вычисления / обмен по фазам
python3 make_hosts.py   [results] [figs]   # время по рангам при P = 6
python3 make_cache.py   [csv ...] [-o figs]   # промахи кэшей
```

| Скрипт | Рисунки | Таблица |
| --- | --- | --- |
| `make_speedup.py` | `speedup_all`, `speedup_<algo>`, `time_all`, `time_<algo>`, `time_<algo>_log`, `time_<algo>_graphs` (pdf + png) | `speedup.csv`: `algo,graph,P,T_ms,T_min_ms,T_max_ms,speedup` |
| `make_phases.py` | `phases_<algo>` (pdf + png) | `phases.csv`: `algo,graph,P,total_ms,sync_ms,compute_ms,sync_share_%,rounds,runs` |
| `make_hosts.py` | `bfs_hosts`, `pagerank_hosts` (pdf + png) | |
| `make_cache.py` | `cache_bfs`, `cache_sssp`, `cache_tc`, `cache_pagerank` (pdf + png) | `cache.csv`: `algo,graph,event,P,total,per_rank_mean,max_over_min` |

Разбор результатов:

* время раунда: медиана значений `Timer_N` из региона алгоритма
  (`BFS`, `SSSP`, `PageRank`, `TC`), дополнительно min/max;
* фаза обмена: сумма `Gluon Sync_<ALGO>_<k>`, вычисления и ожидание: остаток
  от `Timer_N` (профайлер Galois не патчился, поэтому фазы огрублены до двух);
* ускорение `S(P) = T(1)/T(P)`, пунктир на графиках: идеал `S = P` и `T(1)/P`.

## Промахи кэшей

Счётчики `perf stat` снимаются **отдельно по каждому рангу** (обычный
`perf stat mpirun ...` измерял бы сам `mpirun`): каждый ранг запускается
обёрткой `sh -c 'exec perf stat ... -- "$@"'`.

```bash
cd task2
python3 perf_cache.py --graphs belgium_osm rgg_n_2_22_s0 soc-LiveJournal1 \
                       --ns 1 2 3 4 5 6 --algos bfs sssp
python3 perf_cache.py --graphs coPapersDBLP rgg_n_2_22_s0 soc-LiveJournal1 \
                       --ns 1 2 3 4 5 6 --algos tc pagerank --out perf_cache_tc_pr.csv
```

Результат: `perf_cache.csv` и `perf_cache_tc_pr.csv`
(`algo,graph,n,rank,event,value`, строки с `rank = -1` это сумма по рангам)
и сырые отчёты в `perf_raw/`.

Подробности разбора флагов по исходникам Galois, замечания к данным и
проверки корректности в `task2/experiments_graphs.txt`.
