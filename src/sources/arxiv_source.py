"""
ArXiv 论文数据源

从 ArXiv 预印本服务器抓取论文，支持 PDF 下载和深度分析。
支持两种搜索模式：
- 分类搜索（daily_report）：按领域分类 + 时间范围
- 关键词搜索（trend_research）：按关键词 + 时间段
"""

import arxiv
import logging
import signal
import time
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
from typing import List, Optional

from .base_source import BasePaperSource, PaperMetadata

logger = logging.getLogger(__name__)


class _ArxivTimeoutError(TimeoutError):
    """ArXiv 抓取超时异常。"""


class ArxivFetchError(RuntimeError):
    """
    ArXiv 抓取失败异常。

    当 ArXiv API 返回服务端错误（5xx）或其他致命错误，且经过多次重试仍无法获取任何论文时抛出。
    不同于超时或速率限制（这些会自动重试），本异常表示操作已彻底失败。
    """


class _timeout_guard:
    """使用 SIGALRM 对阻塞调用设置硬超时（Linux 主线程可用）。"""

    def __init__(self, seconds: int):
        self.seconds = max(0, int(seconds or 0))
        self._old_handler = None
        self._enabled = False

    def __enter__(self):
        if self.seconds <= 0:
            return self
        if not hasattr(signal, "SIGALRM"):
            return self
        try:
            self._old_handler = signal.getsignal(signal.SIGALRM)

            def _handler(signum, frame):
                raise _ArxivTimeoutError(f"ArXiv 请求超时（>{self.seconds}s）")

            signal.signal(signal.SIGALRM, _handler)
            signal.alarm(self.seconds)
            self._enabled = True
        except Exception:
            self._enabled = False
        return self

    def __exit__(self, exc_type, exc, tb):
        if self._enabled:
            signal.alarm(0)
            if self._old_handler is not None:
                signal.signal(signal.SIGALRM, self._old_handler)
        return False


def _build_submitted_date_filter(date_from: date, date_to: date) -> str:
    """构建 ArXiv submittedDate 查询过滤器。"""
    date_from_str = date_from.strftime("%Y%m%d") + "0000"
    date_to_str = date_to.strftime("%Y%m%d") + "2359"
    return f"submittedDate:[{date_from_str} TO {date_to_str}]"


