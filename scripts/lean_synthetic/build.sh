#!/usr/bin/env bash
# Prepare a local image from the repository's exact upstream source pin.
set -euo pipefail
pin=9ecfed98339c27849a2a708edc03455caf151e91
source_checkout=${1:?Usage: bash scripts/lean_synthetic/build.sh /path/to/pinned/Lean}
asset_directory=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
if [[ "$(git -C "$source_checkout" rev-parse HEAD)" != "$pin" ]]; then
    echo "Expected the QuantConnect Lean checkout at $pin" >&2
    exit 1
fi
context=$(mktemp -d)
trap 'rm -rf -- "$context"' EXIT
mkdir -p "$context/lean"
git -C "$source_checkout" archive "$pin" -- . ':(exclude)Data' | tar -x -C "$context/lean"
git -C "$source_checkout" archive "$pin" -- \
    Data/market-hours/market-hours-database.json \
    Data/symbol-properties/symbol-properties-database.csv | tar -x -C "$context/lean"
cp -- "$asset_directory/Dockerfile" "$asset_directory/NrfxSyntheticAlgorithm.cs" \
    "$asset_directory/entrypoint.sh" "$context/"
docker build --build-arg "LEAN_COMMIT=$pin" --iidfile "$context/image-id" "$context" >&2
cat "$context/image-id"
