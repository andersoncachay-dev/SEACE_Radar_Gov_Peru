#!/bin/sh
set -eu

exec python -m backend.app.tracking_date_refresh_worker
