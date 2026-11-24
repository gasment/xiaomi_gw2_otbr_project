#!/bin/sh
set -eu
cd "$(dirname "$0")"
command -v go >/dev/null 2>&1 || { echo 'Go 1.20+ is required only for the matching gopher-lua tests.' >&2; exit 1; }
go test -mod=readonly -v ./...
