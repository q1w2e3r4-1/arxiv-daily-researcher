"use strict";

// Browser-only contract smoke. Every API response is synthetic; the script
// never points a browser at the owner's mounted data or live WebUI.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const http = require("node:http");
const path = require("node:path");
const { chromium } = require("playwright");

const staticRoot = path.resolve(__dirname, "../src/modern_webui/static");
const screenshotRoot = process.env.ADR_SCREENSHOT_OUTPUT_DIR || path.resolve(__dirname, "../assets");
const reports = [
  { id: "r1", name: "ARXIV_Report_2026-09-25_08-00-00.html", label: "2026-09-25 · 08:00", source: "arxiv", source_label: "arXiv", type: "daily", date: "2026-09-25", modified_at: "2026-09-25T08:00:00", size_bytes: 300 },
  { id: "r2", name: "ARXIV_Report_2026-09-24_08-00-00.html", label: "2026-09-24 · 08:00", source: "arxiv", source_label: "arXiv", type: "daily", date: "2026-09-24", modified_at: "2026-09-24T08:00:00", size_bytes: 300 },
];
const supplements = [
  { id: "s1", name: "Supplement_Report_2026-09-25_08-00-00.html", label: "2026-09-25 · 08:00", source: "arxiv", source_label: "arXiv", type: "supplement", date: "2026-09-25", modified_at: "2026-09-25T08:00:00", size_bytes: 300 },
  { id: "s2", name: "Supplement_Report_2026-09-24_08-00-00.html", label: "2026-09-24 · 08:00", source: "arxiv", source_label: "arXiv", type: "supplement", date: "2026-09-24", modified_at: "2026-09-24T08:00:00", size_bytes: 300 },
];
const logs = [
  { id: "l1", name: "run-one.log", category: "run", modified_at: "2026-09-25T08:00:00", size_bytes: 120 },
  { id: "l2", name: "run-two.log", category: "run", modified_at: "2026-09-24T08:00:00", size_bytes: 110 },
];

function serveStatic(request, response) {
  const requested = new URL(request.url, "http://localhost").pathname;
  const name = requested === "/" ? "index.html" : requested.startsWith("/assets/") ? path.basename(requested) : "";
  const file = name ? path.join(staticRoot, name) : "";
  if (!file || !fs.existsSync(file)) {
    response.writeHead(404).end("Not found");
    return;
  }
  const contentType = name.endsWith(".js") ? "text/javascript" : name.endsWith(".css") ? "text/css" : name.endsWith(".svg") ? "image/svg+xml" : name.endsWith(".png") ? "image/png" : "text/html";
  response.writeHead(200, { "Content-Type": contentType });
  fs.createReadStream(file).pipe(response);
}

