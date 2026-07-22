#!/bin/sh
set -eu

exec python -m backend.app.tracking_alerts_worker
