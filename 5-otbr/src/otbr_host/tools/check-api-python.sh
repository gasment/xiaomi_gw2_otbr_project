#!/bin/sh
set -eu
if [ -n "${OTBR_API_TEST_PYTHON:-}" ]; then
    PYTHON=$OTBR_API_TEST_PYTHON
elif [ -n "${OTBR_TEST_PYTHON:-}" ]; then
    PYTHON=$OTBR_TEST_PYTHON
elif [ -n "${VIRTUAL_ENV:-}" ]; then
    PYTHON=$VIRTUAL_ENV/bin/python
else
    PYTHON=python3
fi
if ! command -v "$PYTHON" >/dev/null 2>&1; then
    echo 'API_TEST_PYTHON_MISSING: activate a Python environment or set OTBR_API_TEST_PYTHON.' >&2
    exit 1
fi
if ! "$PYTHON" -c 'import aioesphomeapi, yaml' >/dev/null 2>&1; then
    echo 'API_TEST_DEPENDENCIES_MISSING: selected Python cannot import aioesphomeapi and PyYAML.' >&2
    echo 'Activate an environment containing both packages, or set OTBR_API_TEST_PYTHON to its python executable.' >&2
    exit 1
fi
printf '%s\n' "$PYTHON"
