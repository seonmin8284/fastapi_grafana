#!/bin/sh
set -e

echo "Starting services..."

echo "Starting Prometheus..."
/usr/local/bin/prometheus --config.file=/etc/prometheus/prometheus.yml --storage.tsdb.path=/prometheus &

echo "Starting Grafana..."
exec /usr/sbin/grafana-server --config=/etc/grafana/grafana.ini --homepath=/usr/share/grafana
