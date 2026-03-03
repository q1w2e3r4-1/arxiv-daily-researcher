"""
多数据源论文研究系统主程序

支持从多个数据源抓取论文：
- ArXiv：预印本论文（支持PDF深度分析）
- 学术期刊：PRL、PRA等（仅评分和摘要翻译）
"""

import sys
import hashlib
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Dict, List, Any

# 将 src 目录加入 Python 模块搜索路径
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from tqdm import tqdm

from config import settings
from utils.logger import setup_logger
from agents import KeywordAgent, AnalysisAgent
from sources import SearchAgent, PaperMetadata
from report import Reporter
from notifications import NotifierAgent, RunResult

# 初始化系统日志记录器
logger = setup_logger("Main")


def _score_single_paper(
    paper,
    source,
    analysis_agent,
    all_keywords,
    translation_cache,
    cache_lock,
    keyword_tracker,
    search_agent,
):
    """
    对单篇论文进行评分和翻译（供并发调用）。

    线程安全：translation_cache 通过 cache_lock 保护，
    mark_as_processed 由 base_source 内部锁保护。
    """
    score_response = analysis_agent.score_paper_with_keywords(
        title=paper.title,
        authors=paper.get_authors_string(),
        abstract=paper.abstract,
        keywords_dict=all_keywords,
    )

    abstract_cn = ""
    if paper.abstract and paper.abstract.strip():
        abstract_hash = hashlib.md5(paper.abstract.encode("utf-8")).hexdigest()

        with cache_lock:
            cached = translation_cache.get(abstract_hash)

        if cached is not None:
            abstract_cn = cached
            logger.debug(f"使用缓存的翻译: {paper.title[:30]}...")
        else:
            abstract_cn = analysis_agent.translate_abstract(paper.abstract)
            with cache_lock:
                translation_cache[abstract_hash] = abstract_cn
            logger.debug(f"翻译并缓存: {paper.title[:30]}...")

    scored = {
        "paper_metadata": paper,
        "paper_id": paper.paper_id,
        "title": paper.title,
        "authors": paper.get_authors_string(),
        "abstract": paper.abstract,
        "abstract_cn": abstract_cn,
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

    search_agent.mark_as_processed(paper.paper_id, source)

    return scored


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


def main():
    """
    多数据源研究系统主流程。

    工作流程:
    1. 加载配置
    2. 准备关键词（主要关键词 + Reference提取的次要关键词）
    3. 从多个数据源抓取论文
    4. 对所有论文进行加权评分
    5. 对ArXiv及格论文进行深度分析（其他来源跳过）
    6. 按数据源分别生成报告
    """
    try:
        print("\n" + "=" * 80)
        print("🚀 多数据源研究系统启动")
        print("=" * 80 + "\n")

        logger.info("=" * 80)
        logger.info("启动多数据源研究系统")
        logger.info("=" * 80)

        # ==================== 阶段1: 配置加载 ====================
        logger.info(">>> 阶段1: 加载配置...")

        # 打印配置信息
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

        # 获取所有关键词（主要 + Reference提取）
        all_keywords = keyword_agent.get_all_keywords()

        if not all_keywords:
            logger.error("错误: 未找到任何关键词。请在 configs/config.json 中配置主要关键词。")
            fail_result = RunResult(
                run_timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                success=False,
                error_message="未找到任何关键词，请在 configs/config.json 中配置主要关键词",
            )
            if settings.ENABLE_NOTIFICATIONS:
                try:
                    from notifications import NotifierAgent

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

        # 计算动态及格分
        total_weight = sum(all_keywords.values())
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

        # 从所有数据源抓取论文
        papers_by_source: Dict[str, List[PaperMetadata]] = search_agent.fetch_all_papers(
            days=settings.SEARCH_DAYS
        )

        # 计算总数
        total_papers_count = sum(len(papers) for papers in papers_by_source.values())

        if total_papers_count == 0:
            logger.info("未找到新论文。")
            print("\n未找到新论文，程序退出。")
            no_papers_result = RunResult(
                run_timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), success=True
            )
            if settings.ENABLE_NOTIFICATIONS:
                try:
                    from notifications import NotifierAgent

                    NotifierAgent().notify(no_papers_result)
                except Exception:
                    pass
            return no_papers_result

        logger.info(
            f"成功抓取 {total_papers_count} 篇新论文（来自 {len(papers_by_source)} 个数据源）"
        )

        # ==================== 阶段4: 对所有论文评分 ====================
        logger.info(">>> 阶段4: 对所有论文进行加权评分...")

        analysis_agent = AnalysisAgent()
        scored_papers_by_source: Dict[str, List[Dict[str, Any]]] = {}

        # 🆕 优化1: KeywordTracker移到循环外，避免重复创建数据库连接
        keyword_tracker = None
        if settings.KEYWORD_TRACKER_ENABLED:
            try:
                from keyword_tracker import KeywordTracker

                keyword_tracker = KeywordTracker()
                logger.debug("KeywordTracker 已初始化")
            except Exception as e:
                logger.warning(f"KeywordTracker 初始化失败: {e}")

        # 🆕 优化2: 翻译缓存 - 避免重复翻译相同的摘要（arxiv和期刊重复时）
        translation_cache = {}  # {abstract_hash: translation}
        cache_lock = threading.Lock()
        logger.debug("翻译缓存已启用")

        for source, papers in papers_by_source.items():
            if not papers:
                continue

            logger.info(f"  评分数据源 [{source}]: {len(papers)} 篇论文")
            scored_papers = []

            if settings.ENABLE_CONCURRENCY and len(papers) > 1:
                # ========== 并发评分模式 ==========
                logger.info(f"    使用并发模式 (workers={settings.CONCURRENCY_WORKERS})")
                with tqdm(
                    total=len(papers), desc=f"📊 [{source}] 评分", unit="篇", ncols=100
                ) as pbar:
                    with ThreadPoolExecutor(max_workers=settings.CONCURRENCY_WORKERS) as executor:
                        futures = {
                            executor.submit(
                                _score_single_paper,
                                paper,
                                source,
                                analysis_agent,
                                all_keywords,
                                translation_cache,
                                cache_lock,
                                keyword_tracker,
                                search_agent,
                            ): paper
                            for paper in papers
                        }
                        for future in as_completed(futures):
                            try:
                                result = future.result()
                                scored_papers.append(result)
                            except Exception as e:
                                paper = futures[future]
                                logger.error(f"论文评分异常 ({paper.title[:30]}...): {e}")
                            pbar.update(1)
            else:
                # ========== 顺序评分模式 ==========
                with tqdm(
                    total=len(papers), desc=f"📊 [{source}] 评分", unit="篇", ncols=100
                ) as pbar:
                    for idx, paper in enumerate(papers, 1):
                        pbar.set_description(f"📊 [{source}] [{idx}/{len(papers)}]")
                        pbar.set_postfix_str(f"{paper.title[:35]}...")

                        result = _score_single_paper(
                            paper,
                            source,
                            analysis_agent,
                            all_keywords,
                            translation_cache,
                            cache_lock,
                            keyword_tracker,
                            search_agent,
                        )
                        scored_papers.append(result)
                        pbar.update(1)

            scored_papers_by_source[source] = scored_papers

            # 统计该数据源的及格论文
            qualified_count = sum(1 for p in scored_papers if p["score_response"].is_qualified)
            logger.info(f"    [{source}] 评分完成: {qualified_count}/{len(papers)} 篇及格")

        # 🆕 优化2统计: 显示翻译缓存效果
        if translation_cache:
            cache_savings = total_papers_count - len(translation_cache)
            if cache_savings > 0:
                logger.info(f"  翻译缓存节省了 {cache_savings} 次API调用")

        # ==================== 阶段5: 深度分析及格论文 ====================
        analyses_by_source: Dict[str, List[Dict[str, Any]]] = {}

        for source, scored_papers in scored_papers_by_source.items():
            qualified_papers = [p for p in scored_papers if p["score_response"].is_qualified]

            if not qualified_papers:
                logger.info(f">>> 阶段5: [{source}] 没有及格论文，跳过深度分析")
                continue

            # 检查是否有可用的PDF（原始PDF或arXiv PDF）
            papers_with_pdf = []
            for p in qualified_papers:
                paper_meta = p.get("paper_metadata")
                if paper_meta and paper_meta.has_pdf_access():
                    papers_with_pdf.append(p)

            if not papers_with_pdf:
                logger.info(
                    f">>> 阶段5: [{source}] {len(qualified_papers)} 篇及格论文均无PDF可用，跳过深度分析"
                )
                continue

            logger.info(
                f">>> 阶段5: [{source}] 深度分析 {len(papers_with_pdf)}/{len(qualified_papers)} 篇有PDF的及格论文..."
            )

            qualified_papers_with_analysis = []

            if settings.ENABLE_CONCURRENCY and len(papers_with_pdf) > 1:
                # ========== 并发深度分析模式 ==========
                logger.info(f"    使用并发模式 (workers={settings.CONCURRENCY_WORKERS})")
                with tqdm(
                    total=len(papers_with_pdf), desc=f"🔬 [{source}] 深度分析", unit="篇", ncols=100
                ) as pbar:
                    with ThreadPoolExecutor(max_workers=settings.CONCURRENCY_WORKERS) as executor:
                        futures = {
                            executor.submit(
                                _deep_analyze_single_paper, paper_info, analysis_agent
                            ): paper_info
                            for paper_info in papers_with_pdf
                        }
                        for future in as_completed(futures):
                            paper_info = futures[future]
                            try:
                                result = future.result()
                                if result:
                                    qualified_papers_with_analysis.append(
                                        {
                                            "paper_id": result["paper_id"],
                                            "analysis": result["analysis"],
                                        }
                                    )
                                    pm = result.get("paper_meta")
                                    if pm and pm.arxiv_id:
                                        pbar.write(
                                            f"  ✓ 完成 (via arXiv {pm.arxiv_id}): {result['title'][:50]}..."
                                        )
                                    else:
                                        pbar.write(f"  ✓ 完成: {result['title'][:55]}...")
                                else:
                                    pbar.write(f"  ✗ 失败: {paper_info['title'][:55]}...")
                            except Exception as e:
                                logger.error(f"深度分析异常 ({paper_info['title'][:30]}...): {e}")
                                pbar.write(f"  ✗ 异常: {paper_info['title'][:55]}...")
                            pbar.update(1)
            else:
                # ========== 顺序深度分析模式 ==========
                with tqdm(
                    total=len(papers_with_pdf), desc=f"🔬 [{source}] 深度分析", unit="篇", ncols=100
                ) as pbar:
                    for idx, paper_info in enumerate(papers_with_pdf, 1):
                        pbar.set_description(f"🔬 [{source}] [{idx}/{len(papers_with_pdf)}]")
                        pbar.set_postfix_str(f"{paper_info['title'][:35]}...")

                        result = _deep_analyze_single_paper(paper_info, analysis_agent)

                        if result:
                            qualified_papers_with_analysis.append(
                                {"paper_id": result["paper_id"], "analysis": result["analysis"]}
                            )
                            pm = result.get("paper_meta")
                            if pm and pm.arxiv_id:
                                pbar.write(
                                    f"  ✓ 完成 (via arXiv {pm.arxiv_id}): {result['title'][:50]}..."
                                )
                            else:
                                pbar.write(f"  ✓ 完成: {result['title'][:55]}...")
                        else:
                            pbar.write(f"  ✗ 失败: {paper_info['title'][:55]}...")

                        pbar.update(1)

            analyses_by_source[source] = qualified_papers_with_analysis
            logger.info(
                f"    [{source}] 深度分析完成: {len(qualified_papers_with_analysis)}/{len(papers_with_pdf)} 篇成功"
            )

        # ==================== 阶段6: 生成分数据源报告 ====================
        logger.info(">>> 阶段6: 生成分数据源研究报告...")

        reporter = Reporter()
        report_paths = reporter.generate_reports_by_source(
            scored_papers_by_source=scored_papers_by_source,
            keywords_dict=all_keywords,
            analyses_by_source=analyses_by_source,
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

                # 根据配置的频率决定是否生成趋势报告
                if settings.KEYWORD_REPORT_ENABLED:
                    from datetime import date

                    today = date.today()
                    should_generate_report = False

                    if settings.KEYWORD_REPORT_FREQUENCY == "always":
                        should_generate_report = True
                    elif settings.KEYWORD_REPORT_FREQUENCY == "daily":
                        should_generate_report = True
                    elif settings.KEYWORD_REPORT_FREQUENCY == "weekly":
                        # 每周一生成
                        should_generate_report = today.weekday() == 0
                    elif settings.KEYWORD_REPORT_FREQUENCY == "monthly":
                        # 每月1号生成
                        should_generate_report = today.day == 1

                    if should_generate_report:
                        logger.info("  生成关键词趋势报告...")
                        trend_report_path = (
                            settings.REPORTS_DIR / f"keyword_trends_{today.isoformat()}.md"
                        )
                        bar_chart = tracker.generate_bar_chart()
                        trend_chart = tracker.generate_trend_chart()
                        top_keywords = tracker.get_top_keywords()

                        with open(trend_report_path, "w", encoding="utf-8") as f:
                            f.write("# 关键词趋势分析报告\n\n")
                            f.write(f"生成日期: {today}\n\n")
                            f.write("## 热门关键词排名\n\n")
                            if bar_chart:
                                f.write(bar_chart + "\n\n")
                            f.write("## 关键词趋势变化\n\n")
                            if trend_chart:
                                f.write(trend_chart + "\n\n")
                            f.write("## 统计表格\n\n")
                            f.write("| Rank | Keyword | Count | Category |\n")
                            f.write("|------|---------|-------|----------|\n")
                            for i, kw in enumerate(top_keywords, 1):
                                f.write(
                                    f"| {i} | {kw['keyword']} | {kw['count']} | {kw.get('category') or '-'} |\n"
                                )

                        logger.info(f"  趋势报告已保存: {trend_report_path}")
                    else:
                        logger.info(
                            f"  跳过趋势报告生成 (频率设置: {settings.KEYWORD_REPORT_FREQUENCY})"
                        )

            except Exception as e:
                logger.warning(f"关键词标准化失败: {e}")

        # ==================== 完成 ====================
        logger.info("=" * 80)
        logger.info("✅ 任务完成！")

        # 收集 Top-N 论文（按总分排序，用于通知）
        all_scored_flat = []
        for source, scored_papers in scored_papers_by_source.items():
            for p in scored_papers:
                all_scored_flat.append(
                    {
                        "title": p["title"],
                        "score": p["score_response"].total_score,
                        "source": source,
                        "tldr": p["score_response"].tldr,
                        "url": p["url"],
                    }
                )
        all_scored_flat.sort(key=lambda x: x["score"], reverse=True)
        top_papers = all_scored_flat[: settings.NOTIFICATION_TOP_N]

        # 构建运行结果
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

        logger.info(
            f"  - 总计: 抓取 {total_papers_count} | 及格 {run_result.total_qualified} | 深度分析 {run_result.total_analyzed}"
        )
        logger.info(f"  - 报告位置: {settings.REPORTS_DIR}")
        logger.info("=" * 80)

        # 打印控制台摘要
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
                from notifications import NotifierAgent

                notifier = NotifierAgent()
                notifier.notify(run_result)
                logger.info("通知发送完成")
            except Exception as e:
                logger.warning(f"通知发送失败: {e}")

        return run_result

    except KeyboardInterrupt:
        logger.warning("\n用户中断程序执行")
        print("\n⚠️  程序已被用户中断")
    except Exception as e:
        logger.error(f"程序执行出错: {e}", exc_info=True)
        print(f"\n❌ 程序执行失败: {e}")
        print("详细错误信息已记录到日志文件")
        import traceback

        traceback.print_exc()

        # 发送失败通知
        if settings.ENABLE_NOTIFICATIONS:
            try:
                from notifications import NotifierAgent

                fail_result = RunResult(
                    run_timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    success=False,
                    error_message=str(e),
                )
                notifier = NotifierAgent()
                notifier.notify(fail_result)
            except Exception:
                pass  # 通知本身失败不应阻塞

        raise


if __name__ == "__main__":
    settings.ensure_directories()

    # 自动更新检查
    if settings.AUTO_UPDATE_ENABLED:
        try:
            from utils.updater import check_and_update

            check_and_update(logger)
        except Exception as e:
            logger.warning(f"自动更新检查失败: {e}")

    main()
