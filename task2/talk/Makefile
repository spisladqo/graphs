TALK ?= talk
ENGINE ?= xelatex # Only `xelatex` or `lualatex` are allowed here

.PHONY: all clean dist-clean figures
.SUFFIXES: .pdf .tex

all: $(TALK).pdf

# Графики строятся из ../results скриптом ../make_speedup.py
figures:
	python3 ../make_speedup.py ../results ../figs
	python3 ../make_phases.py ../results ../figs
	python3 ../make_hosts.py ../results ../figs
	python3 ../make_cache.py ../perf_cache.csv ../figs
	cp ../figs/speedup_all.pdf \
	   ../figs/speedup_bfs.pdf ../figs/speedup_sssp.pdf \
	   ../figs/speedup_pagerank.pdf ../figs/speedup_tc.pdf \
	   ../figs/time_bfs_graphs.pdf ../figs/time_sssp_graphs.pdf \
	   ../figs/time_pagerank_graphs.pdf ../figs/time_tc_graphs.pdf \
	   ../figs/phases_bfs.pdf ../figs/phases_sssp.pdf \
	   ../figs/phases_pagerank.pdf ../figs/phases_tc.pdf \
	   ../figs/bfs_hosts.pdf \
	   ../figs/cache_bfs.pdf ../figs/cache_sssp.pdf \
	   ../figs/speedup.csv ../figs/phases.csv ../figs/cache.csv figures/

%.pdf: %.tex *.tex figures/*.pdf
	latexmk -$(ENGINE) -synctex=1 -interaction=nonstopmode -file-line-error -shell-escape $<

clean:
	latexmk -c $(TALK).tex
	@$(RM) *.nav *.snm *.vrb *.synctex.gz

dist-clean: clean
	latexmk -C $(TALK).tex
