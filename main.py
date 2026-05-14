"""
多数据源论文研究系统入口

运行模式（通过 --mode 参数选择）：
- daily_research（默认）：每日论文监控与研究
- trend_research：关键词驱动的研究趋势分析
"""

import sys
import json
import argparse
from pathlib import Path
from datetime import date, timedelta

# 将 src 目录加入 Python 模块搜索路径
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from config import settings
from utils.logger import setup_logger, setup_run_log
from utils.run_lock import run_lock

logger = setup_logger("Main")


def _load_manual_run_request(request_file: str | None):
    if not request_file:
        return None

    path = Path(request_file)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    finally:
        path.unlink(missing_ok=True)

    date_from_raw = data.get("date_from")
    date_to_raw = data.get("date_to")
    categories = [str(cat).strip() for cat in data.get("arxiv_categories", []) if str(cat).strip()]
    max_results = int(data.get("max_results")) if data.get("max_results") is not None else None

    if not date_from_raw or not date_to_raw:
        raise ValueError("daily request file 缺少 date_from/date_to")
    if not categories:
        raise ValueError("daily request file 至少需要一个 arXiv 分类")
    if max_results is None or max_results < 1:
        raise ValueError("daily request file 的 max_results 必须 >= 1")

    date_from = date.fromisoformat(str(date_from_raw))
    date_to = date.fromisoformat(str(date_to_raw))
    if date_from > date_to:
        raise ValueError("daily request file 的 date_from 不能晚于 date_to")

    return {
        "date_from": date_from,
        "date_to": date_to,
        "max_results": max_results,
        "arxiv_categories": categories,
    }


def _apply_manual_run_overrides(daily_request: dict | None) -> dict | None:
    if not daily_request:
        return None

    settings.ENABLED_SOURCES = ["arxiv"]
    settings.TARGET_JOURNALS = []
    settings.TARGET_DOMAINS = daily_request["arxiv_categories"]
    settings.MAX_RESULTS = daily_request["max_results"]
    settings.MAX_RESULTS_PER_SOURCE = {"arxiv": daily_request["max_results"]}

    logger.info("应用本次网页 daily override:")
    logger.info(f"  日期范围: {daily_request['date_from']} ~ {daily_request['date_to']}")
    logger.info(f"  最大论文数: {daily_request['max_results']}")
    logger.info(f"  ArXiv 分类: {daily_request['arxiv_categories']}")

    return daily_request


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="ArXiv Daily Researcher — 多数据源论文研究系统",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
运行示例:
  python main.py                                        # 每日研究模式（默认）
  python main.py --mode trend_research --keywords "quantum error correction"
  python main.py --mode trend_research --keywords "quantum error correction" "fault tolerant" \\
                 --date-from 2024-01-01 --date-to 2024-12-31
        """,
    )
    parser.add_argument(
        "--mode",
        default="daily_research",
        choices=["daily_research", "trend_research"],
        help="运行模式：daily_research（每日研究，默认）或 trend_research（研究趋势分析）",
    )
    parser.add_argument(
        "--keywords",
        nargs="+",
        help="[trend_research] 搜索关键词，多个用空格分隔",
    )
    parser.add_argument(
        "--date-from",
        type=str,
        default=None,
        help="[trend_research] 搜索起始日期，格式 YYYY-MM-DD",
    )
    parser.add_argument(
        "--date-to",
        type=str,
        default=None,
        help="[trend_research] 搜索截至日期，格式 YYYY-MM-DD（默认：今天）",
    )
    parser.add_argument(
        "--sort-order",
        type=str,
        choices=["ascending", "descending"],
        default=None,
        help="[trend_research] 时间排序方向：ascending（旧→新）或 descending（新→旧）",
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=None,
        help="[trend_research] 最大论文数（安全上限，默认使用配置文件值）",
    )
    parser.add_argument(
        "--categories",
        nargs="+",
        default=None,
        help="[trend_research] 限制搜索的 ArXiv 分类，多个用空格分隔，如 quant-ph cond-mat.mes-hall；不指定则不限制分类",
    )
    parser.add_argument(
        "--manual-run-request-file",
        type=str,
        default=None,
        help="[daily_research] 网页触发的一次性运行参数 JSON 文件路径",
    )
    return parser.parse_args()


if __name__ == "__main__":
    settings.ensure_directories()

    # 自动更新检查
    if settings.AUTO_UPDATE_ENABLED:
        try:
            from utils.updater import check_and_update

            check_and_update(logger)
        except Exception as e:
            logger.warning(f"自动更新检查失败: {e}")

    args = parse_args()

    if args.mode == "trend_research":
        # 研究趋势分析模式
        log_file = setup_run_log("trend_research")
        logger.info(f"趋势研究日志文件: {log_file}")

        if not args.keywords:
            print("错误: trend_research 模式必须指定 --keywords 参数")
            sys.exit(1)

        date_to = date.today()
        if args.date_to:
            date_to = date.fromisoformat(args.date_to)

        date_from = date_to - timedelta(days=settings.RESEARCH_DEFAULT_DATE_RANGE_DAYS)
        if args.date_from:
            date_from = date.fromisoformat(args.date_from)

        sort_order = args.sort_order or settings.RESEARCH_SORT_ORDER
        max_results = (
            args.max_results if args.max_results is not None else settings.RESEARCH_MAX_RESULTS
        )

        from modes.trend_research import TrendResearchPipeline

        with run_lock(
            "trend_research",
            keywords=args.keywords,
            date_from=date_from,
            date_to=date_to,
            categories=args.categories,
        ):
            TrendResearchPipeline(
                settings=settings,
                keywords=args.keywords,
                date_from=date_from,
                date_to=date_to,
                sort_order=sort_order,
                max_results=max_results,
                categories=args.categories,
            ).run()
    else:
        # 每日研究模式（默认）
        log_file = setup_run_log("daily_research")
        logger.info(f"每日研究日志文件: {log_file}")

        daily_request = _apply_manual_run_overrides(_load_manual_run_request(args.manual_run_request_file))

        from modes.daily_research import DailyResearchPipeline

        with run_lock("daily_research"):
            DailyResearchPipeline(
                date_from=daily_request["date_from"] if daily_request else None,
                date_to=daily_request["date_to"] if daily_request else None,
            ).run()
