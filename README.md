# Масштабируемость распределённого Galois (D-Galois)

Задача 2 «Распределённая обработка графов»: оценка сильной масштабируемости BFS,
SSSP, PageRank и подсчёта треугольников (TC) в [D-Galois](https://github.com/IntelligentSoftwareSystems/Galois/tree/master/lonestar/analytics/distributed)
по числу MPI-процессов P = 1…6 и разбор того, от чего ускорение зависит.
Презентация — [`task2/talk/talk.pdf`](task2/talk/talk.pdf) (17 слайдов, beamer).

```
task2/          скрипты запусков и обработки, графики, презентация
task2/Galois/   клон апстрима Galois (master, b67f9420) + каталог сборки build/
task2/figs/     графики (pdf + png) и таблицы csv
task2/talk/     презентация (шаблон СПбГУ)
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

и `Galois/build/tools/graph-convert/graph-convert` — конвертер форматов
(используется в `convert.sh`).

В экспериментах использовались push-варианты BFS и SSSP, pull-вариант PageRank
и `triangle-counting-dist`. Варианта `pagerank-push-dist` в этой сборке нет —
если он понадобится, добавьте `--target pagerank-push-dist`.

## Данные

```bash
cd task2
./convert.sh     # скачать 8 датасетов и сконвертировать MTX → бинарный формат Galois
```

Скрипт идемпотентен: уже скачанные архивы и готовые файлы не трогает.
Для каждого графа получаются `.el` (список рёбер), `.gr`/`.tgr` (граф и его
транспонированная копия) и `.wgr`/`.twgr` (то же с весами — для SSSP).

## Что тестировалось

**Стенд:** Intel Core i7-10750H (6 ядер / 12 потоков, 8 ГБ DDR4), Ubuntu 24.04,
GCC 13.3, Open MPI 4.1.6, Galois `b67f9420` (`Release`).

**Методика:**

* P = 1…6 MPI-рангов, по одному потоку Galois на ранк, каждый ранг привязан к
  своему ядру: `--map-by core --bind-to core`;
* режим `--exec=Sync` (раунд BSP: счёт → sync зеркал → Allreduce), `-t=1`,
  разбиение `-partition=oec`;
* время — медиана таймеров Galois (`Timer_N`) внутри алгоритма, без чтения и
  разбиения графа; `-runs=10` для BFS/SSSP, `-runs=15` для PageRank/TC;
* для BFS и SSSP источник обхода — вершина медианной исходящей степени;
* промахи кэшей — `perf stat` (`L1-dcache-load-misses`, `LLC-load-misses`);
* граф фиксирован, растёт число рангов P: ускорение `S(P) = T(1)/T(P)`, идеал `S(P) = P`.

**Графы:**

| Граф | Вершин | Рёбер | Ср. исх. степень | Тип | RF при P = 6 |
| --- | ---: | ---: | ---: | --- | ---: |
| `belgium_osm` | 1 441 295 | 3 099 940 | 2.15 | дорожный | 1.18 |
| `roadNet-CA` | 1 971 281 | 5 533 214 | 2.81 | дорожный | 1.02 |
| `rgg_n_2_22_s0` | 4 194 304 | 60 718 396 | 14.48 | случайный геометрический | 1.01 |
| `soc-LiveJournal1` | 4 847 571 | 68 993 773 | 14.23 | соцсеть | 3.05 |
| `coPapersDBLP` | 540 486 | 30 491 458 | 56.4 | соавторство | 1.82 |
| `amazon-2008` | 735 323 | 5 158 388 | 7.02 | копулярный | — |
| `cit-Patents` | 3 774 768 | 16 518 948 | 4.38 | копулярный | — |
| `coAuthorsCiteseer` | 227 320 | 1 628 268 | 7.16 | копулярный | — |

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
(`graph_names`, `ns`, `algos`, `runs`); путь к бинарнику — в `algos`
(`run.py:100-105`). В `algos` можно раскомментировать нужный вариант
(`bfs-push-dist`, `sssp-push-dist`, `pagerank-pull-dist`,
`triangle-counting-dist`), а для SSSP можно вместо push-варианта взять
pull-вариант. Под каждым запуском:

```bash
mpirun -n P --map-by core --bind-to core \
  ./Galois/build/lonestar/analytics/distributed/bfs/bfs-push-dist \
  data/<граф>/<граф>.gr -startNode=<вершина> -runs=10 \
  -graphTranspose=data/<граф>/<граф>.tgr \
  -maxIterations=10000 -t=1 -partition=oec -exec=Sync
```

Логи пишутся в `results/result_<algo>_<graph>_n<P>[_hosts].txt`; суффикс
`_hosts` — прогон с `PRINT_PER_HOST_STATS=1` (значения по каждому рангу).
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
python3 make_cache.py   [perf_cache.csv] [figs]   # промахи кэшей
```

| Скрипт | Рисунки | Таблица |
| --- | --- | --- |
| `make_speedup.py` | `speedup_all`, `speedup_<algo>`, `time_all`, `time_<algo>`, `time_<algo>_log`, `time_<algo>_graphs` (pdf + png) | `speedup.csv`: `algo,graph,P,T_ms,T_min_ms,T_max_ms,speedup` |
| `make_phases.py` | `phases_<algo>` (pdf + png) | `phases.csv`: `algo,graph,P,total_ms,sync_ms,compute_ms,sync_share_%,rounds,runs` |
| `make_hosts.py` | `bfs_hosts` (pdf + png) | — |
| `make_cache.py` | `cache_bfs`, `cache_sssp` (pdf + png) | `cache.csv`: `algo,graph,event,P,total,per_rank_mean,max_over_min` |

Разбор результатов:

* время раунда — медиана значений `Timer_N` из региона алгоритма
  (`BFS`, `SSSP`, `PageRank`, `TC`), дополнительно min/max;
* фаза обмена — сумма `Gluon Sync_<ALGO>_<k>`, вычисления и ожидание — остаток
  от `Timer_N` (профайлер Galois не патчился, поэтому фазы огрублены до двух);
* ускорение `S(P) = T(1)/T(P)`, пунктир на графиках — идеал `S = P` и `T(1)/P`.

## Промахи кэшей

Счётчики `perf stat` снимаются **отдельно по каждому рангу** (обычный
`perf stat mpirun ...` измерял бы сам `mpirun`): каждый ранг запускается
обёрткой `sh -c 'exec perf stat ... -- "$@"'`.

```bash
cd task2
python3 perf_cache.py --graphs belgium_osm rgg_n_2_22_s0 soc-LiveJournal1 \
                       --ns 1 2 3 4 5 6 --algos bfs sssp
```

Результат — `perf_cache.csv` (`algo,graph,n,rank,event,value`, строки с
`rank = -1` — сумма по рангам) и сырые отчёты в `perf_raw/`.

## Презентация

```bash
cd task2/talk
make figures   # перестроить графики из ../results и ../perf_cache.csv
make           # talk.pdf, нужен XeLaTeX и шрифты CMU
```

`make figures` зовёт `../make_speedup.py`, `../make_phases.py`,
`../make_hosts.py`, `../make_cache.py` и копирует pdf-рисунки и csv-таблицы
в `talk/figures/`.

Структура доклада: постановка задачи → как считает D-Galois (разбиение OEC,
зеркала, RF, раунд BSP) → стенд и методика → набор данных → ускорение всех
алгоритмов → по алгоритмам (время, фазы, промахи кэшей, работа по рангам) →
результаты и ограничения.

## Результаты

Ускорение при P = 6 (`S(6) = T(1)/T(6)`):

| Алгоритм | Граф | Время T(1) → T(6), с | S(6) |
| --- | --- | --- | ---: |
| TC | `roadNet-CA` | — | 4.90 |
| TC | `rgg_n_2_22_s0` | — | 4.49 |
| PageRank | `roadNet-CA` | 6.39 → 1.44 | 4.45 |
| PageRank | `rgg_n_2_22_s0` | 29.02 → 7.47 | 3.88 |
| TC | `coPapersDBLP` | 29.0 → 13.0 | 2.24 |
| BFS | `belgium_osm` | 4.54 → 1.79 | 2.53 |
| SSSP | `belgium_osm` | 5.60 → 2.13 | 2.63 |
| BFS | `rgg_n_2_22_s0` | 10.98 → 6.24 | 1.76 |
| SSSP | `rgg_n_2_22_s0` | 12.51 → 7.55 | 1.66 |
| BFS | `soc-LiveJournal1` | 2.76 → 2.18 | 1.26 |
| SSSP | `soc-LiveJournal1` | 3.08 → 2.35 | 1.31 |
| PageRank | `soc-LiveJournal1` | 107.64 → 60.42 | 1.78 |

От чего зависит ускорение:

* **наличие раундов и обмена** — TC делает один проход по мастерам и одно
  сложение (Allreduce), поэтому делится почти идеально на малых графах;
  BFS и SSSP упираются в барьер каждого раунда и обмен зеркалами (`S(6) = 1.3…2.6`);
* **средняя степень** — чем она выше, тем хуже ускорение: 2.5 на `belgium_osm`
  против 1.76 на RGG (степень 14.5);
* **хабы и однородность графа** — на `soc-LiveJournal1` RF = 3.05, зеркала хабов
  есть на всех рангах, ускорение 1.26 (BFS) и 1.31 (SSSP);
* **промахи кэшей** растут с числом рангов в 1.1…5.2 раза: на `belgium_osm`
  промахи L1 217 → 324 млн (×1.49), на LiveJournal ×3.08 по L1 и ×5.24 по LLC;
* **дисбаланс работы** — при P = 6 на RGG ранги 0 и 3 получают 335 и 284 млн
  обработок против 11–38 млн у остальных, на `coPapersDBLP` времена рангов
  10.3 / 13.3 / 11.6 / 8.9 / 6.0 / 3.1 с.

Ограничение: все измерения сделаны на одной машине, обмен рангов идёт через
общую память.

Подробности разбора флагов по исходникам Galois, замечания к данным и
проверки корректности — в `task2/experiments_graphs.txt`.
