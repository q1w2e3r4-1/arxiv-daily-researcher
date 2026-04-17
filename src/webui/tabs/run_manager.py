"""运行管理 Tab — 立即运行每日研究、查看运行状态/日志、停止进程。

架构：
  本地模式：直接 subprocess.Popen 启动 main.py，日志写入 logs/manual_*.log。
  Docker 模式：写触发文件 data/run/webui_run_trigger.flag，
               主研究容器 entrypoint.sh 的 trigger_watcher 每 5 秒轮询，
               检测到后启动 python main.py（真实 PID 写入 webui_triggered.pid）。
"""

from __future__ import annotations

import datetime
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

import streamlit as st

from webui.i18n import t

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_LOGS_DIR     = _PROJECT_ROOT / "logs"
_LOCK_DIR     = _PROJECT_ROOT / "data" / "run"
_MAIN_PY      = _PROJECT_ROOT / "main.py"
_WEBUI_PID_FILE  = _LOCK_DIR / "webui_triggered.pid"
_TRIGGER_FILE    = _LOCK_DIR / "webui_run_trigger.flag"

_IS_DOCKER_WEBUI = not _MAIN_PY.exists()

# session_state 键（日志查看器）
_LOG_ACTIVE = "rm_log_active_path"    # 当前展示的日志路径（str）
_LOG_CLOSED = "rm_log_viewer_closed"  # 是否关闭内容区


# ─── 工具函数 ────────────────────────────────────────────────────────────────


def _read_pid_from_file(path: Path) -> Optional[int]:
    try:
        content = path.read_text(encoding="utf-8").strip()
        m = re.search(r"PID=(\d+)", content)
        if m:
            return int(m.group(1))
        first = content.splitlines()[0].strip()
        return int(first) if first.isdigit() else None
    except Exception:
        return None


def _is_process_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def _get_lock_files() -> list[Path]:
    """只返回 *.lock 文件（main.py 拥有的任务锁），按修改时间倒序。"""
    if not _LOCK_DIR.exists():
        return []
    files = list(_LOCK_DIR.glob("*.lock"))
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files


