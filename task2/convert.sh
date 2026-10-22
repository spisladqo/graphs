#!/usr/bin/env bash
set -euo pipefail

DEST="data"
mkdir -p "$DEST"

GC="./Galois/build/tools/graph-convert/graph-convert"

# ---------- 1. Скачивание и распаковка ----------
URLS=(
  "http://media.githubusercontent.com/media/VyacheslavIurevich/graphs-theory-datasets/main/rgg_n_2_22_s0.tar.gz?download=1"
  "http://media.githubusercontent.com/media/VyacheslavIurevich/graphs-theory-datasets/main/soc-LiveJournal1.tar.gz?download=1"
  "http://media.githubusercontent.com/media/VyacheslavIurevich/graphs-theory-datasets/main/belgium_osm.tar.gz?download=1"
  "http://media.githubusercontent.com/media/VyacheslavIurevich/graphs-theory-datasets/main/cit-Patents.tar.gz?download=1"
  "http://media.githubusercontent.com/media/VyacheslavIurevich/graphs-theory-datasets/main/amazon-2008.tar.gz?download=1"
  "http://media.githubusercontent.com/media/VyacheslavIurevich/graphs-theory-datasets/main/coAuthorsCiteseer.tar.gz?download=1"
  "http://media.githubusercontent.com/media/VyacheslavIurevich/graphs-theory-datasets/main/roadNet-CA.tar.gz?download=1"
  "http://media.githubusercontent.com/media/VyacheslavIurevich/graphs-theory-datasets/main/coPapersDBLP.tar.gz?download=1"
)

for url in "${URLS[@]}"; do
  fname=$(basename "${url%%\?*}")
  archive="$DEST/$fname"
  name="${fname%.tar.gz}"
  extracted="$DEST/$name"

  if [[ -d "$extracted" ]]; then
    echo "==> [$name] already extracted at $extracted, skipping"
    continue
  fi

  if [[ -f "$archive" ]]; then
    echo "==> [$name] archive already exists, skipping download"
  else
    echo "==> Downloading $fname"
    curl -fL --retry 3 --retry-delay 2 -o "$archive" "$url"
  fi

  echo "==> Extracting $fname"
  tar -xzf "$archive" -C "$DEST"
done

# ---------- 2. Symmetric graph list ----------
SYMMETRIC_DATASETS=("rgg_n_2_22_s0" "belgium_osm" "coAuthorsCiteseer" "roadNet-CA" "coPapersDBLP")

is_symmetric() {
  local name="$1"
  for s in "${SYMMETRIC_DATASETS[@]}"; do
    [[ "$s" == "$name" ]] && return 0
  done
  return 1
}

# ---------- 3. Edgelist writers ----------
# Unweighted .el: "u v"
# Weighted   .el: "u v 1"  (MTX has no weights, stub weight=1)
# symmetric="yes" additionally writes the reverse (v,u) for every row.
write_edgelist() {
  local mtx="$1"
  local el="$2"
  local symmetric="$3"   # "yes" | "no"
  local weighted="$4"    # "yes" | "no"

  awk -v expand="$symmetric" -v w="$weighted" '
    NR==1 { next }
    /^%/  { next }
    # skip the size line (exactly 3 fields, once)
    NF==3 && !s { s=1; next }
    NF>=2 {
      u = $1 - 1
      v = $2 - 1
      if (u == v) next
      if (w == "yes") {
        print u, v, 1
        if (expand == "yes") print v, u, 1
      } else {
        print u, v
        if (expand == "yes") print v, u
      }
    }
  ' "$mtx" > "$el"
}

convert_mtx_to_gr() {
  local mtx="$1"
  local base="${mtx%.mtx}"
  local name
  name=$(basename "$base")
  local el="${base}.el"
  local wel="${base}.wel"
  local gr="${base}.gr"
  local tgr="${base}.tgr"
  local wgr="${base}.wgr"
  local twgr="${base}.twgr"

  local sym="no"
  if is_symmetric "$name"; then sym="yes"; fi

  # ---- Ensure .el exists (used by both .gr and .wgr) ----
  if [[ ! -s "$el" ]]; then
    echo "==> Converting $mtx -> $el (symmetric=$sym)"
    write_edgelist "$mtx" "$el" "$sym" "no"
    echo "    lines in .el: $(wc -l < "$el")"
  else
    echo "==> [$base] $el already exists, reusing"
  fi

  # ---- Ensure .wel exists ----
  if [[ ! -s "$wel" ]]; then
    echo "==> Converting $mtx -> $wel (symmetric=$sym, weighted)"
    write_edgelist "$mtx" "$wel" "$sym" "yes"
    echo "    lines in .wel: $(wc -l < "$wel")"
  else
    echo "==> [$base] $wel already exists, reusing"
  fi

  # ---- Unweighted family (.gr + .tgr) ----
  if [[ -s "$gr" && -s "$tgr" ]]; then
    echo "==> [$base] .gr and .tgr already exist, skipping"
  else
    if [[ ! -s "$gr" ]]; then
      echo "==> Converting $el -> $gr"
      rm -f "$gr"
      "$GC" -edgelist2gr -edgeType=void "$el" "$gr"
    fi
    if [[ ! -s "$tgr" ]]; then
      echo "==> Transposing $gr -> $tgr"
      rm -f "$tgr"
      "$GC" -gr2tgr -edgeType=void "$gr" "$tgr"
    fi
  fi

  # ---- Weighted family (.wgr + .twgr) ----
  if [[ -s "$wgr" && -s "$twgr" ]]; then
    echo "==> [$base] .wgr and .twgr already exist, skipping"
  else
    if [[ ! -s "$wgr" ]]; then
      echo "==> Converting $wel -> $wgr"
      rm -f "$wgr"
      "$GC" -edgelist2gr -edgeType=uint32 "$wel" "$wgr"
    fi
    if [[ ! -s "$twgr" ]]; then
      echo "==> Transposing $wgr -> $twgr"
      rm -f "$twgr"
      "$GC" -gr2tgr -edgeType=uint32 "$wgr" "$twgr"
    fi
  fi

  ls -lh "$gr" "$tgr" "$wgr" "$twgr"
}

for mtx in \
  "$DEST"/soc-LiveJournal1/soc-LiveJournal1.mtx \
  "$DEST"/belgium_osm/belgium_osm.mtx \
  "$DEST"/cit-Patents/cit-Patents.mtx \
  "$DEST"/rgg_n_2_22_s0/rgg_n_2_22_s0.mtx \
  "$DEST"/roadNet-CA/roadNet-CA.mtx \
  "$DEST"/amazon-2008/amazon-2008.mtx \
  "$DEST"/coAuthorsCiteseer/coAuthorsCiteseer.mtx \
  "$DEST"/coPapersDBLP/coPapersDBLP.mtx \
  "$DEST"/roadNet-CA/roadNet-CA.mtx \
; do
  if [[ -f "$mtx" ]]; then
    convert_mtx_to_gr "$mtx"
  else
    echo "!! Skipping missing $mtx"
  fi
done

echo "Done. Contents of $DEST:"
ls -lh "$DEST"