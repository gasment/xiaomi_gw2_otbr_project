#!/bin/sh
set -eu
cd "$(dirname "$0")"
[ "$#" -eq 0 ] || { echo 'Runtime YAML is edited on the gateway; build-release.sh takes no configuration file.' >&2; exit 2; }
OTBR_API_TEST_PYTHON=$(sh tools/check-api-python.sh)
export OTBR_API_TEST_PYTHON
python3 tools/verify_release_deps.py
python3 tools/check_project_privacy.py
sh build-checks.sh native
python3 tests/deploy_scripts.py
python3 tests/rcp_recovery.py
python3 tests/rcp_recovery_update.py
sh build-web.sh
sh test-web.sh
sh build-api.sh native
sh test-api.sh
sh build-proxy.sh
sh test-proxy.sh
sh build-host.sh arm
python3 tools/check_noise_symbols.py
python3 tools/package_deploy.py
if [ "${OTBR_HOST_PROFILE:-stable}" = bbr ]; then
  echo 'RELEASE_READY: upload otbr-deploy-bbr.tar.gz to gateway /tmp and run otbr-deploy/install.sh.'
else
  echo 'RELEASE_READY: upload otbr-deploy.tar.gz to gateway /tmp and run otbr-deploy/install.sh.'
fi
