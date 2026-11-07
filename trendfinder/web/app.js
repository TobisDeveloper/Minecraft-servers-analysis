"use strict";
const $ = id => document.getElementById(id);
let token = "", current = null, selected = "", running = false, latest = "", polling = false;
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const urlSafe = s => { try { const u = new URL(s); return ["https:","http:"].includes(u.protocol) ? u.href : ""; } catch { return ""; } };

async function api(path, options) {
  const response = await fetch(path, options);
  if (!response.ok) { const data = await response.json(); throw new Error(data.error || "Request failed"); }
  return response.json();
}
async function scan(mode) {
  if (running) return;
  $("scan").disabled = $("demo").disabled = true;
  try {
    await api("/api/scan", {method:"POST",headers:{"Content-Type":"application/json","X-Radar-Token":token},body:JSON.stringify({mode})});
    running = true; await poll();
  } catch (e) { $("status").textContent = e.message; $("scan").disabled = $("demo").disabled = false; }
}
async function refreshRuns(preferred) {
  const rows = await api("/api/runs");
  $("runs").innerHTML = rows.map(r => `<option value="${esc(r.id)}">${r.mode.toUpperCase()} · ${esc(new Date(r.created_at).toLocaleString())}</option>`).join("");
  if (!rows.length) return;
  const rid = preferred && rows.some(r => r.id === preferred) ? preferred : rows[0].id;
  $("runs").value = rid;
  await loadReport(rid);
}
async function loadReport(rid) {
  current = await api("/api/report/" + encodeURIComponent(rid));
  selected = current.rankings[0]?.candidate.id || "";
  $("empty").hidden = true; $("results").hidden = false;
  $("demo-banner").hidden = current.mode !== "demo";
  $("metric-items").textContent = current.observations.length;
  const attempted = current.sources.filter(s => s.state !== "skipped");
  $("metric-health").textContent = `${attempted.filter(s => ["ok","demo"].includes(s.state)).length}/${attempted.length}`;
  $("metric-pilots").textContent = current.rankings.filter(r => r.stage === "PILOT CANDIDATE").length;
  for (const [id,file] of [["pdf-link","report.pdf"],["json-link","report.json"],["csv-link","observations.csv"]]) $(id).href = `/artifacts/${current.id}/${file}`;
  $("source-list").innerHTML = current.sources.map(s => `<article class="source"><div class="source-title">${esc(s.source.replaceAll("_"," "))}<span class="source-state ${s.state === "ok" ? "ok" : ""}">${esc(s.state)} / ${s.observations}</span></div><p>${esc(s.message || "Collected successfully. Results reflect the sampled data only.")}</p></article>`).join("");
  const sources = [...new Set(current.observations.map(o => o.source))];
  $("source-filter").innerHTML = '<option value="all">All sources</option>' + sources.map(s => `<option value="${esc(s)}">${esc(s)}</option>`).join("");
  renderRanking(); renderDetail(); renderEvidence();
}
function renderRanking() {
  $("rankings").innerHTML = current.rankings.map((r,i) => `<button class="rank-row ${r.candidate.id === selected ? "selected" : ""}" data-id="${esc(r.candidate.id)}" aria-pressed="${r.candidate.id === selected}"><span class="rank-index">${String(i+1).padStart(2,"0")}</span><span class="rank-title">${esc(r.candidate.name)}<span class="rank-stage">${esc(r.stage)}</span></span><span class="rank-score">${r.score.toFixed(0)}</span></button>`).join("");
  $("rankings").querySelectorAll("button").forEach(b => b.addEventListener("click", () => { selected=b.dataset.id;renderRanking();renderDetail();renderEvidence(); }));
}
function renderDetail() {
  const r = current.rankings.find(r => r.candidate.id === selected); if (!r) return;
  const bars = Object.entries(r.signals).map(([name,value]) => `<div class="signal"><span>${esc(name.toUpperCase())}</span><div class="signal-track" aria-label="${esc(name)} ${value} out of 100">${Array.from({length:20},(_,i)=>`<i class="signal-cell ${i < Math.round(value/5) ? "on" : ""}"></i>`).join("")}</div><span>${value.toFixed(0)}</span></div>`).join("");
  $("detail").innerHTML = `<div class="detail-inner"><span class="badge">${esc(r.stage)}</span><h3>${esc(r.candidate.name)}</h3><div class="detail-meta">${r.confidence}% COVERAGE · ${r.local_evidence} LOCAL ITEMS · ${r.evidence_ids.length} ANCHORS</div>${bars}<h4>WHAT THE EVIDENCE SAYS</h4>${r.reasons.length ? `<ul>${r.reasons.slice(0,4).map(t=>`<li>${esc(t)}</li>`).join("")}</ul>` : '<p>No usable evidence yet. Collect sources before treating this as an opportunity.</p>'}<h4>HOSTING STARTING POINT</h4><p>${esc(r.candidate.stack)}<br>${r.candidate.ram_gb} GB RAM budget hypothesis — benchmark before selling.</p><p class="caveat">${esc(r.caveats.slice(0,2).join(" "))}<br>Scores are research heuristics. Full caveats, costs and implementation steps are in the PDF.</p></div>`;
}
function renderEvidence() {
  const source = $("source-filter").value;
  const rows = current.observations.filter(o => o.candidate === selected && (source === "all" || o.source === source)).slice(0,40);
  $("evidence").innerHTML = rows.length ? rows.map(o => `<article class="evidence-row"><span>${esc(o.source)}<small>${esc(o.market)}</small></span><div>${urlSafe(o.url) ? `<a href="${esc(urlSafe(o.url))}" target="_blank" rel="noopener noreferrer">${esc(o.title)}</a>` : esc(o.title)}<small>[${esc(o.id)}] · ${esc(o.metric)}: ${Number(o.value).toLocaleString()} · Published ${esc(o.published_at ? o.published_at.slice(0,10) : "unknown")}</small></div><span>${esc(o.family)}</span></article>`).join("") : '<div class="evidence-empty">No matching evidence in this scan. Missing data does not mean no demand. Check source health or add authorized feeds.</div>';
}
async function poll() {
  if (polling) return; polling = true;
  try {
    const state = await api("/api/status");token=state.token;
    const completed = running && !state.running;
    running=state.running;$("status").textContent=state.message;
    $("status-dot").className="status-dot"+(running?" busy":"")+(state.error?" error":"");
    $("scan").disabled=$("demo").disabled=running;
    $("ai-state").textContent=state.ai_enabled?"LOCAL AI / ENABLED":"LOCAL AI / OPTIONAL";
    if (completed || (state.latest && state.latest !== latest)) {latest=state.latest;await refreshRuns(state.latest);}
  } catch { $("status").textContent="Scanner disconnected. Restart Start-Windows.cmd or the local server."; }
  finally {polling=false;}
}
$("scan").addEventListener("click",()=>scan("live"));$("demo").addEventListener("click",()=>scan("demo"));
$("runs").addEventListener("change",()=>loadReport($("runs").value).catch(e=>$("status").textContent=e.message));
$("source-filter").addEventListener("change",renderEvidence);
$("clock").textContent=new Intl.DateTimeFormat("en-GB",{timeZone:"Europe/Bratislava",day:"2-digit",month:"short",year:"numeric"}).format(new Date()).toUpperCase()+" / LOCAL STATION";
(async()=>{await poll();await refreshRuns();setInterval(poll,2000);})().catch(e=>$("status").textContent=e.message);
