"""
每日研究模式主流程

从多个数据源抓取论文，评分、深度分析并生成报告。

工作流程:
1. 加载配置
2. 准备关键词（主要关键词 + Reference 提取的次要关键词）
3. 从多个数据源抓取论文
4. 对所有论文进行加权评分
5. 对 ArXiv 及格论文进行深度分析（其他来源跳过）
6. 按数据源分别生成报告
7. 关键词趋势处理
8. 发送通知
"""

import hashlib
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, date
from typing import Dict, List, Any

from tqdm import tqdm

from config import settings
from utils.logger import setup_logger
from utils.token_counter import token_counter
from utils.daily_research_store import DailyResearchStore
from agents import KeywordAgent, AnalysisAgent
from sources import SearchAgent, PaperMetadata, ArxivFetchError
from report.daily import Reporter
from notifications import NotifierAgent, RunResult

logger = setup_logger("DailyResearch")


def _score_single_paper(
    paper,
    source,
    analysis_agent,
    all_keywords,
    keyword_tracker,
):
    """对单篇论文进行评分（供并发调用）。"""
    logger.info(
        f"开始评分 [{source}] {paper.paper_id} | 标题: {paper.title}"
    )

    score_response = analysis_agent.score_paper(
        paper_id=paper.paper_id,
        title=paper.title,
        authors=paper.get_authors_string(),
        abstract=paper.abstract,
        keywords_dict=all_keywords,
        source=source,
        categories=paper.categories,
    )

    scored = {
        "paper_metadata": paper,
        "paper_id": paper.paper_id,
        "title": paper.title,
        "authors": paper.get_authors_string(),
        "abstract": paper.abstract,
        "abstract_cn": "",
        "url": paper.url,
        "pdf_url": paper.pdf_url,
        "published": paper.published_date.strftime("%Y-%m-%d") if paper.published_date else "N/A",
        "score_response": score_response,
    }

    if keyword_tracker and score_response.extracted_keywords:
        try:
            keyword_tracker.record_keywords(
                keywords=score_response.extracted_keywords, paper_id=paper.paper_id, source=source
            )
        except Exception as e:
            logger.warning(f"关键词记录失败 ({paper.paper_id[:30]}...): {e}")

    return scored


def _translate_single_qualified_paper(scored, analysis_agent, translation_cache, cache_lock):
    """对单篇及格论文执行摘要翻译，并复用翻译缓存。"""
    abstract = scored.get("abstract", "")
    if not abstract or not abstract.strip():
        return {"paper_id": scored["paper_id"], "abstract_cn": "", "from_cache": False}

    abstract_hash = hashlib.md5(abstract.encode("utf-8")).hexdigest()
    with cache_lock:
        cached = translation_cache.get(abstract_hash)
    if cached is not None:
        return {"paper_id": scored["paper_id"], "abstract_cn": cached, "from_cache": True}

    translation = analysis_agent.translate_abstract(abstract)
    with cache_lock:
        translation_cache.setdefault(abstract_hash, translation)
    return {
        "paper_id": scored["paper_id"],
        "abstract_cn": translation,
        "from_cache": False,
    }


def _deep_analyze_single_paper(paper_info, analysis_agent):
    """
    对单篇论文进行深度分析（供并发调用）。

    返回:
        dict 或 None: {'paper_id': ..., 'analysis': ...} 或 None（失败时）
    """
    paper_meta = paper_info.get("paper_metadata")
    pdf_url = paper_meta.get_best_pdf_url() if paper_meta else paper_info.get("pdf_url")

    analysis = analysis_agent.deep_analyze(
        title=paper_info["title"],
        pdf_url=pdf_url,
        abstract=paper_info["abstract"],
        fallback_to_abstract=True,
    )

    if analysis:
        return {
            "paper_id": paper_info["paper_id"],
            "analysis": analysis,
            "paper_meta": paper_meta,
            "title": paper_info["title"],
        }
    return None


