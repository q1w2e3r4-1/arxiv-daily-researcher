"use strict";

// Browser-only contract smoke. Every API response is synthetic; the script
// never points a browser at the owner's mounted data or live WebUI.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const http = require("node:http");
const path = require("node:path");
const { chromium } = require("playwright");

const staticRoot = path.resolve(__dirname, "../src/modern_webui/static");
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
    let dismissed = false;
    const fixturePaper = { entity_id: "p1", paper_id: "p1", source: "arxiv", sources: ["arxiv"], title: "Demo inference optimization", screening_prompt_version: "1.8", screening_origin: "frozen_review", total_score: null, is_qualified: true, authors: [], variants: [] };
    page.on("pageerror", (error) => pageErrors.push(error.message));
    await page.route("**/api/**", async (route) => {
      const url = new URL(route.request().url());
      const endpoint = url.pathname;
      let payload;
      if (endpoint === "/api/auth/status") payload = { enabled: false, authenticated: true, configured: false, username: "smoke" };
      else if (endpoint === "/api/settings") payload = { config: {}, env: {}, secrets: {}, builtin_sources: [], current_version: "4.7" };
      else if (endpoint === "/api/version") payload = { current_version: "4.7", latest_version: "4.7", update_available: false, checked: false };
      else if (endpoint === "/api/i18n") payload = { items: {} };
      else if (endpoint === "/api/papers") {
        paperRequests.push(url.searchParams.toString());
        payload = { available: true, sources: ["arxiv"], total: !dismissed && (url.searchParams.has("query") || url.searchParams.has("min_score")) ? 1 : 0,
          items: !dismissed && (url.searchParams.has("query") || url.searchParams.has("min_score")) ? [fixturePaper] : [] };
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
    await page.locator(".paper-card summary").click();
    await page.screenshot({ path: path.resolve(__dirname, "../assets/webui_paper_window_zh.png"), fullPage: true });
    await page.locator('[data-paper-preference="dislike"]').click();
    await page.locator(".paper-card").waitFor({ state: "detached" });
    await page.goto(`${base}/#content/favorites`);
    await page.locator("[data-trash-restore]").waitFor();
    await page.screenshot({ path: path.resolve(__dirname, "../assets/webui_paper_trash_zh.png"), fullPage: true });
    await page.locator("#language-button").click();
    await page.locator("[data-trash-restore]").waitFor();
    await page.screenshot({ path: path.resolve(__dirname, "../assets/webui_paper_trash_en.png"), fullPage: true });
    await page.locator("#theme-button").click();
    await page.setViewportSize({ width: 390, height: 844 });
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 2));
    assert.match(await page.locator("#trash-papers").textContent(), /Trash/);
    await page.locator("[data-trash-restore]").click();
    await page.locator("[data-trash-restore]").waitFor({ state: "detached" });
    await page.goto(`${base}/#content/paper_search`);
    await page.locator(".paper-card").waitFor();
    assert.equal(await page.locator(".paper-card").count(), 1);
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 2));
    await page.setViewportSize({ width: 1280, height: 900 });

    await page.locator("#theme-button").click();
    await page.screenshot({ path: path.resolve(__dirname, "../assets/webui_paper_window_en.png"), fullPage: true });

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
