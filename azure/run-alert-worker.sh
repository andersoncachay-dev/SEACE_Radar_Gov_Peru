#!/bin/sh
set -eu

exec python -m backend.app.alert_worker
