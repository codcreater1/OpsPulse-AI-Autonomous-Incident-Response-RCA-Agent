// OpsPulse review console. Plain DOM APIs only: every value from the API (which includes LLM output and
// untrusted log text) is rendered with textContent, never innerHTML.
"use strict";

const KEY_STORAGE = "opspulse.apiKey";
const STATUS_TONE = {
  awaiting_approval: "s-warn", needs_review: "s-warn", processing: "s-neutral", analysis_ready: "s-ok",
  pr_created: "s-ok", pr_skipped_duplicate: "s-ok", remediation_rejected: "s-neutral", pr_failed: "s-bad",
  failed: "s-bad", queued: "s-neutral",
};

const $ = (id) => document.getElementById(id);
const state = { cursor: null, current: null };

function apiKey() {
  try { return sessionStorage.getItem(KEY_STORAGE) || ""; } catch { return ""; }
}

function setKey(value) {
  try {
    if (value) sessionStorage.setItem(KEY_STORAGE, value); else sessionStorage.removeItem(KEY_STORAGE);
  } catch { /* storage unavailable: the key lives only in memory for this page */ }
  memoryKey = value;
  $("forget-key").hidden = !value;
}
let memoryKey = "";

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { "X-API-Key": apiKey() || memoryKey, "Content-Type": "application/json", ...(options.headers || {}) },
  });
  let body = null;
  try { body = await response.json(); } catch { body = null; }
  if (!response.ok) {
    const message = body && body.error ? body.error.message : `HTTP ${response.status}`;
    const error = new Error(message);
    error.status = response.status;
    throw error;
  }
  return body;
}

function el(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined && text !== null) node.textContent = String(text);
  if (className) node.className = className;
  return node;
}

function badge(status) {
  return el("span", (status || "").replaceAll("_", " "), `badge ${STATUS_TONE[status] || "s-neutral"}`);
}

function setMessage(id, text, isError = false) {
  const node = $(id);
  node.textContent = text || "";
  node.classList.toggle("error", isError);
}

function when(iso) {
  if (!iso) return "";
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleString();
}

// ------------------------------------------------------------------ list

async function loadList(append = false) {
  if (!append) state.cursor = null;
  const params = new URLSearchParams({ limit: "20" });
  const status = $("status-filter").value;
  if (status) params.set("status", status);
  if (append && state.cursor) params.set("cursor", state.cursor);
  setMessage("list-message", "Loading…");
  try {
    const page = await api(`/incidents?${params}`);
    renderRows(page.items, append);
    state.cursor = page.next_cursor;
    $("load-more").hidden = !page.next_cursor;
    const count = $("incident-table").querySelectorAll("tbody tr").length;
    setMessage("list-message", count ? "" : "No incidents match this filter.");
  } catch (error) {
    $("incident-table").hidden = true;
    setMessage("list-message", error.status === 401 ? "Enter a valid API key to continue." : error.message, true);
  }
}

function renderRows(items, append) {
  const body = $("incident-table").querySelector("tbody");
  if (!append) body.replaceChildren();
  for (const item of items) {
    const row = document.createElement("tr");
    row.tabIndex = 0;
    const statusCell = document.createElement("td");
    statusCell.append(badge(item.status));
    row.append(
      statusCell,
      el("td", item.repo_name),
      el("td", item.affected_file || "-", "mono"),
      el("td", Number(item.quality_score).toFixed(2)),
      el("td", item.iterations),
      el("td", `${when(item.created_at)}${item.submitted_by ? " · " + item.submitted_by : ""}`),
    );
    const open = () => showDetail(item.incident_id);
    row.addEventListener("click", open);
    row.addEventListener("keydown", (event) => { if (event.key === "Enter") open(); });
    body.append(row);
  }
  $("incident-table").hidden = body.children.length === 0;
}

// ------------------------------------------------------------------ detail

async function showDetail(incidentId) {
  try {
    const incident = await api(`/incidents/${encodeURIComponent(incidentId)}`);
    state.current = incident;
    setMessage("a-message", "");
    renderDetail(incident);
    $("list-view").hidden = true;
    $("detail-view").hidden = false;
    window.scrollTo(0, 0);
  } catch (error) {
    setMessage("list-message", error.message, true);
  }
}

