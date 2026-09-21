#!/usr/bin/env bash
# Build the Lambda deployment package.
#
# The runtime provides boto3 and nothing else is needed, so the zip is just
# our own source: the handler, the solver, and the catalog it reads. No pip
# install, no vendored wheels, no build container.
#
# Timestamps are pinned so that the same source produces the same zip. Without
# that, every build produces a new hash and Terraform redeploys a function
# whose code has not changed.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
build="$root/build"
stage="$build/lambda"
out="$build/lambda.zip"

rm -rf "$stage" "$out"
mkdir -p "$stage/data/menus" "$stage/solver"

cp "$root/lambda/handler.py" "$stage/"
cp "$root/solver/"*.py "$stage/solver/"
cp "$root/data/foods.json" "$root/data/aliases.json" "$stage/data/"
cp "$root/data/menus/"*.json "$stage/data/menus/"

find "$stage" -name '__pycache__' -type d -prune -exec rm -rf {} +
find "$stage" -exec touch -t 200001010000.00 {} +

( cd "$stage" && find . -type f | sort | zip -q -X -@ "$out" )

printf 'built %s (%s bytes)\n' "$out" "$(stat -c%s "$out")"