def _scan_all_logs() -> dict[str, list[Path]]:
    """
    扫描 logs/ 目录下所有 *.log，按类型分组（最新在前）。

    分组：
      manual  → manual_*.log（面板手动触发）
      daily   → daily_*.log / cron_*.log / startup_*.log（定时/启动触发）
      trend   → trend_*.log
      system  → system*.log / arxiv_researcher*.log
      other   → 其余
    """
    if not _LOGS_DIR.exists():
        return {}

    all_logs = sorted(
        _LOGS_DIR.glob("**/*.log"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    groups: dict[str, list[Path]] = {
        "manual": [], "daily": [], "trend": [], "system": [], "other": [],
    }
    for p in all_logs:
        name = p.name.lower()
        if name.startswith("manual_"):
            groups["manual"].append(p)
        elif name.startswith(("daily_", "cron_", "startup_")):
            groups["daily"].append(p)
        elif name.startswith("trend_"):
            groups["trend"].append(p)
        elif name.startswith(("system", "arxiv_researcher")):
            groups["system"].append(p)
        else:
            groups["other"].append(p)

    return {k: v for k, v in groups.items() if v}


def _read_log_tail(log_path: Path, max_lines: int = 300) -> str:
    try:
        content = log_path.read_text(encoding="utf-8", errors="replace")
        lines = content.splitlines()
        if len(lines) > max_lines:
            lines = [
                f"... (省略前 {len(lines) - max_lines} 行，仅显示最后 {max_lines} 行) ..."
            ] + lines[-max_lines:]
        return "\n".join(lines)
    except Exception as e:
        return f"读取日志失败: {e}"


def _get_all_running_procs() -> list[tuple[Path, int]]:
    """返回所有拥有存活 PID 的锁文件。"""
    running = []
    for f in _get_lock_files():
        pid = _read_pid_from_file(f)
        if pid and _is_process_running(pid):
            running.append((f, pid))
    return running


def _do_stop_all() -> None:
    running = _get_all_running_procs()
    if not running:
        st.info(t("no_running_process"))
    else:
        killed = 0
        for f, pid in running:
            try:
                os.kill(pid, signal.SIGTERM)
                st.info(t("pid_killed").format(pid=pid) + f" ({f.name})")
                killed += 1
            except Exception as e:
                st.error(f"停止进程 PID={pid} 失败: {e}")
        if killed > 0:
            st.success(f"已向 {killed} 个进程发送停止信号。")
            time.sleep(0.5)
            st.rerun()


# ─── 触发文件机制 ─────────────────────────────────────────────────────────────


def _trigger_age_seconds() -> Optional[float]:
    if not _TRIGGER_FILE.exists():
        return None
    return time.time() - _TRIGGER_FILE.stat().st_mtime


def _write_trigger_file() -> tuple[bool, str]:
    try:
        _LOCK_DIR.mkdir(parents=True, exist_ok=True)
        _TRIGGER_FILE.write_text("daily_research", encoding="utf-8")
        return True, ""
    except Exception as e:
        return False, str(e)


def _render_run_control() -> None:
    trigger_age   = _trigger_age_seconds()
    trigger_stale   = trigger_age is not None and trigger_age > 30
    trigger_pending = trigger_age is not None and not trigger_stale

    active_locks = _get_all_running_procs()
    is_running   = bool(active_locks)

    webui_pid = _read_pid_from_file(_WEBUI_PID_FILE) if _WEBUI_PID_FILE.exists() else None
    webui_proc_running = bool(webui_pid and _is_process_running(webui_pid))

    if trigger_stale:
        st.warning(f"⚠️ {t('rm_trigger_stale').format(n=int(trigger_age))}")
        if st.button(t("rm_clear_trigger_btn"), key="rm_clear_trigger"):
            _TRIGGER_FILE.unlink(missing_ok=True)
            st.rerun()
        return

    if trigger_pending:
        st.info(f"⏳ {t('rm_trigger_pending')}")

    can_run = not trigger_pending and not is_running
    col_run, col_stop, col_status = st.columns([1, 1, 3])
    with col_run:
        run_clicked = st.button(
            "▶ " + t("run_now_btn"), key="rm_run_now",
            type="primary", use_container_width=True, disabled=not can_run,
        )
    with col_stop:
        stop_clicked = st.button(
            "⏹ " + t("stop_all_btn"), key="rm_stop_all",
            type="secondary", use_container_width=True,
            help=t("stop_all_hint"), disabled=not is_running,
        )
    with col_status:
        if is_running:
            lock_info = ", ".join(f"`{f.name}` PID={pid}" for f, pid in active_locks)
            st.info(f"🟢 {t('rm_status_running')} — {lock_info}")
        elif webui_proc_running:
            st.info(f"🟢 {t('rm_process_running_label')} (PID={webui_pid})")
        elif trigger_pending:
            st.caption(t("rm_trigger_pending_short"))
        else:
            _show_last_run_hint()

    if run_clicked:
        if _IS_DOCKER_WEBUI:
            ok, err = _write_trigger_file()
            if ok:
                st.toast(t("rm_trigger_sent_short"), icon="✅")
                st.rerun()
            else:
                st.error(f"{t('rm_trigger_failed')}: {err}")
        else:
            _LOCK_DIR.mkdir(parents=True, exist_ok=True)
            log_file = _LOGS_DIR / f"manual_{datetime.datetime.now():%Y%m%d_%H%M%S}.log"
            try:
                with open(log_file, "w") as lf:
                    proc = subprocess.Popen(
                        [sys.executable, str(_MAIN_PY), "--mode", "daily_research"],
                        cwd=str(_PROJECT_ROOT),
                        stdout=lf, stderr=lf, start_new_session=True,
                    )
                _WEBUI_PID_FILE.write_text(str(proc.pid), encoding="utf-8")
                st.toast(f"✅ {t('process_started')} (PID={proc.pid})", icon="✅")
                time.sleep(0.5)
                st.rerun()
            except Exception as e:
                st.error(f"启动失败: {e}")

    if stop_clicked:
        _do_stop_all()


def _show_last_run_hint() -> None:
    log_groups  = _scan_all_logs()
    manual_logs = log_groups.get("manual", [])
    if manual_logs:
        latest  = manual_logs[0]
        mtime   = datetime.datetime.fromtimestamp(latest.stat().st_mtime)
        size_kb = latest.stat().st_size / 1024
        st.caption(
            f"✅ {t('rm_last_run_at')}: {mtime:%Y-%m-%d %H:%M:%S}  "
            f"({latest.name}, {size_kb:.0f} KB)"
        )
    else:
        st.caption(t("rm_no_panel_process"))


# ─── 状态面板 ────────────────────────────────────────────────────────────────


def _render_status() -> None:
    lock_files = _get_lock_files()
    if not lock_files:
        st.success(f"✅ {t('rm_no_running_tasks')}")
        return

    for f in lock_files:
        pid        = _read_pid_from_file(f)
        is_running = bool(pid and _is_process_running(pid))
        icon       = "🟢" if is_running else "🔴"
        status     = t("rm_status_running") if is_running else t("rm_status_stopped")
        pid_str    = f"PID={pid}" if pid else t("rm_no_pid")
        mtime      = datetime.datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")

        cols = st.columns([5, 1])
        with cols[0]:
            st.markdown(f"{icon} `{f.name}` — {status} | {pid_str} | {t('rm_started_at')}: {mtime}")
        with cols[1]:
            if not is_running:
                if st.button(
                    t("rm_clean_lock_btn"), key=f"clean_{f.name}",
                    use_container_width=True, help=t("rm_clean_lock_help"),
                ):
                    f.unlink(missing_ok=True)
                    st.rerun()


# ─── 日志查看器 ──────────────────────────────────────────────────────────────


def _make_log_options(logs: list[Path]) -> list[tuple[str, Optional[Path]]]:
    """构建 selectbox 选项，首项为空占位符。"""
    opts: list[tuple[str, Optional[Path]]] = [("—", None)]
    for p in logs:
        mtime   = datetime.datetime.fromtimestamp(p.stat().st_mtime).strftime("%m-%d %H:%M")
        size_kb = p.stat().st_size / 1024
        opts.append((f"{p.name}  [{mtime}  {size_kb:.0f}KB]", p))
    return opts


def _render_log_section() -> None:
    """
    三列并排的日志选择器 + 共享内容区。

    布局：
      [📌 系统日志 ▼]  [📀 运行日志 ▼]  [📄 其他日志 ▼]
      ─────────────────────────────────────────────────
      <选中日志的内容（单一显示区）>
    """
    log_groups  = _scan_all_logs()
    system_logs = log_groups.get("system", [])
    run_logs    = log_groups.get("manual", []) + log_groups.get("daily", [])
    run_logs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    other_logs  = log_groups.get("trend", []) + log_groups.get("other", [])
    other_logs.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    sys_opts = _make_log_options(system_logs)
    run_opts = _make_log_options(run_logs)
    oth_opts = _make_log_options(other_logs)

    sys_map = {o[0]: o[1] for o in sys_opts}
    run_map = {o[0]: o[1] for o in run_opts}
    oth_map = {o[0]: o[1] for o in oth_opts}

    # 初次加载：从所有非系统日志中选时间最新的，无则不预选（不选系统日志）
    if _LOG_ACTIVE not in st.session_state:
        non_system = run_logs + other_logs
        if non_system:
            newest = max(non_system, key=lambda p: p.stat().st_mtime)
            st.session_state[_LOG_ACTIVE] = str(newest)

    # ── 三列选择器 ──────────────────────────────────────────────────────────
    col1, col2, col3 = st.columns(3)

    with col1:
        st.caption(f"📌 **{t('rm_log_group_system')}**")
        sys_sel = st.selectbox(
            t("rm_log_group_system"), [o[0] for o in sys_opts],
            key="rm_sel_sys", label_visibility="collapsed",
            disabled=not system_logs,
        )
        new_sys = sys_map.get(sys_sel)
        if new_sys and st.session_state.get("rm_sel_sys_prev") != sys_sel:
            st.session_state[_LOG_ACTIVE] = str(new_sys)
            st.session_state[_LOG_CLOSED] = False
        st.session_state["rm_sel_sys_prev"] = sys_sel

    with col2:
        st.caption(f"📀 **{t('rm_log_group_runs')}**")
        run_sel = st.selectbox(
            t("rm_log_group_runs"), [o[0] for o in run_opts],
            key="rm_sel_run", label_visibility="collapsed",
            disabled=not run_logs,
        )
        new_run = run_map.get(run_sel)
        if new_run and st.session_state.get("rm_sel_run_prev") != run_sel:
            st.session_state[_LOG_ACTIVE] = str(new_run)
            st.session_state[_LOG_CLOSED] = False
        st.session_state["rm_sel_run_prev"] = run_sel

    with col3:
        st.caption(f"📄 **{t('rm_log_group_secondary')}**")
        oth_sel = st.selectbox(
            t("rm_log_group_secondary"), [o[0] for o in oth_opts],
            key="rm_sel_oth", label_visibility="collapsed",
            disabled=not other_logs,
        )
        new_oth = oth_map.get(oth_sel)
        if new_oth and st.session_state.get("rm_sel_oth_prev") != oth_sel:
            st.session_state[_LOG_ACTIVE] = str(new_oth)
            st.session_state[_LOG_CLOSED] = False
        st.session_state["rm_sel_oth_prev"] = oth_sel

    # ── 共享内容区 ──────────────────────────────────────────────────────────
    active_str = st.session_state.get(_LOG_ACTIVE)
    is_closed  = st.session_state.get(_LOG_CLOSED, False)

    if not active_str or is_closed:
        st.caption(t("rm_no_log_selected"))
        return

    active_path = Path(active_str)
    if not active_path.exists():
        st.warning(t("rm_log_file_missing"))
        return

    stat = active_path.stat()
    info_col, r_col, c_col, _ = st.columns([4, 1, 1, 1])
    with info_col:
        st.caption(
            f"`{active_path.name}`  ·  {stat.st_size/1024:.1f} KB  ·  "
            f"{t('reports_mtime')}: "
            f"{datetime.datetime.fromtimestamp(stat.st_mtime):%Y-%m-%d %H:%M:%S}"
        )
    with r_col:
        st.button(f"🔄 {t('rm_refresh_log_btn')}", key="rm_log_refresh", use_container_width=True)
    with c_col:
        if st.button(f"✖ {t('rm_close_log_btn')}", key="rm_log_close", use_container_width=True):
            st.session_state[_LOG_CLOSED] = True
            st.rerun()

    st.code(_read_log_tail(active_path, max_lines=300), language="", line_numbers=True)


# ─── 主渲染 ─────────────────────────────────────────────────────────────────


def render(_env_values: dict, _config_values: dict) -> None:
    st.markdown(
        f'<p class="section-title">{t("run_manager_title")}</p>',
        unsafe_allow_html=True,
    )

    st.markdown(f"#### 🚀 {t('run_now_section_title')}")
    _render_run_control()

    st.divider()

    st.markdown(f"#### 📊 {t('rm_status_title')}")
    _render_status()

    st.divider()

    st.markdown(f"#### 📋 {t('run_log_title')}")
    _render_log_section()


def collect(_env_values: dict, _config_values: dict) -> dict:
    return {}