def _get_tldr_text(scored: Dict[str, Any]) -> str:
    score_resp = scored.get("score_response")
    abstract_cn = (scored.get("abstract_cn") or "").strip()
    paper_meta = scored.get("paper_metadata")
    abstract = ""

    if paper_meta and getattr(paper_meta, "abstract", None):
        abstract = paper_meta.abstract.strip()
    else:
        abstract = (scored.get("abstract") or "").strip()

    if score_resp and getattr(score_resp, "is_qualified", False) and abstract_cn:
        return abstract_cn
    return abstract


def _needs_translation(scored: Dict[str, Any]) -> bool:
    return bool(scored["score_response"].is_qualified and (scored.get("abstract") or "").strip())


def _needs_analysis(scored: Dict[str, Any]) -> bool:
    paper_meta = scored.get("paper_metadata")
    return bool(
        scored["score_response"].is_qualified
        and settings.DAILY_ENABLE_DEEP_ANALYSIS
        and paper_meta
        and paper_meta.has_pdf_access()
    )


def _is_paper_complete(scored: Dict[str, Any]) -> bool:
    if not scored["score_response"].is_qualified:
        return True
    if _needs_translation(scored) and not (scored.get("abstract_cn") or "").strip():
        return False
    if _needs_analysis(scored) and not scored.get("analysis"):
        return False
    return True


def _finalize_paper_if_complete(
    scored: Dict[str, Any],
    source: str,
    run_id: str,
    store: DailyResearchStore,
    search_agent: SearchAgent,
) -> bool:
    if not _is_paper_complete(scored):
        return False
    store.mark_completed(run_id, source, scored["paper_id"])
    search_agent.mark_as_processed(scored["paper_id"], source)
    return True


def _submit_postscreen_tasks(
    scored,
    source,
    analysis_agent,
    translation_cache,
    cache_lock,
    postscreen_executor,
    translation_futures,
    analysis_futures,
):
    """为单篇及格论文提交翻译和深度分析任务。"""
    if not scored["score_response"].is_qualified:
        return

    if _needs_translation(scored) and not (scored.get("abstract_cn") or "").strip():
        future = postscreen_executor.submit(
            _translate_single_qualified_paper,
            scored,
            analysis_agent,
            translation_cache,
            cache_lock,
        )
        translation_futures[future] = scored

    if _needs_analysis(scored) and not scored.get("analysis"):
        future = postscreen_executor.submit(_deep_analyze_single_paper, scored, analysis_agent)
        analysis_futures[future] = {"source": source, "paper": scored}


