"""
自动更新检查模块

从 GitHub 仓库检查是否有新版本，并自动拉取最新代码。
"""

import subprocess
import sys
from pathlib import Path

REPO_URL = "https://github.com/yzr278892/arxiv-daily-researcher"


def check_and_update(logger=None) -> bool:
    """
    检查 GitHub 仓库是否有更新，如有则自动拉取。

    返回:
        bool: True 表示已更新或已是最新，False 表示检查失败
    """

    def log(msg, level="info"):
        if logger:
            getattr(logger, level)(msg)
        else:
            print(msg)

    project_root = Path(__file__).resolve().parent.parent.parent
    git_dir = project_root / ".git"

    if not git_dir.exists():
        log("未检测到 .git 目录，跳过更新检查", "warning")
        return False

    try:
        # 获取当前分支
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=10,
        )
        branch = result.stdout.strip() or "main"

        # 获取远程更新信息
        log("正在检查更新...")
        fetch_result = subprocess.run(
            ["git", "fetch", "origin", branch],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if fetch_result.returncode != 0:
            log(f"获取远程更新失败: {fetch_result.stderr.strip()}", "warning")
            return False

        # 比较本地和远程的提交
        result = subprocess.run(
            ["git", "rev-list", f"HEAD..origin/{branch}", "--count"],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            log(f"比较提交失败: {result.stderr.strip()}", "warning")
            return False
        behind_count = int(result.stdout.strip())

        if behind_count == 0:
            log("当前已是最新版本")
            return True

        log(f"发现 {behind_count} 个新提交，正在更新...")

        # 检查是否有未提交的修改
        status_result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=10,
        )
        has_changes = bool(status_result.stdout.strip())

        if has_changes:
            # 暂存本地修改
            log("检测到本地修改，暂存中...")
            subprocess.run(
                ["git", "stash", "push", "-m", "auto-update-stash"],
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=10,
            )

        # 拉取最新代码
        pull_result = subprocess.run(
            ["git", "pull", "origin", branch],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=60,
        )

        if pull_result.returncode != 0:
            log(f"拉取更新失败: {pull_result.stderr.strip()}", "warning")
            if has_changes:
                subprocess.run(
                    ["git", "stash", "pop"],
                    cwd=project_root,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
            return False

        if has_changes:
            # 恢复本地修改
            pop_result = subprocess.run(
                ["git", "stash", "pop"],
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if pop_result.returncode != 0:
                log("恢复本地修改时出现冲突，请手动解决", "warning")

        log(f"更新完成！已拉取 {behind_count} 个新提交")
        return True

    except subprocess.TimeoutExpired:
        log("更新检查超时，跳过", "warning")
        return False
    except Exception as e:
        log(f"更新检查异常: {e}", "warning")
        return False
