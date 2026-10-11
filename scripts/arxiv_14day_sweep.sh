#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
container_name="arxiv-14day-sweep"
image_name="arxiv-daily-researcher-test-worker:local"
log_file="$repo_root/logs/arxiv_14day_sweep.log"
command_name="${1:-}"

run_python() {
  docker run --rm --user "$(id -u):$(id -g)" --network host \
    --entrypoint python -v "$repo_root:/app" -w /app \
    "$image_name" scripts/arxiv_14day_sweep.py "$@"
}

case "$command_name" in
  run)
    if docker container inspect "$container_name" >/dev/null 2>&1; then
      echo "任务容器已经存在；请先查看进度或停止它。" >&2
      exit 1
    fi
    mkdir -p "$repo_root/logs"
    nohup docker run --rm --name "$container_name" \
      --user "$(id -u):$(id -g)" --network host --entrypoint python \
      -v "$repo_root:/app" -w /app \
      -e HTTP_PROXY -e HTTPS_PROXY -e ALL_PROXY -e NO_PROXY \
      -e http_proxy -e https_proxy -e all_proxy -e no_proxy \
      "$image_name" scripts/arxiv_14day_sweep.py run \
      >"$log_file" 2>&1 </dev/null &
    sleep 2
    if ! docker container inspect "$container_name" >/dev/null 2>&1; then
      echo "任务未能启动，请查看日志：$log_file" >&2
      tail -n 10 "$log_file" >&2
      exit 1
    fi
    echo "后台任务已提交；日志：$log_file"
    ;;
  status|export)
    run_python "$command_name" "${@:2}"
    ;;
  stop)
    docker stop -t 60 "$container_name"
    ;;
  logs)
    tail -f "$log_file"
    ;;
  *)
    echo "用法：$0 {run|status|export|stop|logs} [--top N]" >&2
    exit 2
    ;;
esac