class ArxivSource(BasePaperSource):
    """
    ArXiv 论文数据源。

    特点：
    - 支持按领域分类（如 quant-ph, cs.AI）抓取
    - 支持 PDF 下载，可进行深度分析
    - 使用官方 arxiv Python 库
    - 支持网络代理
    """

    def __init__(
        self,
        history_dir: Path,
        max_results: int = 100,
        proxy_dict: Optional[dict] = None,
    ):
        """
        初始化 ArXiv 数据源。

        参数:
            history_dir: 历史记录存储目录
            max_results: 每个领域最多保留的新论文数
            proxy_dict: 代理配置字典，如 {"http": "...", "https": "..."}
        """
        super().__init__("arxiv", history_dir)
        self.max_results = max_results
        self.client = arxiv.Client(page_size=100, delay_seconds=6.0, num_retries=3)  # 避免 429 错误

        # 注入代理配置到 arxiv.Client 的内部 requests.Session
        if proxy_dict:
            self.client._session.proxies.update(proxy_dict)
            logger.info(f"[ArXiv] 已配置网络代理: {proxy_dict.get('https', proxy_dict.get('http', 'N/A'))}")

    @property
    def display_name(self) -> str:
        return "ArXiv"

    def can_download_pdf(self) -> bool:
        return True

    def fetch_papers(self, days: int, domains: List[str] = None, **kwargs) -> List[PaperMetadata]:
        """
        从 ArXiv 抓取指定领域最近 N 天的论文。

        参数:
            days: 搜索最近 N 天的论文
            domains: ArXiv 领域分类列表，如 ["quant-ph", "cs.AI"]
            kwargs.date_from/date_to: 可选显式日期范围（闭区间）

        返回:
            List[PaperMetadata]: 论文元数据列表
        """
        if domains is None:
            domains = ["quant-ph"]

        all_papers = {}
        date_from = kwargs.get("date_from")
        date_to = kwargs.get("date_to")
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

        try:
            from config import settings as _settings

            fetch_timeout_seconds = int(
                kwargs.get(
                    "fetch_timeout_seconds",
                    getattr(_settings, "ARXIV_FETCH_TIMEOUT_SECONDS", 180),
                )
            )
        except Exception:
            fetch_timeout_seconds = int(kwargs.get("fetch_timeout_seconds", 180))

        logger.info("[ArXiv] 开始抓取论文")
        logger.info(f"  目标领域: {domains}")
        if date_from and date_to:
            logger.info(f"  时间范围: {date_from} ~ {date_to}")
        else:
            logger.info(f"  时间范围: 最近 {days} 天")

        # 记录因严重错误失败的领域及其最后错误信息
        failed_domains: list = []

        for domain in domains:
            query = f"cat:{domain}"
            if date_from and date_to:
                query = f"({query}) AND {_build_submitted_date_filter(date_from, date_to)}"
            logger.info(f"  正在抓取领域 {domain}...")

            # 顺序遍历最新论文，并在收集到足够的新论文后立即停止。
            # 这样既能跨过 history 中已处理/被时间过滤的结果，又不会突破用户配置的上限。
            configured_limit = self.max_results if self.max_results > 0 else None

            search = arxiv.Search(
                query=query, max_results=None, sort_by=arxiv.SortCriterion.SubmittedDate
            )

            # 添加重试机制
            max_retries = 8
            retry_count = 0
            base_wait_time = 60
            domain_failed = False
            last_error_msg = ""

            while retry_count <= max_retries:
                try:
                    count = 0
                    api_total = 0
                    skipped_processed = 0
                    skipped_old = 0
                    consecutive_processed = 0
                    # 早停阈值：连续遇到已处理论文超过此数量则认为已到达上次抓取边界
                    early_stop_threshold = 100

                    with _timeout_guard(fetch_timeout_seconds):
                        for result in self.client.results(search):
                            api_total += 1
                            paper_id = result.get_short_id()

                            # 时间过滤
                            published_dt = result.published
                            published_day = published_dt.date()
                            if date_from and date_to:
                                if published_day > date_to:
                                    continue
                                if published_day < date_from:
                                    skipped_old += 1
                                    break
                            elif published_dt < cutoff_date:
                                skipped_old += 1
                                break

                            # 去重：跳过已处理的论文（仅对时间窗口内的论文生效）
                            if self.is_processed(paper_id):
                                skipped_processed += 1
                                consecutive_processed += 1
                                # 早停：连续遇到大量已处理论文，说明已到达历史边界
                                if consecutive_processed >= early_stop_threshold:
                                    logger.info(
                                        f"    连续 {early_stop_threshold} 篇已处理，已到达历史边界，停止继续获取"
                                    )
                                    break
                                continue

                            # 遇到新论文时重置连续计数器
                            consecutive_processed = 0

                            # 去重：跳过本次已抓取的论文
                            if paper_id in all_papers:
                                continue

                            # 转换为统一格式
                            metadata = PaperMetadata(
                                paper_id=paper_id,
                                title=result.title,
                                authors=[author.name for author in result.authors],
                                abstract=result.summary,
                                published_date=result.published,
                                url=result.entry_id,
                                source="arxiv",
                                pdf_url=result.pdf_url,
                                doi=result.doi,
                                categories=list(result.categories) if result.categories else [],
                            )
                            all_papers[paper_id] = metadata
                            count += 1

                            if configured_limit is not None and count >= configured_limit:
                                logger.info(
                                    f"    已达到配置上限 {configured_limit} 篇，停止继续获取"
                                )
                                break

                    # 增强诊断日志
                    logger.info(f"    领域 {domain}: 发现 {count} 篇新论文")
                    if api_total > 0 and count == 0:
                        logger.info(
                            f"    诊断信息: API 返回 {api_total} 篇，"
                            f"已处理跳过 {skipped_processed} 篇，"
                            f"时间过滤 {skipped_old} 篇"
                        )
                    domain_failed = False
                    break  # 成功则退出重试循环

                except Exception as e:
                    error_msg = str(e)
                    last_error_msg = error_msg
                    if isinstance(e, _ArxivTimeoutError):
                        retry_count += 1
                        if retry_count <= max_retries:
                            wait_time = min(30 * retry_count, 90)
                            logger.warning(
                                f"    领域 {domain} 抓取超时（{fetch_timeout_seconds}s），"
                                f"{wait_time} 秒后重试 ({retry_count}/{max_retries})"
                            )
                            time.sleep(wait_time)
                        else:
                            logger.error(f"    领域 {domain} 抓取失败: 多次超时")
                            domain_failed = True
                            break
                    elif "429" in error_msg or "Too Many Requests" in error_msg:
                        retry_count += 1
                        if retry_count <= max_retries:
                            wait_time = min(base_wait_time * (2 ** (retry_count - 1)), 180)
                            logger.warning(f"    遇到速率限制，等待 {wait_time} 秒后重试...")
                            time.sleep(wait_time)
                        else:
                            logger.error(f"    领域 {domain} 抓取失败: 超过最大重试次数")
                            domain_failed = True
                            break
                    else:
                        # 其他错误（包括 503 等服务端错误）：有限重试后仍失败则标记为严重错误
                        retry_count += 1
                        if retry_count <= max_retries:
                            wait_time = min(30 * retry_count, 90)
                            logger.warning(
                                f"    领域 {domain} 抓取出错: {error_msg}，"
                                f"{wait_time} 秒后重试 ({retry_count}/{max_retries})"
                            )
                            time.sleep(wait_time)
                        else:
                            logger.error(
                                f"    领域 {domain} 抓取失败（已重试 {max_retries} 次）: {error_msg}"
                            )
                            domain_failed = True
                            break

            if domain_failed:
                failed_domains.append((domain, last_error_msg))

        papers = list(all_papers.values())
        logger.info(f"[ArXiv] 总计发现 {len(papers)} 篇新论文")

        # 若所有领域均因错误失败且没有抓取到任何论文，则抛出异常使上层正确报错
        if failed_domains and len(papers) == 0:
            domain_errors = "; ".join(f"{d}({e})" for d, e in failed_domains)
            raise ArxivFetchError(
                f"ArXiv 抓取失败，所有领域均未能获取论文。失败领域及错误: {domain_errors}"
            )
        elif failed_domains:
            # 部分领域失败但其他领域成功获取了论文，只记录警告
            domain_errors = "; ".join(f"{d}({e})" for d, e in failed_domains)
            logger.warning(
                f"[ArXiv] 部分领域抓取失败（{len(failed_domains)}/{len(domains)} 个），"
                f"但已成功获取 {len(papers)} 篇论文。失败领域: {domain_errors}"
            )

        return papers

    def search_by_keywords(
        self,
        keywords: List[str],
        date_from: date,
        date_to: date,
        sort_order: str = "ascending",
        max_results: int = 500,
        categories: Optional[List[str]] = None,
    ) -> List[PaperMetadata]:
        """
        按关键词和时间范围搜索 ArXiv 论文（研究趋势模式专用）。

        使用 all: 字段搜索（标题+摘要+全文），多个关键词用 AND 连接。
        时间范围通过 submittedDate:[YYYYMMDD TO YYYYMMDD] 过滤。
        可选地通过 cat: 限制搜索分类，多个分类用 OR 连接。
        不查询历史记录，不去重，每次独立执行。

        参数:
            keywords: 搜索关键词列表
            date_from: 开始日期
            date_to: 结束日期
            sort_order: 排序方向，"ascending"(旧→新) 或 "descending"(新→旧)
            max_results: 最大结果数（0 = 不限制）
            categories: ArXiv 分类列表，如 ["quant-ph", "cond-mat"]；空列表则不限制分类

        返回:
            按发表时间排序的论文列表
        """
        # 构建查询：多个关键词用 AND 连接，每个关键词用 all: 搜索
        keyword_parts = []
        for kw in keywords:
            # 如果关键词包含空格，用引号包裹做短语匹配
            if " " in kw:
                keyword_parts.append(f'all:"{kw}"')
            else:
                keyword_parts.append(f"all:{kw}")
        keyword_query = " AND ".join(keyword_parts)

        # 分类过滤（可选）：多个分类用 OR 连接
        if categories:
            cat_parts = [f"cat:{c}" for c in categories]
            if len(cat_parts) == 1:
                cat_query = cat_parts[0]
            else:
                cat_query = f"({' OR '.join(cat_parts)})"
            keyword_query = f"({keyword_query}) AND {cat_query}"

        date_filter = _build_submitted_date_filter(date_from, date_to)

        full_query = f"({keyword_query}) AND {date_filter}"

        arxiv_sort_order = (
            arxiv.SortOrder.Ascending if sort_order == "ascending" else arxiv.SortOrder.Descending
        )

        logger.debug(f"[ArXiv] 关键词查询: {full_query}")

        search = arxiv.Search(
            query=full_query,
            max_results=max_results if max_results > 0 else None,
            sort_by=arxiv.SortCriterion.SubmittedDate,
            sort_order=arxiv_sort_order,
        )

        papers = []
        try:
            from config import settings as _settings

            fetch_timeout_seconds = int(getattr(_settings, "ARXIV_FETCH_TIMEOUT_SECONDS", 180))
        except Exception:
            fetch_timeout_seconds = 180

        max_retries = 3
        retry_count = 0
        base_wait_time = 60

        while retry_count <= max_retries:
            papers = []  # 每次重试前清空，防止重复积累
            try:
                with _timeout_guard(fetch_timeout_seconds):
                    for result in self.client.results(search):
                        paper_id = result.get_short_id()

                        metadata = PaperMetadata(
                            paper_id=paper_id,
                            title=result.title,
                            authors=[author.name for author in result.authors],
                            abstract=result.summary,
                            published_date=result.published,
                            url=result.entry_id,
                            source="arxiv",
                            pdf_url=result.pdf_url,
                            doi=result.doi,
                            categories=list(result.categories) if result.categories else [],
                        )
                        papers.append(metadata)

                logger.info(f"[ArXiv] 关键词搜索完成: 共 {len(papers)} 篇论文")
                break

            except Exception as e:
                error_msg = str(e)
                if isinstance(e, _ArxivTimeoutError):
                    retry_count += 1
                    if retry_count <= max_retries:
                        wait_time = min(30 * retry_count, 90)
                        logger.warning(
                            f"  关键词搜索超时（{fetch_timeout_seconds}s），"
                            f"{wait_time} 秒后重试 ({retry_count}/{max_retries})"
                        )
                        time.sleep(wait_time)
                    else:
                        logger.error("  关键词搜索失败: 多次超时")
                        break
                elif "429" in error_msg or "Too Many Requests" in error_msg:
                    retry_count += 1
                    if retry_count <= max_retries:
                        wait_time = base_wait_time * (2 ** (retry_count - 1))
                        logger.warning(f"  遇到速率限制，等待 {wait_time} 秒后重试...")
                        time.sleep(wait_time)
                    else:
                        logger.error("  关键词搜索失败: 超过最大重试次数")
                        break
                else:
                    logger.error(f"  关键词搜索失败: {e}")
                    break

        return papers
