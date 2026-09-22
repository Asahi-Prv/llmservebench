"use strict";

/* llmservebench i18n - ja/en dictionaries
 * 新しい言語はここに辞書を追加するだけで対応できます。
 * 使い方:
 *   t("key")              静的テキスト (data-i18n 属性でも自動適用)
 *   t("key", {name: "x"}) {name} プレースホルダー置換
 *   setLang("en")         言語切替 (localStorage に保存)
 */

const I18N = {
  en: {
    "doc.title": "llmservebench - LLM inference backend benchmark",
    "app.subtitle": "Benchmark & compare LLM inference backends (OpenAI-compatible APIs)",

    "tab.single": "Single benchmark",
    "tab.compare": "Backend comparison",

    "target.title": "Target",
    "label.baseUrl": "Base URL",
    "label.model": "Model",
    "label.apiKey": "API key (optional)",
    "label.apiKeyPlaceholder": "Leave empty if not set",
    "fetchModels": "Fetch",

    "compare.title": "Targets (compare 2+ backends)",
    "compare.addBackend": "+ Add backend",
    "compare.run": "Run comparison",
    "target.name": "Name",

    "common.title": "Common settings",
    "common.parallelLevels": "Parallelism (comma-separated)",
    "common.maxTokens": "max tokens",
    "common.runs": "Runs",
    "common.parallelRuns": "Parallel rounds",
    "common.prefillTokens": "Prefill target tokens",
    "common.temperature": "temperature (optional)",
    "common.temperaturePlaceholder": "unset",
    "common.seed": "seed (optional)",
    "common.seedPlaceholder": "unset",
    "common.warmup": "Send warmup request",
    "common.randomize": "Randomize prompts (prefix-cache busting)",

    "run": "Run benchmark",
    "running": "Running...",
    "progress.title": "Progress",
    "result.title": "Results",
    "export.json": "Download JSON",
    "export.md": "Download Markdown",

    "log.info": "[info] {msg}",
    "log.warn": "[warn] {msg}",
    "log.error": "[ERROR] {msg}",
    "log.target": "##### target: {name} #####",
    "log.targetError": "[error] target '{name}': {msg}",
    "log.phaseEnd": "== {name} done ==",
    "log.reqGen": "  #{i}: ttft={ttft} gen={rate}",
    "log.reqPrefill": "  #{i}: ttft={ttft} prompt={rate}",
    "log.reqError": "  #{i}: ERROR {msg}",
    "log.runDone": "  run {run}: aggregate={rate} wall={wall}",
    "log.done": "== all done ==",

    "stat.ttft": "TTFT (median)",
    "stat.gen": "Generation speed (median)",
    "stat.tpot": "TPOT (median)",
    "stat.prefill": "Prefill speed (median)",
    "stat.peak": "Aggregate throughput (peak)",

    "detail.single": "Single stream",
    "detail.prefill": "Prefill (long prompt)",
    "detail.parallel": "Parallel throughput",

    "table.metric": "Metric",
    "table.mean": "mean",
    "table.median": "median",
    "table.p95": "p95",
    "table.min": "min",
    "table.max": "max",
    "table.parallelism": "parallelism",
    "table.aggPeak": "agg tok/s (peak)",
    "table.ttftMed": "TTFT median (s)",
    "table.perReq": "per-req tok/s median",
    "table.ok": "ok/total",
    "table.target": "target",
    "table.model": "model",
    "table.tpotCol": "TPOT (s)",
    "table.prefillCol": "prefill (tok/s)",
    "table.ttftCol": "TTFT (s)",
    "table.genCol": "gen tok/s (median)",

    "compare.bestNote": "Comparison (green = best per metric)",
    "compare.charts": "Comparison charts",
    "compare.details": "Details",
    "chart.gen": "Generation speed (median, tok/s)",
    "chart.ttft": "TTFT (median, s)",
    "chart.peak": "Aggregate throughput (peak, tok/s)",

    "alert.missingTarget": "Base URL and Model are required for all targets",
    "alert.startFailed": "Could not start",
    "alert.connFailed": "Cannot connect to server: {err}",
    "alert.noBaseUrl": "Enter a Base URL",
    "alert.modelsFailed": "Failed to fetch models",
    "alert.connError": "Connection error: {err}",
    "alert.downloadFailed": "Download failed: {err}",
    "alert.reportFailed": "Failed to fetch report",
  },

  ja: {
    "doc.title": "llmservebench - LLM推論バックエンド評価",
    "app.subtitle": "LLM推論バックエンド (OpenAI互換API) のベンチマーク & 比較",

    "tab.single": "単一ベンチ",
    "tab.compare": "バックエンド比較",

    "target.title": "ターゲット",
    "label.baseUrl": "Base URL",
    "label.model": "Model",
    "label.apiKey": "API Key (任意)",
    "label.apiKeyPlaceholder": "未設定なら空欄",
    "fetchModels": "取得",

    "compare.title": "ターゲット (2つ以上のバックエンドを比較)",
    "compare.addBackend": "+ バックエンドを追加",
    "compare.run": "比較ベンチ実行",
    "target.name": "名前",

    "common.title": "共通設定",
    "common.parallelLevels": "並列数 (カンマ区切り)",
    "common.maxTokens": "max tokens",
    "common.runs": "実行回数 (runs)",
    "common.parallelRuns": "並列テスト回数",
    "common.prefillTokens": "prefill目標トークン数",
    "common.temperature": "temperature (任意)",
    "common.temperaturePlaceholder": "未指定",
    "common.seed": "seed (任意)",
    "common.seedPlaceholder": "未指定",
    "common.warmup": "ウォームアップを行う",
    "common.randomize": "プロンプトをランダム化 (prefix cache 対策)",

    "run": "ベンチマーク実行",
    "running": "実行中...",
    "progress.title": "進行状況",
    "result.title": "結果",
    "export.json": "JSON をダウンロード",
    "export.md": "Markdown をダウンロード",

    "log.info": "[info] {msg}",
    "log.warn": "[warn] {msg}",
    "log.error": "[ERROR] {msg}",
    "log.target": "##### target: {name} #####",
    "log.targetError": "[error] target '{name}': {msg}",
    "log.phaseEnd": "== {name} 完了 ==",
    "log.reqGen": "  #{i}: ttft={ttft} gen={rate}",
    "log.reqPrefill": "  #{i}: ttft={ttft} prompt={rate}",
    "log.reqError": "  #{i}: ERROR {msg}",
    "log.runDone": "  run {run}: aggregate={rate} wall={wall}",
    "log.done": "== all done ==",

    "stat.ttft": "TTFT (median)",
    "stat.gen": "生成速度 (median)",
    "stat.tpot": "TPOT (median)",
    "stat.prefill": "prefill速度 (median)",
    "stat.peak": "並列集約スループット (peak)",

    "detail.single": "単一ストリーム",
    "detail.prefill": "prefill (長プロンプト)",
    "detail.parallel": "並列スループット",

    "table.metric": "指標",
    "table.mean": "mean",
    "table.median": "median",
    "table.p95": "p95",
    "table.min": "min",
    "table.max": "max",
    "table.parallelism": "parallelism",
    "table.aggPeak": "集約 tok/s (peak)",
    "table.ttftMed": "TTFT median (s)",
    "table.perReq": "per-req tok/s median",
    "table.ok": "ok/total",
    "table.target": "target",
    "table.model": "model",
    "table.tpotCol": "TPOT (s)",
    "table.prefillCol": "prefill (tok/s)",
    "table.ttftCol": "TTFT (s)",
    "table.genCol": "生成速度 (tok/s)",

    "compare.bestNote": "比較表 (緑字が各指標の最良値)",
    "compare.charts": "比較グラフ",
    "compare.details": "詳細",
    "chart.gen": "生成速度 (median, tok/s)",
    "chart.ttft": "TTFT (median, s)",
    "chart.peak": "並列集約スループット (peak, tok/s)",

    "alert.missingTarget": "全ターゲットの Base URL と Model は必須です",
    "alert.startFailed": "開始できませんでした",
    "alert.connFailed": "サーバーに接続できません: {err}",
    "alert.noBaseUrl": "Base URL を入力してください",
    "alert.modelsFailed": "モデル一覧の取得に失敗しました",
    "alert.connError": "接続エラー: {err}",
    "alert.downloadFailed": "ダウンロードに失敗しました: {err}",
    "alert.reportFailed": "レポート取得に失敗しました",
  },
};