function renderDetail(incident) {
  const analysis = incident.analysis || {};
  const summary = analysis.incident_summary || {};
  const root = ((analysis.diagnostic_chain || {}).primary_root_cause) || {};
  $("d-title").textContent = summary.title || incident.error_message.split("\n")[0];
  $("d-status").replaceWith(Object.assign(badge(incident.status), { id: "d-status" }));
  $("d-id").textContent = incident.incident_id;
  $("d-repo").textContent = incident.repo_name;
  $("d-file").textContent = incident.affected_file || "-";
  $("d-category").textContent = analysis.root_cause_category || "-";
  $("d-score").textContent = `${Number(incident.quality_score).toFixed(2)} after ${incident.iterations} attempt(s)`;
  $("d-submitter").textContent = incident.submitted_by || "-";
  $("d-usage").textContent = usageSummary(analysis.attempts || []);
  const reason = [incident.status_reason, incident.error_category && `(${incident.error_category})`].filter(Boolean);
  $("d-reason").textContent = reason.join(" ");
  $("d-root").textContent = root.technical_explanation || "No analysis available.";

  const evidence = $("d-evidence");
  evidence.replaceChildren();
  for (const item of analysis.evidence || []) {
    const li = el("li");
    li.append(el("span", item.kind, `kind kind-${item.kind}`), el("span", item.claim));
    if (item.quote) li.append(el("span", `${item.source}: ${item.quote}`, "quote"));
    evidence.append(li);
  }
  fillList("d-uncertainties", analysis.uncertainties);
  fillList("d-tests", analysis.tests_to_run);

  const checks = $("d-checks");
  checks.replaceChildren();
  const evaluation = analysis.evaluation || {};
  for (const [name, check] of Object.entries(evaluation.checks || {})) {
    const row = document.createElement("tr");
    const ok = check.score >= check.max - 1e-9;
    row.append(
      el("td", `${name}${check.blocking ? " *" : ""}`),
      el("td", `${Number(check.score).toFixed(2)} / ${Number(check.max).toFixed(2)}`, ok ? "s-ok" : "s-bad"),
      el("td", check.detail),
    );
    checks.append(row);
  }

  renderDiff(incident.suggested_patch);
  $("retry").hidden = incident.status !== "failed";
  const pending = incident.pending_approval;
  $("approval").hidden = !pending;
  if (pending) $("a-sha").textContent = pending.patch_sha256;
}

function usageSummary(attempts) {
  if (!attempts.length) return "-";
  const sum = (key) => attempts.reduce((total, a) => total + (Number(a[key]) || 0), 0);
  const tokens = sum("input_tokens") + sum("output_tokens");
  const seconds = sum("latency_ms") / 1000;
  return `${attempts.length} call(s), ${tokens.toLocaleString()} tokens, ${seconds.toFixed(1)} s`;
}

function fillList(id, values) {
  const list = $(id);
  list.replaceChildren();
  for (const value of values || []) list.append(el("li", value));
  if (!list.children.length) list.append(el("li", "none", "muted"));
}

function renderDiff(patch) {
  const pre = $("d-patch");
  pre.replaceChildren();
  if (!patch) { pre.append(el("span", "No patch proposed.")); return; }
  for (const line of patch.split("\n")) {
    let cls = "";
    if (line.startsWith("@@")) cls = "hunk";
    else if (line.startsWith("+") && !line.startsWith("+++")) cls = "add";
    else if (line.startsWith("-") && !line.startsWith("---")) cls = "del";
    pre.append(el("span", line || " ", cls));
  }
}

async function retry() {
  const incident = state.current;
  if (!incident) return;
  $("retry").disabled = true;
  try {
    const updated = await api(`/incidents/${encodeURIComponent(incident.incident_id)}/retry`, { method: "POST" });
    state.current = updated;
    renderDetail(updated);
    setMessage("a-message", "Re-queued: a worker will analyse it again.");
  } catch (error) {
    setMessage("a-message", error.message, true);
  } finally {
    $("retry").disabled = false;
  }
}

async function decide(decision) {
  const incident = state.current;
  const pending = incident && incident.pending_approval;
  if (!pending) return;
  if (decision === "approve" && !window.confirm("Open a draft pull request with this patch?")) return;
  for (const id of ["approve", "reject"]) $(id).disabled = true;
  setMessage("a-message", "Submitting…");
  try {
    const updated = await api(`/incidents/${encodeURIComponent(incident.incident_id)}/remediation/decision`, {
      method: "POST",
      body: JSON.stringify({
        approval_id: pending.approval_id,
        patch_sha256: pending.patch_sha256,
        decision,
        note: $("a-note").value || null,
      }),
    });
    state.current = updated;
    renderDetail(updated);
    setMessage("a-message", `Decision recorded: ${updated.status.replaceAll("_", " ")}`);
  } catch (error) {
    setMessage("a-message", error.message, true);
  } finally {
    for (const id of ["approve", "reject"]) $(id).disabled = false;
  }
}

// ------------------------------------------------------------------ wiring

document.addEventListener("DOMContentLoaded", () => {
  $("key-form").addEventListener("submit", (event) => {
    event.preventDefault();
    setKey($("api-key").value.trim());
    $("api-key").value = "";
    loadList();
  });
  $("forget-key").addEventListener("click", () => { setKey(""); loadList(); });
  $("status-filter").addEventListener("change", () => loadList());
  $("refresh").addEventListener("click", () => loadList());
  $("load-more").addEventListener("click", () => loadList(true));
  $("back").addEventListener("click", () => { $("detail-view").hidden = true; $("list-view").hidden = false; loadList(); });
  $("approve").addEventListener("click", () => decide("approve"));
  $("reject").addEventListener("click", () => decide("reject"));
  $("retry").addEventListener("click", retry);
  $("forget-key").hidden = !apiKey();
  loadList();
});
