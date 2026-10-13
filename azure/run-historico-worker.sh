#!/bin/sh
set -eu

exec python -m backend.app.historico_worker
