#!/bin/bash
set -e

echo "================================================"
echo "  ArXiv Daily Researcher - Docker Container"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "================================================"

# Configuration with defaults
CRON_SCHEDULE="${CRON_SCHEDULE:-0 8 * * *}"
RUN_ON_STARTUP="${RUN_ON_STARTUP:-false}"
MODE="${MODE:-cron}"

echo "Mode: $MODE"
echo "Timezone: $TZ"
echo "Cron Schedule: $CRON_SCHEDULE"
echo "Run on Startup: $RUN_ON_STARTUP"

# Ensure data directories exist
mkdir -p /app/data/reports/daily_research/markdown \
         /app/data/reports/daily_research/html \
         /app/data/reports/trend_research/markdown \
         /app/data/reports/trend_research/html \
         /app/data/reports/keyword_trend/markdown \
         /app/data/reports/keyword_trend/html \
         /app/data/history \
         /app/data/reference_pdfs /app/data/downloaded_pdfs \
         /app/logs

# Clean up stale log files
LOG_KEEP_DAYS="${LOG_KEEP_DAYS:-30}"
find /app/logs -name "cron_*.log" -type f -mtime +${LOG_KEEP_DAYS} -delete 2>/dev/null || true
find /app/logs -name "startup_*.log" -type f -mtime +${LOG_KEEP_DAYS} -delete 2>/dev/null || true
find /app/logs -name "daily_*.log" -type f -mtime +${LOG_KEEP_DAYS} -delete 2>/dev/null || true
find /app/logs -name "trend_*.log" -type f -mtime +${LOG_KEEP_DAYS} -delete 2>/dev/null || true

# ==================== Interactive Setup Wizard ====================
# Run setup wizard on first deployment (no .env file) or when SETUP_WIZARD=true
SETUP_WIZARD="${SETUP_WIZARD:-auto}"
if [ "$SETUP_WIZARD" = "true" ]; then
    echo ""
    echo "Running interactive setup wizard..."
    cd /app && python src/utils/setup_wizard.py
    echo "Setup wizard complete."
    echo ""
elif [ "$SETUP_WIZARD" = "auto" ] && [ ! -f /app/.env ]; then
    echo ""
    echo "No .env file detected — first deployment."
    echo "Running interactive setup wizard..."
    cd /app && python src/utils/setup_wizard.py
    echo "Setup wizard complete."
    echo ""
fi

# ==================== Single Execution Mode ====================
if [ "$MODE" = "run-once" ]; then
    LOG_FILE="/app/logs/cron_$(date +%Y%m%d_%H%M%S).log"
    echo "Running in single-execution mode..."
    echo "Log: $LOG_FILE"
    cd /app && python main.py 2>&1 | tee "$LOG_FILE"
    exit ${PIPESTATUS[0]}
fi

# ==================== Cron Mode ====================

# Export environment variables for cron
# (cron does not inherit the container's environment by default)
printenv | grep -v "no_proxy" > /etc/environment

# Create the cron job
CRON_LOG="/app/logs/cron_\$(date +\%Y\%m\%d_\%H\%M\%S).log"
CRON_CMD="cd /app && /usr/local/bin/python main.py >> $CRON_LOG 2>&1"
echo "$CRON_SCHEDULE $CRON_CMD" > /etc/cron.d/arxiv-daily
chmod 0644 /etc/cron.d/arxiv-daily
crontab /etc/cron.d/arxiv-daily

echo "Cron job installed:"
crontab -l

# Run immediately on startup if configured
if [ "$RUN_ON_STARTUP" = "true" ]; then
    echo ""
    echo "Running initial execution..."
    cd /app && python main.py 2>&1 | tee /app/logs/startup_$(date +%Y%m%d_%H%M%S).log
    echo "Initial execution complete."
    echo ""
fi

# ==================== WebUI Trigger File Watcher ====================
# The Streamlit config panel (WebUI container) can request a run by writing
# a trigger file to the shared volume.  This background loop picks it up.
TRIGGER_FILE="/app/data/run/webui_run_trigger.flag"
mkdir -p /app/data/run

trigger_watcher() {
    echo "[trigger-watcher] Started. Polling $TRIGGER_FILE every 5s..."
    while true; do
        if [ -f "$TRIGGER_FILE" ]; then
            # Read mode from trigger file
            RUN_MODE=$(cat "$TRIGGER_FILE" 2>/dev/null | tr -d '[:space:]')
            [ -z "$RUN_MODE" ] && RUN_MODE="daily_research"
            rm -f "$TRIGGER_FILE"
            echo "[trigger-watcher] Trigger received! mode=$RUN_MODE"

            # Use manual_ prefix to distinguish WebUI-triggered runs from cron runs
            LOG_FILE="/app/logs/manual_$(date +%Y%m%d_%H%M%S).log"
            PID_FILE="/app/data/run/webui_triggered.pid"

            # Launch python directly (no subshell) so $! is the actual Python PID
            cd /app && python main.py --mode "$RUN_MODE" >> "$LOG_FILE" 2>&1 &
            MAIN_PID=$!
            echo "$MAIN_PID" > "$PID_FILE"
            echo "[trigger-watcher] Launched PID=$MAIN_PID  log=$LOG_FILE"
        fi
        sleep 5
    done
}

trigger_watcher &

# Start cron daemon
echo "Starting cron daemon..."
cron

# Keep container alive
echo "Container is running. Waiting for scheduled executions..."
echo "Schedule: $CRON_SCHEDULE"
echo ""

# Tail the system log to keep container alive and show output
touch /app/logs/system.log
tail -f /app/logs/system.log