class DailyResearchPipeline:
    """
    每日研究模式流水线。

    从多个数据源抓取论文，评分筛选，深度分析，生成报告，发送通知。
    """

    def run(self):
        """
        执行每日研究完整流程。
        """
        store = None
        run_id = ""
        try:
            print("\n" + "=" * 80)
            print("🚀 多数据源研究系统启动")
            print("=" * 80 + "\n")

            logger.info("=" * 80)
            logger.info("启动多数据源研究系统")
            logger.info("=" * 80)

            if settings.TOKEN_TRACKING_ENABLED:
                token_counter.reset()

            # ==================== 阶段1: 配置加载 ====================
            logger.info(">>> 阶段1: 加载配置...")

            logger.info(f"启用的数据源: {settings.ENABLED_SOURCES}")
            if "arxiv" in settings.ENABLED_SOURCES:
                logger.info(f"ArXiv目标领域: {settings.TARGET_DOMAINS}")
            if settings.TARGET_JOURNALS:
                logger.info(f"目标期刊: {settings.TARGET_JOURNALS}")
            logger.info(f"搜索天数: {settings.SEARCH_DAYS}")
            logger.info(f"最大结果数: {settings.MAX_RESULTS}")
            logger.info(f"启用Reference提取: {settings.ENABLE_REFERENCE_EXTRACTION}")

            # ==================== 阶段2: 关键词准备 ====================
            logger.info(">>> 阶段2: 准备关键词...")

            keyword_agent = KeywordAgent()
            all_keywords = keyword_agent.get_all_keywords()

            if not all_keywords and not settings.is_committee_scoring_enabled():
                logger.error("错误: 未找到任何关键词。请在 configs/config.json 中配置主要关键词。")
                fail_result = RunResult(
                    run_timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    success=False,
                    error_message="未找到任何关键词，请在 configs/config.json 中配置主要关键词",
                )
                if settings.ENABLE_NOTIFICATIONS:
                    try:
                        NotifierAgent().notify(fail_result)
                    except Exception:
                        pass
                return fail_result

            logger.info("关键词准备完成:")
            logger.info(
                f"  - 主要关键词: {len(settings.PRIMARY_KEYWORDS)} 个（权重 {settings.PRIMARY_KEYWORD_WEIGHT}）"
            )
            if settings.ENABLE_REFERENCE_EXTRACTION:
                ref_count = len(all_keywords) - len(settings.PRIMARY_KEYWORDS)
                logger.info(f"  - Reference关键词: {ref_count} 个（权重 0.3-0.8）")
            logger.info(f"  - 关键词总数: {len(all_keywords)} 个")
            logger.info(f"  - 总权重: {sum(all_keywords.values()):.2f}")

            store = DailyResearchStore(settings.DATA_DIR / "daily_research" / "daily_research.db")
            run_id = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            store.create_run(
                run_id,
                search_days=settings.SEARCH_DAYS,
                max_results=settings.MAX_RESULTS,
                enabled_sources=settings.ENABLED_SOURCES,
                keywords=all_keywords,
            )

            total_weight = sum(all_keywords.values())
            if settings.is_committee_scoring_enabled():
                logger.info("  - 评分策略: MLSys 多模型委员会")
                logger.info(f"  - 委员会模型: {', '.join(settings.MLSYS_COMMITTEE_MODELS)}")
                logger.info(f"  - 固定通过分: {settings.MLSYS_PASSING_SCORE:.1f}")
                logger.info(f"  - Fallback 分数: {settings.MLSYS_FALLBACK_SCORE:.1f}")
            else:
                passing_score = settings.calculate_passing_score(total_weight)
                logger.info(f"  - 动态及格分: {passing_score:.1f}")
                logger.info(
                    f"  - 及格分公式: {settings.PASSING_SCORE_BASE} + {settings.PASSING_SCORE_WEIGHT_COEFFICIENT} × {total_weight:.1f}"
                )

            # ==================== 阶段3: 抓取所有最新论文 ====================
            logger.info(">>> 阶段3: 从多个数据源抓取论文...")

            search_agent = SearchAgent(
                history_dir=settings.HISTORY_DIR,
                enabled_sources=settings.ENABLED_SOURCES,
                arxiv_domains=settings.TARGET_DOMAINS,
                journals=settings.TARGET_JOURNALS,
                max_results=settings.MAX_RESULTS,
                max_results_per_source=settings.MAX_RESULTS_PER_SOURCE,
                openalex_email=settings.OPENALEX_EMAIL,
                openalex_api_key=settings.OPENALEX_API_KEY,
                enable_semantic_scholar=settings.ENABLE_SEMANTIC_SCHOLAR_TLDR,
                semantic_scholar_api_key=settings.SEMANTIC_SCHOLAR_API_KEY,
            )

            try:
                papers_by_source: Dict[str, List[PaperMetadata]] = search_agent.fetch_all_papers(
                    days=settings.SEARCH_DAYS
                )
            except ArxivFetchError as afe:
                # ArXiv 抓取彻底失败（多次重试后仍无法获取任何论文）
                error_detail = str(afe)
                logger.error(f"ArXiv 抓取失败，终止本次运行: {error_detail}")
                fetch_fail_result = RunResult(
                    run_timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    success=False,
                    error_message=f"ArXiv 抓取失败: {error_detail}",
                )
                store.complete_run(run_id, status="failed", error_message=f"ArXiv 抓取失败: {error_detail}")
                if settings.ENABLE_NOTIFICATIONS:
                    try:
                        NotifierAgent().notify(fetch_fail_result)
                        NotifierAgent().notify_error(
                            "error_network",
                            service="ArXiv",
                            error_detail=error_detail,
                            suggestion="请检查网络连接、ArXiv 服务状态及相关 API 配置。",
                        )
                    except Exception as ne:
                        logger.warning(f"发送错误通知失败: {ne}")
                return fetch_fail_result

            total_papers_count = sum(len(papers) for papers in papers_by_source.values())

            if total_papers_count == 0:
                logger.info("未找到新论文。")
                print("\n未找到新论文，程序退出。")
                no_papers_result = RunResult(
                    run_timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), success=True
                )
                store.complete_run(run_id, status="completed")
                if settings.ENABLE_NOTIFICATIONS:
                    try:
                        NotifierAgent().notify(no_papers_result)
                    except Exception:
                        pass
                return no_papers_result

            logger.info(
                f"成功抓取 {total_papers_count} 篇新论文（来自 {len(papers_by_source)} 个数据源）"
            )

            # ==================== 阶段4: 对所有论文评分 ====================
            logger.info(">>> 阶段4: 对所有论文进行加权评分，并在及格后立即启动后处理...")

            analysis_agent = AnalysisAgent()

            scored_papers_by_source: Dict[str, List[Dict[str, Any]]] = {}
            analyses_by_source: Dict[str, List[Dict[str, Any]]] = {
                source: [] for source in papers_by_source.keys()
            }

            keyword_tracker = None
            if settings.KEYWORD_TRACKER_ENABLED:
                try:
                    from keyword_tracker import KeywordTracker

                    keyword_tracker = KeywordTracker()
                    logger.debug("KeywordTracker 已初始化")
                except Exception as e:
                    logger.warning(f"KeywordTracker 初始化失败: {e}")

            translation_cache = {}
            cache_lock = threading.Lock()
            translation_futures = {}
            analysis_futures = {}
            logger.debug("翻译缓存已启用")

            postscreen_workers = settings.CONCURRENCY_WORKERS if settings.ENABLE_CONCURRENCY else 1
            postscreen_executor = None
            if settings.ENABLE_CONCURRENCY:
                postscreen_executor = ThreadPoolExecutor(max_workers=postscreen_workers)

            try:
                for source, papers in papers_by_source.items():
                    if not papers:
                        continue

                    logger.info(f"  评分数据源 [{source}]: {len(papers)} 篇论文")
                    scored_papers = []
                    qualified_count = 0

                    use_scoring_concurrency = settings.ENABLE_CONCURRENCY and len(papers) > 1

                    with tqdm(
                        total=len(papers), desc=f"📊 [{source}] 评分", unit="篇", ncols=100
                    ) as pbar:
                        if use_scoring_concurrency:
                            logger.info(f"    使用并发模式 (workers={settings.CONCURRENCY_WORKERS})")
                            with ThreadPoolExecutor(max_workers=settings.CONCURRENCY_WORKERS) as executor:
                                futures = {}
                                for paper in papers:
                                    restored = store.hydrate_scored_paper(source, paper.paper_id)
                                    if restored:
                                        restored.setdefault("analysis", None)
                                        scored_papers.append(restored)
                                        if restored["score_response"].is_qualified:
                                            qualified_count += 1
                                        if restored.get("analysis"):
                                            analyses_by_source[source].append(
                                                {
                                                    "paper_id": restored["paper_id"],
                                                    "analysis": restored["analysis"],
                                                }
                                            )
                                        if postscreen_executor is not None and not _is_paper_complete(restored):
                                            _submit_postscreen_tasks(
                                                restored,
                                                source,
                                                analysis_agent,
                                                translation_cache,
                                                cache_lock,
                                                postscreen_executor,
                                                translation_futures,
                                                analysis_futures,
                                            )
                                        _finalize_paper_if_complete(
                                            restored,
                                            source,
                                            run_id,
                                            store,
                                            search_agent,
                                        )
                                        pbar.update(1)
                                        continue

                                    future = executor.submit(
                                        _score_single_paper,
                                        paper,
                                        source,
                                        analysis_agent,
                                        all_keywords,
                                        keyword_tracker,
                                    )
                                    futures[future] = paper
                                for future in as_completed(futures):
                                    paper = futures[future]
                                    try:
                                        result = future.result()
                                        result.setdefault("analysis", None)
                                        store.upsert_scored_paper(run_id, source, result)
                                        scored_papers.append(result)
                                        if result["score_response"].is_qualified:
                                            qualified_count += 1
                                        if postscreen_executor is not None:
                                            _submit_postscreen_tasks(
                                                result,
                                                source,
                                                analysis_agent,
                                                translation_cache,
                                                cache_lock,
                                                postscreen_executor,
                                                translation_futures,
                                                analysis_futures,
                                            )
                                        _finalize_paper_if_complete(
                                            result,
                                            source,
                                            run_id,
                                            store,
                                            search_agent,
                                        )
                                    except Exception as e:
                                        logger.error(f"论文评分异常 ({paper.title[:30]}...): {e}")
                                    pbar.update(1)
                        else:
                            for idx, paper in enumerate(papers, 1):
                                pbar.set_description(f"📊 [{source}] [{idx}/{len(papers)}]")
                                pbar.set_postfix_str(f"{paper.title[:35]}...")

                                restored = store.hydrate_scored_paper(source, paper.paper_id)
                                if restored:
                                    restored.setdefault("analysis", None)
                                    scored_papers.append(restored)
                                    if restored["score_response"].is_qualified:
                                        qualified_count += 1
                                    if restored.get("analysis"):
                                        analyses_by_source[source].append(
                                            {
                                                "paper_id": restored["paper_id"],
                                                "analysis": restored["analysis"],
                                            }
                                        )
                                    if postscreen_executor is not None and not _is_paper_complete(restored):
                                        _submit_postscreen_tasks(
                                            restored,
                                            source,
                                            analysis_agent,
                                            translation_cache,
                                            cache_lock,
                                            postscreen_executor,
                                            translation_futures,
                                            analysis_futures,
                                        )
                                    elif restored["score_response"].is_qualified:
                                        if _needs_translation(restored) and not (restored.get("abstract_cn") or "").strip():
                                            translation_result = _translate_single_qualified_paper(
                                                restored,
                                                analysis_agent,
                                                translation_cache,
                                                cache_lock,
                                            )
                                            restored["abstract_cn"] = translation_result.get("abstract_cn", "")
                                            store.update_translation(
                                                run_id,
                                                source,
                                                restored["paper_id"],
                                                restored["abstract_cn"],
                                            )
                                        if _needs_analysis(restored) and not restored.get("analysis"):
                                            analysis_result = _deep_analyze_single_paper(
                                                restored, analysis_agent
                                            )
                                            if analysis_result:
                                                restored["analysis"] = analysis_result["analysis"]
                                                analyses_by_source[source].append(
                                                    {
                                                        "paper_id": analysis_result["paper_id"],
                                                        "analysis": analysis_result["analysis"],
                                                    }
                                                )
                                                store.update_analysis(
                                                    run_id,
                                                    source,
                                                    restored["paper_id"],
                                                    analysis_result["analysis"],
                                                )
                                        _finalize_paper_if_complete(
                                            restored,
                                            source,
                                            run_id,
                                            store,
                                            search_agent,
                                        )
                                    else:
                                        _finalize_paper_if_complete(
                                            restored,
                                            source,
                                            run_id,
                                            store,
                                            search_agent,
                                        )
                                    pbar.update(1)
                                    continue

                                result = _score_single_paper(
                                    paper,
                                    source,
                                    analysis_agent,
                                    all_keywords,
                                    keyword_tracker,
                                )
                                result.setdefault("analysis", None)
                                store.upsert_scored_paper(run_id, source, result)
                                scored_papers.append(result)
                                if result["score_response"].is_qualified:
                                    qualified_count += 1
                                if postscreen_executor is not None:
                                    _submit_postscreen_tasks(
                                        result,
                                        source,
                                        analysis_agent,
                                        translation_cache,
                                        cache_lock,
                                        postscreen_executor,
                                        translation_futures,
                                        analysis_futures,
                                    )
                                elif result["score_response"].is_qualified:
                                    translation_result = _translate_single_qualified_paper(
                                        result,
                                        analysis_agent,
                                        translation_cache,
                                        cache_lock,
                                    )
                                    result["abstract_cn"] = translation_result.get("abstract_cn", "")
                                    store.update_translation(
                                        run_id,
                                        source,
                                        result["paper_id"],
                                        result["abstract_cn"],
                                    )
                                    if _needs_analysis(result):
                                        analysis_result = _deep_analyze_single_paper(
                                            result, analysis_agent
                                        )
                                        if analysis_result:
                                            result["analysis"] = analysis_result["analysis"]
                                            analyses_by_source[source].append(
                                                {
                                                    "paper_id": analysis_result["paper_id"],
                                                    "analysis": analysis_result["analysis"],
                                                }
                                            )
                                            store.update_analysis(
                                                run_id,
                                                source,
                                                result["paper_id"],
                                                analysis_result["analysis"],
                                            )
                                    _finalize_paper_if_complete(
                                        result,
                                        source,
                                        run_id,
                                        store,
                                        search_agent,
                                    )
                                else:
                                    _finalize_paper_if_complete(
                                        result,
                                        source,
                                        run_id,
                                        store,
                                        search_agent,
                                    )
                                pbar.update(1)

                    scored_papers_by_source[source] = scored_papers
                    logger.info(f"    [{source}] 评分完成: {qualified_count}/{len(papers)} 篇及格")

                if settings.ENABLE_CONCURRENCY:
                    logger.info(">>> 阶段5: 等待及格论文的摘要翻译与深度分析完成...")
                    if not settings.DAILY_ENABLE_DEEP_ANALYSIS:
                        logger.info("    深度分析已通过配置关闭，仅等待摘要翻译任务")

                    translation_future_count = len(translation_futures)
                    analysis_future_count = len(analysis_futures)

                    if translation_future_count:
                        with tqdm(
                            total=translation_future_count,
                            desc="🌐 摘要翻译",
                            unit="篇",
                            ncols=100,
                        ) as pbar:
                            for future in as_completed(translation_futures):
                                scored = translation_futures[future]
                                source = scored.get("paper_metadata").source if scored.get("paper_metadata") else ""
                                try:
                                    result = future.result()
                                    scored["abstract_cn"] = result.get("abstract_cn", "")
                                    store.update_translation(
                                        run_id,
                                        source,
                                        scored["paper_id"],
                                        scored["abstract_cn"],
                                    )
                                    _finalize_paper_if_complete(
                                        scored,
                                        source,
                                        run_id,
                                        store,
                                        search_agent,
                                    )
                                    if result.get("from_cache"):
                                        logger.debug(f"使用缓存的翻译: {scored['title'][:30]}...")
                                    else:
                                        logger.debug(f"翻译并缓存: {scored['title'][:30]}...")
                                except Exception as e:
                                    store.update_last_error(source, scored["paper_id"], str(e))
                                    logger.error(f"摘要翻译异常 ({scored['title'][:30]}...): {e}")
                                pbar.update(1)

                    if analysis_future_count:
                        with tqdm(
                            total=analysis_future_count,
                            desc="🔬 深度分析",
                            unit="篇",
                            ncols=100,
                        ) as pbar:
                            for future in as_completed(analysis_futures):
                                future_meta = analysis_futures[future]
                                paper_info = future_meta["paper"]
                                source = future_meta["source"]
                                try:
                                    result = future.result()
                                    if result:
                                        paper_info["analysis"] = result["analysis"]
                                        analyses_by_source[source].append(
                                            {
                                                "paper_id": result["paper_id"],
                                                "analysis": result["analysis"],
                                            }
                                        )
                                        store.update_analysis(
                                            run_id,
                                            source,
                                            result["paper_id"],
                                            result["analysis"],
                                        )
                                        _finalize_paper_if_complete(
                                            paper_info,
                                            source,
                                            run_id,
                                            store,
                                            search_agent,
                                        )
                                        pm = result.get("paper_meta")
                                        if pm and pm.arxiv_id:
                                            pbar.write(
                                                f"  ✓ 完成 (via arXiv {pm.arxiv_id}): {result['title'][:50]}..."
                                            )
                                        else:
                                            pbar.write(f"  ✓ 完成: {result['title'][:55]}...")
                                    else:
                                        store.update_last_error(
                                            source,
                                            paper_info["paper_id"],
                                            "deep analysis returned no result",
                                        )
                                        pbar.write(f"  ✗ 失败: {paper_info['title'][:55]}...")
                                except Exception as e:
                                    store.update_last_error(source, paper_info["paper_id"], str(e))
                                    logger.error(
                                        f"深度分析异常 ({paper_info['title'][:30]}...): {e}"
                                    )
                                    pbar.write(f"  ✗ 异常: {paper_info['title'][:55]}...")
                                pbar.update(1)
            finally:
                if postscreen_executor is not None:
                    postscreen_executor.shutdown(wait=True)

            if translation_cache:
                cache_savings = total_papers_count - len(translation_cache)
                if cache_savings > 0:
                    logger.info(f"  翻译缓存节省了 {cache_savings} 次API调用")

            for source, scored_papers in scored_papers_by_source.items():
                qualified_papers = [p for p in scored_papers if p["score_response"].is_qualified]
                papers_with_pdf = [
                    p
                    for p in qualified_papers
                    if p.get("paper_metadata") and p["paper_metadata"].has_pdf_access()
                ]

                if not qualified_papers:
                    logger.info(f">>> 阶段5: [{source}] 没有及格论文")
                    continue

                if not settings.DAILY_ENABLE_DEEP_ANALYSIS:
                    logger.info(f">>> 阶段5: [{source}] 深度分析已关闭")
                    continue

                if not papers_with_pdf:
                    logger.info(
                        f">>> 阶段5: [{source}] {len(qualified_papers)} 篇及格论文均无PDF可用，跳过深度分析"
                    )
                    continue

                logger.info(
                    f">>> 阶段5: [{source}] 深度分析完成: {len(analyses_by_source.get(source, []))}/{len(papers_with_pdf)} 篇成功"
                )

            # ==================== 阶段6: 生成分数据源报告 ====================
            logger.info(">>> 阶段6: 生成分数据源研究报告...")

            reporter = Reporter()
            report_paths = reporter.generate_reports_by_source(
                scored_papers_by_source=scored_papers_by_source,
                keywords_dict=all_keywords,
                analyses_by_source=analyses_by_source,
                token_usage=token_counter.get_summary() if settings.TOKEN_TRACKING_ENABLED else None,
            )

            # ==================== 阶段7: 关键词趋势处理 ====================
            if settings.KEYWORD_TRACKER_ENABLED and settings.KEYWORD_NORMALIZATION_ENABLED:
                logger.info(">>> 阶段7: 运行每日关键词标准化...")
                try:
                    from keyword_tracker import KeywordTracker

                    tracker = keyword_tracker or KeywordTracker()
                    stats = tracker.run_daily_normalization()
                    logger.info(
                        f"  标准化完成: 处理 {stats['processed']} 个, 新增规范词 {stats['new_canonical']}, 合并 {stats['merged']}"
                    )

                    if settings.KEYWORD_REPORT_ENABLED:
                        today = date.today()
                        should_generate_report = False

                        if settings.KEYWORD_REPORT_FREQUENCY == "always":
                            should_generate_report = True
                        elif settings.KEYWORD_REPORT_FREQUENCY == "daily":
                            should_generate_report = True
                        elif settings.KEYWORD_REPORT_FREQUENCY == "weekly":
                            should_generate_report = today.weekday() == 0
                        elif settings.KEYWORD_REPORT_FREQUENCY == "monthly":
                            should_generate_report = today.day == 1

                        if should_generate_report:
                            logger.info("  生成关键词趋势报告...")
                            top_keywords = tracker.get_top_keywords()
                            trends = tracker.get_trends()
                            bar_chart = tracker.generate_bar_chart()
                            trend_chart = tracker.generate_trend_chart()

                            from report.keyword_trend import KeywordTrendReporter
                            kw_reporter = KeywordTrendReporter()
                            trend_paths = kw_reporter.render(
                                top_keywords=top_keywords,
                                trends=trends,
                                bar_chart=bar_chart,
                                trend_chart=trend_chart,
                                today=today,
                                days=tracker.default_days,
                            )
                            logger.info(f"  趋势报告已保存: {trend_paths.get('markdown', '')}")
                        else:
                            logger.info(
                                f"  跳过趋势报告生成 (频率设置: {settings.KEYWORD_REPORT_FREQUENCY})"
                            )

                except Exception as e:
                    logger.warning(f"关键词标准化失败: {e}")

            # ==================== 完成 ====================
            logger.info("=" * 80)
            logger.info("✅ 任务完成！")

            all_scored_flat = []
            for source, scored_papers in scored_papers_by_source.items():
                for p in scored_papers:
                    score_response = p["score_response"]
                    all_scored_flat.append(
                        {
                            "title": p["title"],
                            "score": score_response.total_score,
                            "source": source,
                            "tldr": _get_tldr_text(p),
                            "reasoning": score_response.reasoning,
                            "url": p["url"],
                        }
                    )
            all_scored_flat.sort(key=lambda x: x["score"], reverse=True)
            top_papers = all_scored_flat[: settings.NOTIFICATION_TOP_N]

            run_result = RunResult(
                run_timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                total_papers_fetched=total_papers_count,
                top_papers=top_papers,
            )

            for source, scored_papers in scored_papers_by_source.items():
                source_qualified = sum(1 for p in scored_papers if p["score_response"].is_qualified)
                source_analyzed = len(analyses_by_source.get(source, []))
                run_result.papers_by_source[source] = len(scored_papers)
                run_result.qualified_by_source[source] = source_qualified
                run_result.analyzed_by_source[source] = source_analyzed
                run_result.total_qualified += source_qualified
                run_result.total_analyzed += source_analyzed
                logger.info(
                    f"  [{source}] 抓取: {len(scored_papers)} | 及格: {source_qualified} | 深度分析: {source_analyzed}"
                )

            run_result.report_paths = {s: str(p) for s, p in report_paths.items()}
            if settings.TOKEN_TRACKING_ENABLED:
                run_result.token_usage = token_counter.get_summary()

            store.complete_run(
                run_id,
                status="completed",
                report_paths=run_result.report_paths,
                token_usage=run_result.token_usage,
            )

            logger.info(
                f"  - 总计: 抓取 {total_papers_count} | 及格 {run_result.total_qualified} | 深度分析 {run_result.total_analyzed}"
            )
            logger.info(f"  - 报告位置: {settings.REPORTS_DIR}")
            logger.info("=" * 80)

            print("\n" + "=" * 80)
            print("🎉 所有任务已完成！")
            print("=" * 80)
            print("📊 统计信息:")

            for source, scored_papers in scored_papers_by_source.items():
                source_qualified = run_result.qualified_by_source.get(source, 0)
                source_analyzed = run_result.analyzed_by_source.get(source, 0)
                pct = (source_qualified / len(scored_papers) * 100) if scored_papers else 0
                print(f"   [{source.upper()}]")
                print(f"     • 抓取: {len(scored_papers)} 篇")
                print(f"     • 及格: {source_qualified} 篇 ({pct:.1f}%)")
                if search_agent.can_download_pdf(source):
                    print(f"     • 深度分析: {source_analyzed} 篇")

            print("\n📁 报告位置:")
            for source, path in report_paths.items():
                print(f"   • [{source}] {path}")
            print("=" * 80 + "\n")

            # ==================== 阶段8: 发送通知 ====================
            if settings.ENABLE_NOTIFICATIONS:
                logger.info(">>> 阶段8: 发送通知...")
                try:
                    notifier = NotifierAgent()
                    notifier.notify(run_result)
                    logger.info("通知发送完成")
                except Exception as e:
                    logger.warning(f"通知发送失败: {e}")

            return run_result

        except KeyboardInterrupt:
            try:
                if store and run_id:
                    store.complete_run(run_id, status="interrupted", error_message="KeyboardInterrupt")
            except Exception:
                pass
            logger.warning("\n用户中断程序执行")
            print("\n⚠️  程序已被用户中断")
        except Exception as e:
            try:
                if store and run_id:
                    store.complete_run(run_id, status="failed", error_message=str(e))
            except Exception:
                pass
            logger.error(f"程序执行出错: {e}", exc_info=True)
            print(f"\n❌ 程序执行失败: {e}")
            print("详细错误信息已记录到日志文件")
            import traceback

            traceback.print_exc()

            if settings.ENABLE_NOTIFICATIONS:
                try:
                    fail_result = RunResult(
                        run_timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        success=False,
                        error_message=str(e),
                    )
                    NotifierAgent().notify(fail_result)
                except Exception:
                    pass

            raise
