#!/usr/bin/env bash

DEST="data"
mkdir -p "$DEST"

URLS=(
  "http://media.githubusercontent.com/media/VyacheslavIurevich/graphs-theory-datasets/main/rgg_n_2_22_s0.tar.gz?download=1"
  "http://media.githubusercontent.com/media/VyacheslavIurevich/graphs-theory-datasets/main/soc-LiveJournal1.tar.gz?download=1"
  "http://media.githubusercontent.com/media/VyacheslavIurevich/graphs-theory-datasets/main/belgium_osm.tar.gz?download=1"
  "http://media.githubusercontent.com/media/VyacheslavIurevich/graphs-theory-datasets/main/cit-Patents.tar.gz?download=1"
)

for url in "${URLS[@]}"; do
  fname=$(basename "${url%%\?*}")
  echo "==> Downloading $fname"
  curl -fL --retry 3 --retry-delay 2 -o "$DEST/$fname" "$url"

  echo "==> Extracting $fname"
  tar -xzf "$DEST/$fname" -C "$DEST"
done

echo "Done. Contents of $DEST:"
ls -lh "$DEST"