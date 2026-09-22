"use strict";

const $ = (id) => document.getElementById(id);

let pollTimer = null;
let renderedEvents = 0;
let currentResult = null;

function fmtSec(v) {
  return typeof v === "number" ? v.toFixed(3) + "s" : "-";
}

function fmtRate(v) {
  return typeof v === "number" ? v.toFixed(1) + " tok/s" : "-";
}

function fmtNum(v, d) {
  return typeof v === "number" ? v.toFixed(d) : "-";
}

function esc(s) {
  return String(s)
    .replace(/&/g, "\x26amp;")
    .replace(/</g, "\x26lt;")
    .replace(/>/g, "\x26gt;")
    .replace(/"/g, "\x26quot;");
}

function setRunning(running) {
  $("run-single").disabled = running;
  $("run-compare").disabled = running;
  const badge = $("status-badge");
  if (badge) badge.classList.toggle("hidden", !running);
}

/* ---------- tabs ---------- */

function switchTab(name) {
  $("tab-single").classList.toggle("hidden", name !== "single");
  $("tab-compare").classList.toggle("hidden", name !== "compare");
  $("tab-btn-single").classList.toggle("active", name === "single");
  $("tab-btn-compare").classList.toggle("active", name === "compare");
}

/* ---------- compare target rows ---------- */

function addTargetRow(data) {
  const row = document.createElement("div");
  row.className = "compare-row";
  row.innerHTML = `
    <label>名前<input class="t-name" type="text" placeholder="llamacpp"></label>
    <label class="grow">Base URL<input class="t-url" type="text" placeholder="http://localhost:8080/v1"></label>
    <label class="grow">Model<input class="t-model" type="text" placeholder="モデルID"></label>
    <label>API Key<input class="t-key" type="password" placeholder="任意"></label>
    <button class="remove-target" type="button" title="削除">×</button>
  `;
  if (data) {
    row.querySelector(".t-name").value = data.name || "";
    row.querySelector(".t-url").value = data.url || "";
    row.querySelector(".t-model").value = data.model || "";
  }
  row.querySelector(".remove-target").addEventListener("click", () => row.remove());
  $("compare-rows").appendChild(row);
}

function collectTargets(mode) {
  if (mode === "single") {
    return [
      {
        name: "default",
        base_url: $("base-url").value.trim(),
        model: $("model").value.trim(),
        api_key: $("api-key").value,
      },
    ];
  }
  return Array.from(document.querySelectorAll("#compare-rows .compare-row")).map((row, i) => ({
    name: row.querySelector(".t-name").value.trim() || `target${i + 1}`,
    base_url: row.querySelector(".t-url").value.trim(),
    model: row.querySelector(".t-model").value.trim(),
    api_key: row.querySelector(".t-key").value,
  }));
}

function collectCommon() {
  const tempRaw = $("temperature").value.trim();
  const seedRaw = $("seed").value.trim();
  return {
    parallel_levels: $("parallel-levels").value
      .split(",")
      .map((s) => parseInt(s.trim(), 10))
      .filter((n) => Number.isFinite(n) && n > 0),
    max_tokens: parseInt($("max-tokens").value, 10) || 256,
    runs: parseInt($("runs").value, 10) || 5,
    parallel_runs: parseInt($("parallel-runs").value, 10) || 3,
    prefill_tokens: parseInt($("prefill-tokens").value, 10) || 2048,
    warmup: $("warmup").checked,
    randomize_prompts: $("randomize").checked,
    temperature: tempRaw === "" ? null : parseFloat(tempRaw),
    seed: seedRaw === "" ? null : parseInt(seedRaw, 10),
  };
}

/* ---------- run & poll ---------- */

async function startRun(mode) {
  const targets = collectTargets(mode);
  for (const t of targets) {
    if (!t.base_url || !t.model) {
      alert("全ターゲットの Base URL と Model は必須です");
      return;
    }
  }
  const payload = { targets, ...collectCommon() };

  renderedEvents = 0;
  $("log").textContent = "";
  $("result-card").classList.add("hidden");
  $("progress-card").classList.remove("hidden");
  currentResult = null;
  try {
    const resp = await fetch("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await resp.json();
    if (!resp.ok) {
      alert(data.error || "開始できませんでした");
      setRunning(false);
      return;
    }
    setRunning(true);
    startPolling();
  } catch (e) {
    alert("サーバーに接続できません: " + e);
    setRunning(false);
  }
}

function startPolling() {
  stopPolling();
  pollTimer = setInterval(pollStatus, 800);
  pollStatus();
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

async function pollStatus() {
  let data;
  try {
    const resp = await fetch("/api/status");
    data = await resp.json();
  } catch (e) {
    return;
  }
  renderEvents(data.events || []);
  if (data.result) {
    currentResult = data.result;
    renderResult(data.result);
    $("result-card").classList.remove("hidden");
  }
  if (!data.running) {
    setRunning(false);
    stopPolling();
    if (data.error) {
      appendLog("[ERROR] " + data.error);
    }
  }
}

/* ---------- event log ---------- */

function appendLog(line) {
  const log = $("log");
  log.textContent += line + "\n";
  log.scrollTop = log.scrollHeight;
}

function formatEvent(ev) {
  switch (ev.type) {
    case "info":
      return "[info] " + ev.message;
    case "warn":
      return "[warn] " + ev.message;
    case "target_start":
      return `##### target: ${ev.name} #####`;
    case "target_error":
      return `[error] target '${ev.name}': ${ev.message}`;
    case "phase_start": {
      const extra = ev.name === "parallel" ? ` (parallelism=${ev.parallelism})` : "";
      return `== ${ev.name}${extra} ==`;
    }
    case "phase_end":
      return `== ${ev.name} 完了 ==`;
    case "request_done":
      if (!ev.ok) return `  #${ev.index}: ERROR ${ev.error || ""}`;
      if (ev.phase === "prefill") {
        return `  #${ev.index}: ttft=${fmtSec(ev.ttft_s)} prompt=${fmtRate(ev.prompt_tok_per_s)}`;
      }
      return `  #${ev.index}: ttft=${fmtSec(ev.ttft_s)} gen=${fmtRate(ev.gen_tok_per_s)}`;
    case "run_done":
      return `  run ${ev.run}: aggregate=${fmtRate(ev.aggregate_tok_per_s)} wall=${fmtSec(ev.wall_time_s)}`;
    case "done":
      return "== all done ==";
    default:
      return JSON.stringify(ev);
  }
}

function renderEvents(events) {
  for (let i = renderedEvents; i < events.length; i++) {
    appendLog(formatEvent(events[i]));
  }
  renderedEvents = events.length;
}

/* ---------- charts ---------- */

function barChartSVG(entries, higherIsBetterNote) {
  if (!entries.length) return "";
  const w = 560;
  const h = 240;
  const padL = 64;
  const padB = 40;
  const padT = 16;
  const maxV = Math.max(...entries.map((e) => e.value || 0), 0.0001);
  const innerW = w - padL - 16;
  const innerH = h - padT - padB;
  const bw = innerW / entries.length;
  let bars = "";
  entries.forEach((e, i) => {
    const val = e.value || 0;
    const bh = (val / maxV) * innerH;
    const x = padL + i * bw + bw * 0.15;
    const y = padT + innerH - bh;
    const cls = higherIsBetterNote && e.isBest ? "bar best" : "bar";
    bars += `<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${(bw * 0.7).toFixed(1)}" height="${Math.max(bh, 1).toFixed(1)}" rx="3" class="${cls}"></rect>`;
    bars += `<text x="${(padL + i * bw + bw / 2).toFixed(1)}" y="${(h - padB + 18).toFixed(1)}" text-anchor="middle" class="axis-label">${esc(e.label)}</text>`;
    if (val) {
      bars += `<text x="${(padL + i * bw + bw / 2).toFixed(1)}" y="${(y - 6).toFixed(1)}" text-anchor="middle" class="value-label">${val.toFixed(1)}</text>`;
    }
  });
  let grid = "";
  for (let g = 0; g <= 4; g++) {
    const gy = padT + innerH - (innerH * g) / 4;
    grid += `<line x1="${padL}" y1="${gy.toFixed(1)}" x2="${w - 16}" y2="${gy.toFixed(1)}" class="gridline"></line>`;
    grid += `<text x="${padL - 8}" y="${(gy + 4).toFixed(1)}" text-anchor="end" class="axis-label">${((maxV * g) / 4).toFixed(0)}</text>`;
  }
  return `<svg viewBox="0 0 ${w} ${h}" class="chart">${grid}${bars}</svg>`;
}

/* ---------- tables ---------- */

const STAT_KEYS = ["mean", "median", "p95", "min", "max"];

function tableHTML(headers, rows) {
  return (
    `<table><thead><tr>${headers.map((h) => `<th>${h}</th>`).join("")}</tr></thead><tbody>` +
    rows
      .map((r) => `<tr>${r.map((c) => `<td>${c}</td>`).join("")}</tr>`)
      .join("") +
    "</tbody></table>"
  );
}

function statRow(label, obj, digits) {
  return [label, ...STAT_KEYS.map((k) => fmtNum((obj || {})[k], digits))];
}

function targetDetailHTML(target, open) {
  if (target.error) {
    return `<details${open ? " open" : ""}><summary>${esc(target.name)} (${esc(target.model || "")})</summary><p class="error-text">ERROR: ${esc(target.error)}</p></details>`;
  }
  const phases = target.phases || {};
  const parts = [];
  const single = phases.single;
  if (single) {
    parts.push("<h4>単一ストリーム</h4>");
    parts.push(
      tableHTML(
        ["指標", ...STAT_KEYS],
        [
          statRow("TTFT (s)", single.ttft, 3),
          statRow("生成速度 (tok/s)", single.gen_tok_per_s, 2),
          statRow("TPOT (s)", single.tpot, 3),
          statRow("ITL (s)", single.itl, 3),
          statRow("completion tokens", single.completion_tokens, 1),
        ]
      )
    );
  }
  const prefill = phases.prefill;
  if (prefill) {
    parts.push("<h4>prefill (長プロンプト)</h4>");
    parts.push(tableHTML(["指標", ...STAT_KEYS], [statRow("prompt tok/s", prefill.prompt_tok_per_s, 0)]));
  }
  const parallel = phases.parallel || {};
  const keys = Object.keys(parallel).sort((a, b) => parseInt(a, 10) - parseInt(b, 10));
  if (keys.length) {
    parts.push("<h4>並列スループット</h4>");
    parts.push(
      tableHTML(
        ["parallelism", "集約 tok/s (peak)", "TTFT median (s)", "per-req tok/s median", "ok/total"],
        keys.map((k) => {
          const p = parallel[k];
          return [
            k,
            fmtNum(p.aggregate_tok_per_s, 2),
            fmtNum((p.ttft || {}).median, 3),
            fmtNum((p.gen_tok_per_s || {}).median, 2),
            `${p.ok_requests ?? "-"}/${p.requests ?? "-"}`,
          ];
        })
      )
    );
  }
  return `<details${open ? " open" : ""}><summary>${esc(target.name)} (${esc(target.model || "")})</summary>${parts.join("")}</details>`;
}

/* ---------- result rendering ---------- */

function renderResult(result) {
  const targets = result.targets || {};
  const names = Object.keys(targets);
  if (result.mode === "compare" && result.comparison && names.length > 1) {
    renderCompare(result);
  } else if (names.length > 0) {
    renderSingle(targets[names[0]]);
  }
}

function renderSingle(target) {
  if (target.error) {
    $("result-body").innerHTML = `<p class="error-text">ERROR: ${esc(target.error)}</p>`;
    return;
  }
  const s = target.summary || {};
  const peak = s.parallel_aggregate_tok_per_s_peak;
  const peakLabel =
    fmtRate(peak) +
    (s.parallel_aggregate_tok_per_s_peak_level ? ` @ p=${s.parallel_aggregate_tok_per_s_peak_level}` : "");
  const cards = [
    ["TTFT (median)", fmtSec(s.ttft_s_median)],
    ["生成速度 (median)", fmtRate(s.gen_tok_per_s_median)],
    ["TPOT (median)", fmtSec(s.tpot_s_median)],
    [
      "prefill速度 (median)",
      typeof s.prefill_prompt_tok_per_s_median === "number"
        ? Math.round(s.prefill_prompt_tok_per_s_median) + " tok/s"
        : "-",
    ],
    ["並列集約スループット (peak)", peakLabel],
  ];
  $("result-body").innerHTML =
    `<div class="summary-grid">` +
    cards
      .map(
        ([label, value]) =>
          `<div class="stat"><div class="stat-label">${label}</div><div class="stat-value">${value}</div></div>`
      )
      .join("") +
    `</div>` +
    targetDetailHTML(target, true);
}

function renderCompare(result) {
  const comp = result.comparison;
  const rows = comp.rows || [];
  const best = comp.best || {};

  const comparisonTable = tableHTML(
    ["target", "model", "TTFT (s)", "生成速度 (tok/s)", "TPOT (s)", "prefill (tok/s)", "集約 tok/s (peak)"],
    rows.map((r) => {
      const cell = (v, metric, digits, suffix) => {
        let s = fmtNum(v, digits) + (suffix || "");
        if (typeof v === "number" && best[metric] === r.name) {
          s = `<span class="best-value">${s}</span>`;
        }
        return s;
      };
      return [
        esc(r.name),
        esc(r.model || "-"),
        cell(r.ttft_s_median, "ttft_s_median", 3, "s"),
        cell(r.gen_tok_per_s_median, "gen_tok_per_s_median", 2, ""),
        cell(r.tpot_s_median, "tpot_s_median", 3, "s"),
        cell(
          r.prefill_prompt_tok_per_s_median,
          "prefill_prompt_tok_per_s_median",
          0,
          typeof r.prefill_prompt_tok_per_s_median === "number" ? "" : ""
        ),
        cell(
          r.parallel_aggregate_tok_per_s_peak,
          "parallel_aggregate_tok_per_s_peak",
          2,
          r.parallel_aggregate_tok_per_s_peak_level ? ` @p=${r.parallel_aggregate_tok_per_s_peak_level}` : ""
        ),
      ];
    })
  );

  const charts =
    "<h3>比較グラフ</h3>" +
    "<h4>生成速度 (median, tok/s)</h4>" +
    barChartSVG(rows.map((r) => ({ label: r.name, value: r.gen_tok_per_s_median, isBest: best.gen_tok_per_s_median === r.name }))) +
    "<h4>TTFT (median, s)</h4>" +
    barChartSVG(rows.map((r) => ({ label: r.name, value: r.ttft_s_median, isBest: best.ttft_s_median === r.name }))) +
    "<h4>並列集約スループット (peak, tok/s)</h4>" +
    barChartSVG(rows.map((r) => ({ label: r.name, value: r.parallel_aggregate_tok_per_s_peak, isBest: best.parallel_aggregate_tok_per_s_peak === r.name })));

  const details = "<h3>詳細</h3>" + Object.values(result.targets)
    .map((t) => targetDetailHTML(t, false))
    .join("");

  $("result-body").innerHTML =
    "<h3>比較表 (緑字が各指標の最良値)</h3>" + comparisonTable + charts + details;
}

/* ---------- export ---------- */

async function downloadReport(format) {
  if (!currentResult) return;
  try {
    const resp = await fetch("/api/report?format=" + format);
    if (!resp.ok) {
      const data = await resp.json().catch(() => ({}));
      alert(data.error || "レポート取得に失敗しました");
      return;
    }
    const blob = await resp.blob();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    const stamp = new Date().toISOString().replace(/[:T]/g, "-").slice(0, 19);
    a.download = `llmservebench-${stamp}.${format === "markdown" ? "md" : "json"}`;
    a.click();
    URL.revokeObjectURL(a.href);
  } catch (e) {
    alert("ダウンロードに失敗しました: " + e);
  }
}

/* ---------- models ---------- */

async function fetchModels() {
  const base = $("base-url").value.trim();
  if (!base) {
    alert("Base URL を入力してください");
    return;
  }
  const btn = $("fetch-models");
  btn.disabled = true;
  try {
    const resp = await fetch("/api/models", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ base_url: base, api_key: $("api-key").value }),
    });
    const data = await resp.json();
    if (!resp.ok) {
      alert(data.error || "モデル一覧の取得に失敗しました");
      return;
    }
    const dl = $("model-list");
    dl.innerHTML = (data.models || []).map((m) => `<option value="${esc(m)}"></option>`).join("");
    if (data.models && data.models.length && !$("model").value) {
      $("model").value = data.models[0];
    }
  } catch (e) {
    alert("接続エラー: " + e);
  } finally {
    btn.disabled = false;
  }
}

/* ---------- init ---------- */

$("tab-btn-single").addEventListener("click", () => switchTab("single"));
$("tab-btn-compare").addEventListener("click", () => switchTab("compare"));
$("run-single").addEventListener("click", () => startRun("single"));
$("run-compare").addEventListener("click", () => startRun("compare"));
$("add-target").addEventListener("click", () => addTargetRow());
$("export-json").addEventListener("click", () => downloadReport("json"));
$("export-md").addEventListener("click", () => downloadReport("markdown"));
$("fetch-models").addEventListener("click", fetchModels);

addTargetRow({ name: "llamacpp", url: "http://localhost:8080/v1", model: "" });
addTargetRow({ name: "ollama", url: "http://localhost:11434/v1", model: "" });