async function main() {
  const server = http.createServer(serveStatic);
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const base = `http://127.0.0.1:${server.address().port}`;
  let browser;
  try {
    browser = await chromium.launch({ headless: true, ...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH } : {}) });
    const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
    const pageErrors = [];
    const paperRequests = [];
    let savedConfiguration = {};
    let dismissed = false;
    const fixtureAnalysis = {
      chinese_title: "演示论文：共享缓存与推理调度优化",
      full_text_tldr: "这是用于界面验证的虚构论文。多请求推理面临重复缓存占用和调度等待。演示方案通过复用公共前缀并按资源需求调度，减少重复工作。报告用四部分解释问题、观察、设计与结果。",
      summary: "多请求推理中的缓存重复占用会挤压并发空间，排队等待也会影响响应速度。本文演示如何围绕这些瓶颈组织阅读报告。",
      innovations: "1. **重复内容占用缓存。** 多个请求可能使用相同的输入前缀，分别存储会造成额外占用。这个观察推动了缓存复用设计。\n\n2. **请求资源需求不同。** 固定调度顺序难以兼顾响应速度与资源利用，需要根据实际需求安排执行。",
      methodology: "1. **复用公共前缀。** 将重复内容对应的缓存统一管理，减少重复存储，为更多请求留出空间。\n\n2. **按资源需求调度。** 根据请求状态安排执行顺序，缓解排队等待。这些机制对应前述两个问题。",
      key_results: "演示评测围绕缓存占用与响应速度展开，结果说明系统设计如何缓解前述瓶颈。此处不提供虚构的性能数字。",
      __meta: { content_source: "pdf", private_marker: "not-for-display" },
    };
    const fixturePaper = { entity_id: "p1", paper_id: "p1", source: "arxiv", sources: ["arxiv"], title: "Demo inference optimization", screening_prompt_version: "1.8", screening_origin: "frozen_review", total_score: null, is_qualified: true, authors: [], tldr: "Legacy scoring TLDR", variants: [{ source: "arxiv", tldr: "Legacy variant TLDR", analysis_status: "succeeded", analysis: fixtureAnalysis }] };
    let exportFails = false, paginated = false;
    const exportRequests = [];
    page.on("pageerror", (error) => pageErrors.push(error.message));
    await page.route("**/api/**", async (route) => {
      const url = new URL(route.request().url());
      const endpoint = url.pathname;
      let payload;
      if (endpoint === "/api/auth/status") payload = { enabled: false, authenticated: true, configured: false, username: "smoke" };
      else if (endpoint === "/api/settings") {
        if (route.request().method() === "PUT") savedConfiguration = route.request().postDataJSON().config;
        payload = { config: savedConfiguration, env: {}, secrets: {}, builtin_sources: [], current_version: "4.7" };
      }
      else if (endpoint === "/api/version") payload = { current_version: "4.7", latest_version: "4.7", update_available: false, checked: false };
      else if (endpoint === "/api/i18n") payload = { items: {} };
      else if (endpoint === "/api/papers/export") {
        exportRequests.push(route.request().postDataJSON());
        if (exportFails) return route.fulfill({ status: 400, contentType: "application/json", body: JSON.stringify({ detail: "Synthetic export failure" }) });
        return route.fulfill({ status: 200, contentType: "application/pdf", headers: { "content-disposition": 'attachment; filename="paper-reading-reports.pdf"' }, body: "%PDF-1.7\nSynthetic download fixture" });
      }
      else if (endpoint === "/api/papers") {
        paperRequests.push(url.searchParams.toString());
        payload = { available: true, sources: ["arxiv"], total: !dismissed && (url.searchParams.has("query") || url.searchParams.has("min_score")) ? 1 : 0,
          items: !dismissed && (url.searchParams.has("query") || url.searchParams.has("min_score")) ? [fixturePaper] : [] };
        if (paginated) payload = {available: true, sources: ["arxiv"], total: 21, items: [Number(url.searchParams.get("offset")) ? {...fixturePaper, entity_id: "p2", paper_id: "p2", title: "Second page paper"} : fixturePaper]};
      } else if (endpoint === "/api/preferences") {
        const body = route.request().postDataJSON();
        dismissed = body.preference === "dislike";
        payload = { ok: true, preference: body.preference };
      } else if (endpoint === "/api/trash") payload = { available: true, total: dismissed ? 1 : 0, items: dismissed ? [{ ...fixturePaper, preference: "dislike", updated_at: "2026-08-20T08:00:00" }] : [] };
      else if (endpoint === "/api/favorites") payload = { available: true, counts: { like: 0, dislike: dismissed ? 1 : 0 }, liked: [], authors: [], keywords: [] };
      else if (endpoint === "/api/reports") payload = { daily: reports, trend: [], other: supplements };
      else if (/^\/api\/reports\/[rs][12]\/papers$/.test(endpoint)) payload = { items: [] };
      else if (/^\/api\/reports\/[rs][12]\/file$/.test(endpoint)) {
        await route.fulfill({ status: 200, contentType: "text/html", body: '<!doctype html><html><body><div class="card pass"><div class="field">Fixture report</div></div></body></html>' });
        return;
      } else if (endpoint === "/api/logs") payload = { items: logs };
      else if (/^\/api\/logs\/l[12]$/.test(endpoint)) payload = { name: endpoint.endsWith("l1") ? logs[0].name : logs[1].name, content: "Fixture log", truncated: false };
      else throw new Error(`Unexpected browser smoke request: ${endpoint}`);
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(payload) });
    });

    await page.goto(`${base}/#content/paper_search`);
    await page.locator("#search-score").waitFor();
    assert.equal(await page.locator("#search-score").getAttribute("min"), null);
    await page.locator("#search-score").fill("0");
    await page.locator("#search-run").click();
    await page.locator(".score-pill").waitFor();
    assert.equal((await page.locator(".score-pill").textContent()).trim(), "—");
    assert(paperRequests.some((query) => new URLSearchParams(query).get("min_score") === "0"));

    await Promise.all([page.waitForResponse(response => response.url().includes("/api/papers?") && response.url().includes("completed_from")), page.locator('[data-search-days="14"]').click()]);
    const windowQuery = new URLSearchParams(paperRequests.at(-1));
    assert.equal(windowQuery.get("qualified_only"), "true");
    assert(windowQuery.get("completed_from"));
    await page.locator(".paper-card > summary").click();
    assert.equal(await page.locator(".analysis-section").count(), 4);
    assert.equal(await page.locator(".paper-tldr").count(), 1);
    assert(!(await page.locator(".paper-content").textContent()).includes("Legacy"));
    assert.equal(await page.locator(".analysis-section ol").count(), 2);
    assert.match(await page.locator(".analysis-section strong").first().textContent(), /重复内容/);
    assert.equal(await page.locator(".paper-analysis pre").count(), 0);
    assert(!(await page.locator(".analysis-report").textContent()).includes("not-for-display"));
    assert(!(await page.locator(".paper-content").textContent()).includes("不代表已完成 PDF"));
    await page.setViewportSize({ width: 390, height: 844 });
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 2));
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({ path: path.join(screenshotRoot, "webui_paper_report_zh.png"), fullPage: true });
    await page.screenshot({ path: path.join(screenshotRoot, "webui_paper_window_zh.png"), fullPage: true });
    await page.locator('[data-paper-preference="dislike"]').click();
    await page.locator(".paper-card").waitFor({ state: "detached" });
    await page.goto(`${base}/#content/favorites`);
    await page.locator("[data-trash-restore]").waitFor();
    await page.screenshot({ path: path.join(screenshotRoot, "webui_paper_trash_zh.png"), fullPage: true });
    await page.locator("#language-button").click();
    await page.locator("[data-trash-restore]").waitFor();
    await page.screenshot({ path: path.join(screenshotRoot, "webui_paper_trash_en.png"), fullPage: true });
    await page.locator("#theme-button").click();
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.setViewportSize({ width: 390, height: 844 });
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 2));
    assert.match(await page.locator("#trash-papers").textContent(), /Trash/);
    await page.locator("[data-trash-restore]").click();
    await page.locator("[data-trash-restore]").waitFor({ state: "detached" });
    await page.goto(`${base}/#content/paper_search`);
    await page.locator(".paper-card").waitFor();
    assert.equal(await page.locator(".paper-card").count(), 1);
    await page.locator(".paper-card > summary").click();
    assert.equal(await page.locator(".analysis-section").count(), 4);
    assert.equal(await page.locator(".paper-tldr").count(), 1);
    assert(!(await page.locator(".paper-content").textContent()).includes("Legacy"));
    assert.match(await page.locator(".analysis-section h5").nth(1).textContent(), /Observations/);
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 2));
    await page.setViewportSize({ width: 1280, height: 900 });

    await page.locator("#theme-button").click();
    await page.screenshot({ path: path.join(screenshotRoot, "webui_paper_report_en.png"), fullPage: true });
    await page.screenshot({ path: path.join(screenshotRoot, "webui_paper_window_en.png"), fullPage: true });
    // Selection remains across pages; failures preserve it for a retry.
    paginated = true;
    await page.locator("#search-run").click();
    await page.locator("#search-next").waitFor();
    await page.locator('[data-paper-export-id="p1"]').check();
    await page.locator("#search-next").click();
    await page.locator('[data-paper-export-id="p2"]').waitFor();
    await page.locator("#paper-export-page").click();
    assert.match(await page.locator("#paper-export-count").textContent(), /2 \/ 100/);
    await page.locator("#search-prev").click();
    await page.locator('[data-paper-export-id="p1"]').waitFor();
    assert(await page.locator('[data-paper-export-id="p1"]').isChecked());
    exportFails = true;
    await page.locator("#paper-export-download").click();
    await page.locator("#paper-export-status.error-message").waitFor();
    assert.match(await page.locator("#paper-export-status").textContent(), /Synthetic export failure/);
    assert.deepEqual(exportRequests.at(-1).entity_ids, ["p1", "p2"]);
    exportFails = false;
    const downloadPromise = page.waitForEvent("download");
    await page.locator("#paper-export-download").click();
    const download = await downloadPromise;
    assert.equal(download.suggestedFilename(), "paper-reading-reports.pdf");
    assert.equal(await download.failure(), null);
    await page.locator("#paper-export-clear").click();
    assert(await page.locator("#paper-export-download").isDisabled());
    paginated = false;
    await page.locator("#search-run").click();
    await page.locator(".paper-variant").waitFor({state: "attached"});

    // Provider prose is inert, legacy arrays/custom fields remain readable,
    // and abstract fallback must not expose a purported full-text TL;DR.
    await page.locator(".paper-variant").evaluate(node => { node.innerHTML = paperAnalysisMarkup({
      summary: '<img src=x onerror="window.reportInjection=true">',
      innovations: ["Legacy point one", "Legacy point two"], custom_field: "Other stored analysis",
      full_text_tldr: "Must not show", __meta: { content_source: "abstract_fallback" }
    }); });
    assert.equal(await page.locator(".analysis-report img").count(), 0);
    assert.equal(await page.locator(".analysis-report li").count(), 2);
    assert.match(await page.locator(".analysis-report").textContent(), /Other stored analysis/);
    assert(!(await page.locator(".analysis-report").textContent()).includes("Must not show"));
    assert.equal(await page.evaluate(() => window.reportInjection), undefined);

    assert.equal(await page.evaluate(() => paperTldr({tldr: "Scoring fallback", variants: [{analysis: {full_text_tldr: "Untrusted", __meta: {content_source: "abstract_fallback"}}}]})), "Scoring fallback");
    assert.equal(await page.evaluate(() => paperTldr({source: "acm", paper_id: "preferred", variants: [{source: "arxiv", analysis: {full_text_tldr: "Other", __meta: {content_source: "pdf"}}}, {source: "acm", paper_id: "preferred", analysis: {full_text_tldr: "Preferred", __meta: {content_source: "pdf"}}}]})), "Preferred");

    await page.goto(`${base}/#configuration/advanced`);
    const idleField = page.locator('[data-field="llm_analysis_idle_timeout_seconds"]');
    await idleField.waitFor();
    await idleField.fill("45");
    assert(await page.locator("#save-button").evaluate(node => node.classList.contains("has-unsaved")));
    await page.locator("#save-button").click();
    await page.waitForFunction(() => !document.querySelector("#save-button").classList.contains("has-unsaved"));
    assert.equal(savedConfiguration.llm_analysis_idle_timeout_seconds, 45);
    await page.setViewportSize({ width: 390, height: 844 });
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 2));
    await page.setViewportSize({ width: 1280, height: 900 });

    await page.goto(`${base}/#content/reports`);
    await page.locator('[data-scroll-select="daily:arxiv"]').waitFor();
    assert.equal(await page.locator("[data-report-select-option]").count(), 0);
    await page.locator('[data-scroll-select="daily:arxiv"] summary').click();
    await page.locator("[data-report-select-option]").first().waitFor();
    assert.equal(await page.locator("[data-report-select-option]").count(), 2);
    await page.locator('[data-report-id="r2"]').click();
    await page.locator(".report-file-info", { hasText: reports[1].name }).waitFor();
    await page.locator('[data-scroll-select="supplement:arxiv"] summary').click();
    await page.locator('[data-report-id="s2"]').click();
    await page.locator(".report-file-info", { hasText: supplements[1].name }).waitFor();
    assert.match(await page.locator('[data-scroll-select="supplement:arxiv"] summary').textContent(), /补充报告|Supplement Report/);

    await page.goto(`${base}/#system/logs`);
    await page.locator('[data-scroll-select="log-run-select"]').waitFor();
    assert.equal(await page.locator("[data-log-select-option]").count(), 0);
    await page.locator('[data-scroll-select="log-run-select"] summary').click();
    await page.locator("[data-log-select-option]").first().waitFor();
    assert.equal(await page.locator("[data-log-select-option]").count(), 2);
    await page.locator('[data-log-id="l2"]').click();
    await page.locator(".log-content", { hasText: logs[1].name }).waitFor();
    assert.deepEqual(pageErrors, []);
    console.log("WebUI browser smoke passed (search, reports, logs).");
  } finally {
    if (browser) await browser.close();
    await new Promise((resolve) => server.close(resolve));
  }
}

main().catch((error) => { console.error(error); process.exitCode = 1; });
