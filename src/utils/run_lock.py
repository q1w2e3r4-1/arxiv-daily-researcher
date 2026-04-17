"""
任务并发锁 — 防止完全相同的任务同时执行。

使用文件独占锁（fcntl.LOCK_EX | LOCK_NB），进程退出后锁自动释放。

锁文件目录：data/run/
  daily_research.lock                — 每日研究（同时只允许一个）
  trend_research_<params_hash>.lock  — 趋势研究（相同参数同时只允许一个）
"""

import fcntl
import hashlib
import os
import re
import signal
import time
import sys
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import List, Optional


def _lock_dir() -> Path:
    try:
        from config import settings

        d = Path(settings.DATA_DIR) / "run"
    except Exception:
        d = Path("data/run")
    d.mkdir(parents=True, exist_ok=True)
    return d


def _params_hash(
    keywords: List[str],
    date_from,
    date_to,
    categories: Optional[List[str]],
) -> str:
    key = "|".join(
        [
            ",".join(sorted(str(k) for k in keywords)),
            str(date_from),
            str(date_to),
            ",".join(sorted(str(c) for c in (categories or []))),
        ]
    )
    return hashlib.md5(key.encode()).hexdigest()[:8]


def _remove_stale_lock(lock_path: Path) -> None:
    """若锁文件里记录的 PID 已不存在，删除 stale lock file。

    适用场景：容器被 SIGKILL 强制终止，finally 块未执行，锁文件残留。
    """
    if not lock_path.exists():
        return
    try:
        content = lock_path.read_text().strip()
        m = re.search(r"PID=(\d+)", content)
        if not m:
            return
        pid = int(m.group(1))
        os.kill(pid, 0)  # 若进程不存在则抛 ProcessLookupError
    except ProcessLookupError:
        lock_path.unlink(missing_ok=True)  # 进程已死，清理 stale lock
    except Exception:
        pass  # 无法判断，保守地保留锁文件


def _parse_lock_info(content: str):
    """解析锁文件中的 PID 与 started 时间。"""
    pid = None
    started_at = None

    m_pid = re.search(r"PID=(\d+)", content or "")
    if m_pid:
        pid = int(m_pid.group(1))

    started_pattern = r"started=([0-9]{4}-[0-9]{2}-[0-9]{2} " r"[0-9]{2}:[0-9]{2}:[0-9]{2})"
    m_started = re.search(started_pattern, content or "")
    if m_started:
        try:
            started_at = datetime.strptime(m_started.group(1), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            started_at = None

    return pid, started_at


def _try_kill_stuck_process(pid: int) -> bool:
    """尝试终止疑似卡死进程。成功终止返回 True。"""
    try:
        os.kill(pid, signal.SIGTERM)
        # 最多等待 5 秒优雅退出
        for _ in range(10):
            time.sleep(0.5)
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return True

        # 仍存活则强制终止
        os.kill(pid, signal.SIGKILL)
        for _ in range(10):
            time.sleep(0.2)
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return True
    except ProcessLookupError:
        return True
    except Exception:
        return False

    return False


def _recover_expired_lock(lock_file, task_desc: str, max_age_hours: int) -> bool:
    """当锁超龄时尝试回收。回收成功返回 True。"""
    if max_age_hours <= 0:
        return False

    try:
        lock_file.seek(0)
        info = lock_file.read().strip()
    except Exception:
        return False

    pid, started_at = _parse_lock_info(info)
    if not started_at:
        return False

    age_seconds = (datetime.now() - started_at).total_seconds()
    if age_seconds <= max_age_hours * 3600:
        return False

    print(f"⚠️  检测到超龄运行锁（>{max_age_hours}h），尝试回收: {task_desc}")
    if pid:
        killed = _try_kill_stuck_process(pid)
        if not killed:
            print(f"⚠️  无法终止超龄进程 PID={pid}，保留当前锁")
            return False

    # 等待内核释放 flock
    time.sleep(0.2)
    return True


@contextmanager
def run_lock(
    mode: str,
    keywords: Optional[List[str]] = None,
    date_from=None,
    date_to=None,
    categories: Optional[List[str]] = None,
):
    """
    获取运行锁；若相同任务已在运行则打印提示并以 exit(0) 退出。

    用法:
        with run_lock("daily_research"):
            DailyResearchPipeline().run()

        with run_lock(
            "trend_research", keywords=[...], date_from=..., date_to=..., categories=[...]
        ):
            TrendResearchPipeline(...).run()
    """
    if mode == "trend_research" and keywords:
        h = _params_hash(keywords, date_from, date_to, categories)
        fname = f"trend_research_{h}.lock"
        task_desc = f"trend_research [keywords={keywords}, {date_from}~{date_to}"
        if categories:
            task_desc += f", categories={categories}"
        task_desc += "]"
    else:
        fname = f"{mode}.lock"
        task_desc = mode

    lock_path = _lock_dir() / fname

    try:
        from config import settings

        max_age_hours = int(getattr(settings, "RUN_LOCK_MAX_AGE_HOURS", 12))
    except Exception:
        max_age_hours = 12

    # 清理 stale lock（上次进程被 SIGKILL 时 finally 未执行的残留）
    _remove_stale_lock(lock_path)

    lock_file = open(lock_path, "a+")

    try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (IOError, OSError):
        # 若锁已超龄，尝试回收并重试一次获取锁
        recovered = _recover_expired_lock(lock_file, task_desc, max_age_hours)
        acquired_after_recovery = False
        if recovered:
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except (IOError, OSError):
                pass
            else:
                acquired_after_recovery = True

        if not acquired_after_recovery:
            try:
                lock_file.seek(0)
                info = lock_file.read().strip()
            except Exception:
                info = ""
            lock_file.close()

            print("\n⚠️  相同任务正在运行中，跳过本次执行")
            print(f"   任务: {task_desc}")
            if info:
                print(f"   运行信息: {info}")
            print(f"   锁文件: {lock_path}\n")
            sys.exit(0)

        try:
            lock_file.seek(0)
            info = lock_file.read().strip()
        except Exception:
            info = ""
        if info:
            print(f"ℹ️  已回收超龄运行锁: {info}")

    # 写入诊断信息方便排查
    try:
        lock_file.seek(0)
        lock_file.truncate()
        lock_file.write(
            f"PID={os.getpid()}, started={datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        lock_file.flush()
    except Exception:
        pass

    # 将 SIGTERM 转为 SystemExit，确保 docker stop 时 finally 块能正常执行
    _old_sigterm = signal.getsignal(signal.SIGTERM)

    def _sigterm_handler(signum, frame):
        sys.exit(0)

    signal.signal(signal.SIGTERM, _sigterm_handler)

    try:
        yield
    finally:
        signal.signal(signal.SIGTERM, _old_sigterm)
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            lock_file.close()
            lock_path.unlink(missing_ok=True)
        except Exception:
            pass
