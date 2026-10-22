# Презентация: масштабируемость D-Galois

Сборка beamer-презентации по экспериментам из `../results` и `../perf_cache*.csv`.

```
make            # talk.pdf
make figures    # перестроить графики из ../results и ../perf_cache*.csv
                # и положить их в figures/
```

Файлы:

| Файл | Что это |
| --- | --- |
| `talk.tex` | текст презентации (20 слайдов) |
| `preamble.tex` | преамбула шаблона СПбГУ + макрос `\figcap` |
| `pretitle.tex`, `title.tex` | параметры титульного листа (`\filltitle{ru}{...}`) |
| `beamerthemeSPbGU.sty` | тема оформления |
| `figures/*.pdf` | рисунки (сгенерированы `../make_speedup.py`, `../make_phases.py`, `../make_hosts.py`, `../make_cache.py`) |
| `figures/speedup.csv` | полные времена и ускорения по всем прогонам |
| `figures/phases.csv` | времена и доли фаз (обмен / вычисления) |
| `figures/cache.csv` | промахи кэшей по рангам и коэффициент роста |

Данные для графиков: `../results/result_<algo>_<graph>_n<P>.txt`,
обработка — `../make_speedup.py` (медиана 15 прогонов, ускорение `S(P) = T(1)/T(P)`).

Графики промахов кэшей строятся из `../perf_cache.csv` (BFS, SSSP) и
`../perf_cache_tc_pr.csv` (TC, PageRank) скриптом `../make_cache.py`
(счётчики `perf stat` снимались отдельно для каждого ранга, в столбце — их сумма).

Графики «работа по рангам» (`bfs_hosts.pdf`, `pagerank_hosts.pdf`) строятся скриптом
`../make_hosts.py` из файлов `../results/result_<algo>_<graph>_n6_hosts.txt`:
вычисления — `PageRank_*`/`PageRank_delta_*` (pull и зеркалирование весов),
обмен — `Gluon Sync_<ALGO>_*`, остальное — остаток до `Timer_*`.
