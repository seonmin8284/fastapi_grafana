FROM python:3.9-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    wget \
    curl \
    gnupg2 \
    && rm -rf /var/lib/apt/lists/*

# Install Prometheus
RUN wget https://github.com/prometheus/prometheus/releases/download/v2.47.2/prometheus-2.47.2.linux-amd64.tar.gz \
    && tar xvfz prometheus-2.47.2.linux-amd64.tar.gz \
    && mv prometheus-2.47.2.linux-amd64/prometheus /usr/local/bin/ \
    && mv prometheus-2.47.2.linux-amd64/promtool /usr/local/bin/ \
    && mkdir -p /etc/prometheus \
    && mv prometheus-2.47.2.linux-amd64/prometheus.yml /etc/prometheus/ \
    && rm -rf prometheus-2.47.2.linux-amd64*

# Install Grafana
RUN curl -fsSL https://packages.grafana.com/gpg.key | gpg --dearmor -o /usr/share/keyrings/grafana-archive-keyring.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/grafana-archive-keyring.gpg] https://packages.grafana.com/oss/deb stable main" | tee /etc/apt/sources.list.d/grafana.list \
    && apt-get update \
    && apt-get install -y grafana \
    && rm -rf /var/lib/apt/lists/*

# Create Grafana directories and set permissions
RUN mkdir -p /var/lib/grafana \
    && mkdir -p /var/log/grafana \
    && mkdir -p /var/lib/grafana/plugins \
    && mkdir -p /var/run/grafana \
    && mkdir -p /var/lib/grafana/dashboards \
    && mkdir -p /etc/grafana/provisioning/dashboards \
    && mkdir -p /etc/grafana/provisioning/datasources

# Copy entrypoint script
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

# Copy configuration files
COPY grafana/provisioning/dashboards/default.yml /etc/grafana/provisioning/dashboards/
COPY grafana/provisioning/datasources/datasource.yml /etc/grafana/provisioning/datasources/
COPY grafana/dashboards/fastapi_metrics_dashboard.json /var/lib/grafana/dashboards/
COPY grafana/grafana.ini /etc/grafana/grafana.ini
COPY prometheus.yml /etc/prometheus/prometheus.yml

# Expose Prometheus and Grafana ports
EXPOSE 9090 3000

ENTRYPOINT ["./entrypoint.sh"]
