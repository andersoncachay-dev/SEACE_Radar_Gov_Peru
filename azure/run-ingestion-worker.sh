#!/bin/sh
set -eu

exec python -m backend.app.ingestion_worker
