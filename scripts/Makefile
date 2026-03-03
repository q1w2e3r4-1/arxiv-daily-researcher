.PHONY: build run stop logs run-once build-multi clean

# Docker compose 文件路径
COMPOSE_FILE := ../docker/docker-compose.yml

# 构建 Docker 镜像
build:
	docker compose -f $(COMPOSE_FILE) build

# 启动容器 (后台运行，按 CRON_SCHEDULE 定时执行)
run:
	docker compose -f $(COMPOSE_FILE) up -d

# 停止容器
stop:
	docker compose -f $(COMPOSE_FILE) down

# 查看实时日志
logs:
	docker compose -f $(COMPOSE_FILE) logs -f

# 立即运行一次 (容器运行完即退出)
run-once:
	docker compose -f $(COMPOSE_FILE) run --rm -e MODE=run-once arxiv-researcher

# 启动并立即运行一次 (之后继续按计划定时运行)
run-now:
	docker compose -f $(COMPOSE_FILE) up -d -e RUN_ON_STARTUP=true

# 多架构构建 (支持 NAS ARM64)
build-multi:
	docker buildx build --platform linux/amd64,linux/arm64 \
		-f ../docker/Dockerfile -t arxiv-daily-researcher:latest ..

# 清理容器和镜像
clean:
	docker compose -f $(COMPOSE_FILE) down --rmi local --volumes --remove-orphans