let currentLang = "ja";

function detectLang() {
  try {
    const saved = localStorage.getItem("llmservebench-lang");
    if (saved && I18N[saved]) return saved;
  } catch (e) {
    /* localStorage 無効環境では既定値を使う */
  }
  const nav = (navigator.language || "ja").toLowerCase();
  return nav.startsWith("ja") ? "ja" : "en";
}

function t(key, params) {
  const dict = I18N[currentLang] || I18N.en;
  let s = dict[key] ?? I18N.en[key] ?? key;
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      s = s.split("{" + k + "}").join(String(v));
    }
  }
  return s;
}

function applyI18n() {
  document.documentElement.lang = currentLang === "ja" ? "ja" : "en";
  document.title = t("doc.title");
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    el.textContent = t(el.getAttribute("data-i18n"));
  });
  document.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
    el.placeholder = t(el.getAttribute("data-i18n-placeholder"));
  });
  document.querySelectorAll(".lang-switch .tab-item").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.lang === currentLang);
  });
}

function setLang(lang) {
  if (!I18N[lang]) return;
  currentLang = lang;
  try {
    localStorage.setItem("llmservebench-lang", lang);
  } catch (e) {
    /* 保存できなくても切替は有効 */
  }
  applyI18n();
  if (typeof currentResult !== "undefined" && currentResult) {
    renderResult(currentResult);
  }
}

currentLang = detectLang();
applyI18n();
document.querySelectorAll(".lang-switch .tab-item").forEach((btn) => {
  btn.addEventListener("click", () => setLang(btn.dataset.lang));
});
