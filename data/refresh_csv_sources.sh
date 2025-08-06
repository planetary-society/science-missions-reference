#!/bin/bash

# Array of URLs
URLS=(
  "https://docs.google.com/spreadsheets/d/1ag7otfTfElrFz-yRZEdp-sLxlwkS_p7gRvnD1tVo7fE/export?format=csv&gid=2093582436"
  "https://raw.githubusercontent.com/planetary-society/nssdca-catalog-scraper/3577a60c1032c2224a2ea280345b1f01548d2631/data/all_spacecraft_list.csv"
)

# Corresponding output filenames
FILENAMES=(
  "us_space_science_missions.csv"
  "all_spacecraft_list.csv"
)

# Download each file
for i in "${!URLS[@]}"; do
  echo "Downloading ${URLS[$i]} to ${FILENAMES[$i]}"
  curl -L -o "${FILENAMES[$i]}" "${URLS[$i]}"
done