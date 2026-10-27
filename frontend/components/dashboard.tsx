"use client";

import { FormEvent, ReactNode, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  Activity, ArrowDownToLine, ArrowRight, Bot, ChevronRight, CircleHelp, Clock3,
  Command, Fingerprint, Globe2, Layers3, LayoutDashboard, LoaderCircle, Network,
  Radio, Search, ShieldCheck, TerminalSquare, TriangleAlert, Waypoints, X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { InfrastructureGraph } from "@/components/infrastructure-graph";
import { WorldMap } from "@/components/world-map";
import { api, download, type GetToken } from "@/lib/api";
import type { AnalystAnswer, ScanJob, Simulation, Workspace } from "@/lib/types";

type View = "overview" | "graph" | "map" | "history" | "leaderboard" | "analyst";
const navigation: { id: View; label: string; icon: typeof Activity }[] = [
  { id: "overview", label: "Intelligence overview", icon: LayoutDashboard },
  { id: "graph", label: "Dependency graph", icon: Waypoints },
  { id: "map", label: "Internet atlas", icon: Globe2 },
  { id: "history", label: "Change timeline", icon: Clock3 },
  { id: "leaderboard", label: "Exposure rankings", icon: Layers3 },
  { id: "analyst", label: "Infrastructure analyst", icon: Bot },
];

export function Dashboard({ getToken, signedIn, account }: { getToken: GetToken; signedIn: boolean; account: ReactNode }) {
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [view, setView] = useState<View>("overview");
  const [selectedId, setSelectedId] = useState("");
  const [domain, setDomain] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(true);
  const [job, setJob] = useState<ScanJob | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [simulation, setSimulation] = useState<Simulation | null>(null);
  const [providerId, setProviderId] = useState("");
  const [simulationBusy, setSimulationBusy] = useState(false);
  const [question, setQuestion] = useState("Which observed dependency has the highest concentration risk?");
  const [answer, setAnswer] = useState<AnalystAnswer | null>(null);
  const [analystBusy, setAnalystBusy] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [monitorBusy, setMonitorBusy] = useState(false);
  const mounted = useRef(true);
  const development = process.env.NEXT_PUBLIC_DEVELOPMENT_AUTH === "true";
  const scanBusy = submitting || job?.status === "queued" || job?.status === "running";

  const loadWorkspace = useCallback(async (mode: "demo" | "live") => {
    setLoading(true);
    setError("");
    try {
      const data = await api<Workspace>(mode === "demo" ? "/api/demo" : "/api/workspace", getToken);
      setWorkspace(data);
      setSelectedId(data.snapshots[0]?.id ?? "");
      setSimulation(null);
      setAnswer(null);
      setProviderId(data.portfolio.providers[0]?.id ?? "");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Workspace could not load.");
    } finally { setLoading(false); }
  }, [getToken]);

  useEffect(() => { void loadWorkspace("demo"); }, [loadWorkspace]);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => {
    if (!job || !["queued", "running"].includes(job.status)) return;
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    let attempts = 0;
    async function poll() {
      if (!job) return;
      try {
        const status = await api<ScanJob>(`/api/scans/${job.id}`, getToken);
        if (!active) return;
        if (status.status === "completed") {
          setJob(status);
          await loadWorkspace("live");
          setNotice(`Evidence collected for ${status.domain}. Inspect the coverage and limitations before drawing conclusions.`);
        } else if (status.status === "failed") {
          setJob(status);
          setError(status.error ?? "Collection failed. No successful snapshot was recorded.");
        } else if (++attempts >= 150) {
          setJob({ ...status, status: "failed" });
          setError("The scan is taking longer than five minutes. Check the workspace later or retry.");
        } else {
          timer = setTimeout(poll, 2000);
        }
      } catch (reason) {
        if (active) {
          setJob((current) => current ? { ...current, status: "failed" } : null);
          setError(reason instanceof Error ? reason.message : "Scan status unavailable.");
        }
      }
    }
    timer = setTimeout(poll, 1500);
    return () => { active = false; clearTimeout(timer); };
  }, [job, getToken, loadWorkspace]);

  const selected = workspace?.snapshots.find((s) => s.id === selectedId) ?? workspace?.snapshots[0];
  const intel = selected?.intelligence;
  const currentAssets = useMemo(() => {
    const seen = new Set<string>();
    return workspace?.snapshots.filter((s) => !seen.has(s.domain) && Boolean(seen.add(s.domain))) ?? [];
  }, [workspace]);
  const locations = useMemo(() => currentAssets.flatMap((s) => s.intelligence.locations), [currentAssets]);
  const history = workspace?.snapshots.filter((s) => s.domain === selected?.domain) ?? [];
  const topProvider = workspace?.portfolio.providers[0];
  const avgScore = useMemo(() => {
    const known = currentAssets.map((s) => s.intelligence.overall_score).filter((s): s is number => s !== null);
    return known.length ? Math.round(known.reduce((sum, score) => sum + score, 0) / known.length) : null;
  }, [currentAssets]);

  async function submitScan(event: FormEvent) {
    event.preventDefault();
    setError(""); setNotice("");
    if (!signedIn && !development) {
      setError("Sign in with Clerk to run a live scan. The public demo uses synthetic domains and makes no live-company claims.");
      return;
    }
    setSubmitting(true);
    try {
      const result = await api<ScanJob>("/api/scans", getToken, {
        method: "POST", headers: { "Idempotency-Key": crypto.randomUUID() },
        body: JSON.stringify({ domain }),
      });
      if (mounted.current) setJob(result);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Scan could not be submitted.");
    } finally { if (mounted.current) setSubmitting(false); }
  }

  async function runSimulation(id: string) {
    if (!workspace) return;
    setProviderId(id); setSimulationBusy(true); setError("");
    try {
      const result = await api<Simulation>(workspace.mode === "demo" ? "/api/demo/simulate" : "/api/simulate", getToken, {
        method: "POST", body: JSON.stringify({ provider_id: id }),
      });
      setSimulation(result);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Simulation unavailable."); }
    finally { setSimulationBusy(false); }
  }

  async function askAnalyst(event: FormEvent) {
    event.preventDefault();
    if (!workspace || !selected) return;
    setAnalystBusy(true); setError("");
    try {
      setAnswer(await api<AnalystAnswer>(workspace.mode === "demo" ? "/api/demo/analyst" : "/api/analyst", getToken, {
        method: "POST", body: JSON.stringify({ snapshot_id: selected.id, question }),
      }));
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Analyst unavailable."); }
    finally { setAnalystBusy(false); }
  }

  async function exportReport(format: string) {
    if (!selected || !workspace) return;
    setExporting(true); setError("");
    try {
      await download(`${workspace.mode === "demo" ? "/api/demo" : "/api"}/reports/${selected.id}/${format}`, getToken, `shadow-${selected.domain}.${format}`);
      setNotice(`${format.toUpperCase()} evidence report exported.`);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Report export failed."); }
    finally { setExporting(false); }
  }

  async function monitorDomain(enabled: boolean) {
    if (!selected || workspace?.mode !== "live") {
      setError("Scheduled monitoring is available for live domains in your authenticated workspace.");
      return;
    }
    setMonitorBusy(true); setError("");
    try {
      await api("/api/monitors", getToken, { method: "POST", body: JSON.stringify({
        domain: selected.domain, interval_hours: 24, enabled,
      }) });
      setNotice(enabled ? `Daily monitoring enabled for ${selected.domain}. The worker and beat scheduler must remain running.` : `Monitoring paused for ${selected.domain}.`);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Monitoring configuration failed."); }
    finally { setMonitorBusy(false); }
  }

  return <div className="app-shell">
    <aside className="sidebar">
      <a href="/" className="brand"><div className="brand-icon"><Network size={24} /></div><div>SHADOW<span>INTERNET</span></div></a>
      <div className="workspace-label"><span className="workspace-avatar">SI</span><div>Research workspace<small>{workspace?.mode === "live" ? "PRIVATE / LIVE EVIDENCE" : "SYNTHETIC DEMO / READ ONLY"}</small></div></div>
      <span className="nav-caption">OBSERVABILITY</span>
      <nav aria-label="Main navigation">{navigation.map(({ id, label, icon: Icon }) =>
        <button key={id} onClick={() => setView(id)} className={`nav-item ${view === id ? "active" : ""}`}><Icon size={17} />{label}{id === "analyst" && <span className="new-tag">RAG</span>}</button>)}</nav>
      <div className="sidebar-divider" />
      <span className="nav-caption">WORKSPACE ASSETS <b>{currentAssets.length.toString().padStart(2, "0")}</b></span>
      <div className="asset-list">{currentAssets.map((s) => <button key={s.id} className={selected?.domain === s.domain ? "selected" : ""} onClick={() => { setSelectedId(s.id); setAnswer(null); }}>
        <span className="asset-dot" />{s.domain}<span>{s.intelligence.overall_score ?? "--"}</span>
      </button>)}</div>
      <div className="sidebar-bottom"><div><ShieldCheck size={16} /><span>Evidence, not assumptions</span></div><p>Passive public signals. No port scans, exploitation, or private network access.</p><a href="https://github.com/UdhaviVerma/shadow-internet" target="_blank" rel="noreferrer">Source & methodology <ArrowRight size={13} /></a></div>
    </aside>
    <main className="main">
      <header className="topbar"><div className="breadcrumb">Workspace <ChevronRight size={13} /><span>{navigation.find((n) => n.id === view)?.label}</span></div><div className="topbar-actions"><span className="version">v0.1.0</span>{account}</div></header>
      <div className="content">
        <div className="heading-row"><div><div className="eyebrow"><span className="live-dot" /> INFRASTRUCTURE INTELLIGENCE PLATFORM</div><h1>{view === "overview" ? "The internet beneath the surface." : navigation.find((n) => n.id === view)?.label}</h1><p className="subtitle">Reveal the hidden infrastructure powering the internet.</p></div><div className="mode-toggle" aria-label="Workspace mode"><button disabled={Boolean(scanBusy)} className={workspace?.mode === "demo" ? "active" : ""} onClick={() => loadWorkspace("demo")}>Demo</button><button disabled={Boolean(scanBusy)} className={workspace?.mode === "live" ? "active" : ""} onClick={() => loadWorkspace("live")}>My workspace</button></div></div>
        <form className="scan-bar" onSubmit={submitScan}><Search size={19} /><input aria-label="Domain to analyze" value={domain} onChange={(e) => setDomain(e.target.value)} placeholder="Enter a domain to reveal its infrastructure..." required maxLength={253} /><kbd><Command size={11} /> PUBLIC SIGNALS</kbd><Button disabled={Boolean(scanBusy)} type="submit">{scanBusy ? <LoaderCircle size={15} className="spin" /> : <Radio size={15} />}{scanBusy ? "Collecting evidence" : "Analyze domain"}<ArrowRight size={15} /></Button></form>
        <div className="scan-help"><span>DNS + TLS + ASN + EDGE PROVIDERS</span><span>No credentials sent to target websites. Live scans require a private workspace.</span></div>
        {error && <div className="feedback error" role="alert"><TriangleAlert size={17} /><span>{error}</span><button aria-label="Dismiss error" onClick={() => setError("")}><X size={15} /></button></div>}
        {notice && <div className="feedback success" role="status"><ShieldCheck size={17} />{notice}<button aria-label="Dismiss notification" onClick={() => setNotice("")}><X size={15} /></button></div>}
        {workspace?.mode === "demo" && <div className="demo-banner"><Fingerprint size={16} /><strong>EXPLORER DEMO</strong><span>All .example assets, dependencies, scores and locations below are synthetic. Real company architecture is not being asserted.</span></div>}
        {loading ? <div className="loading-panel"><LoaderCircle className="spin" size={25} /><span>Loading evidence workspace...</span></div> : workspace && <>
          <div className="stats-grid">
            <Stat title="OBSERVED ASSETS" value={workspace.portfolio.asset_count.toString().padStart(2, "0")} icon={<Globe2 size={18} />} foot={`${workspace.snapshots.length} historical snapshots`} />
            <Stat title="PROVIDER IDENTITIES" value={workspace.portfolio.providers.length.toString().padStart(2, "0")} icon={<Layers3 size={18} />} foot="Inferred from public signals" />
            <Stat title="OBSERVATION INDEX" value={avgScore === null ? "--" : `${avgScore}`} suffix="/100" icon={<ShieldCheck size={18} />} foot="Measured categories only; not a safety rating" />
            <Stat title="TOP CONCENTRATION" value={`${topProvider?.concentration ?? 0}%`} icon={<Activity size={18} />} foot={topProvider ? `${topProvider.name} / workspace exposure` : "No dependency evidence yet"} warning />
          </div>
          <AnimatePresence mode="wait"><motion.div key={view} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.18 }}>
            {(view === "overview" || view === "graph") && <div className={`analysis-grid ${view === "graph" ? "expanded" : ""}`}>
              <section className="panel graph-panel"><PanelHeading icon={<Waypoints size={17} />} title="Infrastructure dependency graph" meta={`${workspace.graph.nodes.length} NODES / ${workspace.graph.edges.length} EDGES`} /><InfrastructureGraph graph={workspace.graph} affectedIds={simulation?.affected_node_ids ?? []} onProvider={runSimulation} onInspect={(id) => { if (id.startsWith("domain:")) { const asset = currentAssets.find((s) => s.domain === id.slice(7)); if (asset) setSelectedId(asset.id); } }} /><div className="graph-legend"><span><i className="legend-dot green" />Domain</span><span><i className="legend-dot blue" />Provider</span><span><i className="legend-dot violet" />Network / IP</span><span>Click a provider to simulate exposure <ArrowRight size={12} /></span></div></section>
              <section className="panel simulation-panel"><PanelHeading icon={<TriangleAlert size={17} />} title="Blast radius simulator" /><div className="panel-body"><span className="field-caption">HYPOTHETICAL PROVIDER OUTAGE</span><label className="sr-only" htmlFor="provider-select">Provider to simulate</label><select id="provider-select" value={providerId} onChange={(e) => setProviderId(e.target.value)}>{workspace.portfolio.providers.map((p) => <option value={p.id} key={p.id}>{p.name}</option>)}</select><Button className="w-full mt-3" variant="secondary" disabled={!providerId || simulationBusy} onClick={() => runSimulation(providerId)}>{simulationBusy ? <LoaderCircle className="spin" size={15} /> : <Activity size={15} />}Simulate outage exposure</Button>
                {simulation ? <div className="simulation-result"><div className="exposure-number">{simulation.affected_assets.length}<span>potentially exposed assets</span></div><div className="risk-strip"><span>Observed concentration</span><b>{simulation.concentration}%</b></div><div className="meter danger"><i style={{ width: `${simulation.concentration}%` }} /></div><ul className="impact-tree"><li><TriangleAlert size={14} />{simulation.provider}</li>{simulation.affected_assets.map((asset) => <li key={asset}><span />{asset}</li>)}</ul><p className="disclaimer">{simulation.interpretation}</p><button className="text-button mt-3" onClick={() => setSimulation(null)}>Clear simulation <X size={12} /></button></div> : <div className="simulation-empty"><div className="radar-rings"><Activity size={22} /></div><h3>One provider. Many dependencies.</h3><p>Trace which assets share a provider. The result is exposure, not a prediction of downtime.</p></div>}
              </div></section>
            </div>}
            {(view === "overview" || view === "map") && <div className="details-grid">
              <section className="panel"><PanelHeading icon={<Globe2 size={17} />} title="Infrastructure footprint" meta="APPROXIMATE IP LOCATIONS" /><WorldMap locations={locations} /></section>
              <section className="panel"><PanelHeading icon={<ShieldCheck size={17} />} title="Security observation index" meta={selected?.domain ?? "NO ASSET"} /><div className="panel-body">{intel ? <><div className="score-head"><div className="score-ring" style={{ background: `conic-gradient(#42e3c2 ${(intel.overall_score ?? 0) * 3.6}deg, #1a2833 0deg)` }}><div>{intel.overall_score ?? "--"}<small>/ 100</small></div></div><div><h3>{intel.coverage}% category coverage</h3><p className="muted text-xs">Explainable signals, not a compliance verdict.</p></div></div>{intel.scores.map((score) => <div className="score-row" key={score.name} title={score.explanation}><div><span>{score.name}</span><b>{score.score ?? "Unknown"}</b></div><div className="meter"><i style={{ width: `${score.score ?? 0}%` }} /></div><small>{score.explanation}</small></div>)}</> : <EmptyState text="Analyze a domain to measure observable categories." />}</div></section>
            </div>}
            {(view === "overview" || view === "history") && <section className="panel mt-5"><PanelHeading icon={<Clock3 size={17} />} title="Infrastructure change timeline" meta={selected?.domain ?? "NO ASSET"} /><div className="evidence-topline"><span className="muted">Snapshots persist across rescans. Scheduled checks require the worker + beat services.</span><div className="export-actions"><button disabled={monitorBusy} onClick={() => monitorDomain(true)}>ENABLE DAILY</button><button disabled={monitorBusy} onClick={() => monitorDomain(false)}>PAUSE</button></div></div><div className="timeline">{history.length ? history.map((s, index) => <button className={`timeline-item ${selected?.id === s.id ? "selected" : ""}`} key={s.id} onClick={() => { setSelectedId(s.id); setAnswer(null); }}><div className="timeline-track"><i /><span /></div><div><small>{new Date(s.created_at).toLocaleString("en-GB", { timeZone: "UTC", dateStyle: "medium", timeStyle: "short" })} UTC</small><h3>{s.changes[0]}</h3><p>{s.changes.slice(1).join(" / ") || s.domain}</p></div><span className="timeline-tag">{index === 0 ? "LATEST" : "SNAPSHOT"}</span></button>) : <EmptyState text="Your first completed scan creates a persistent baseline. Rescans compare observed changes." />}</div></section>}
            {view === "leaderboard" && <section className="panel"><PanelHeading icon={<Layers3 size={17} />} title="Workspace exposure rankings" meta="LATEST SNAPSHOT PER DOMAIN" /><div className="panel-body"><p className="disclaimer mb-5">{workspace.portfolio.scope}. Higher scores describe stronger measured signals, not the safest sites on the internet.</p><div className="table-scroll"><table><thead><tr><th>ASSET</th><th>INDEX</th><th>COVERAGE</th><th>PROVIDER COMPLEXITY</th><th>DATA MODE</th></tr></thead><tbody>{workspace.portfolio.leaderboard.map((row) => <tr key={row.domain}><td>{row.domain}</td><td className="accent">{row.score ?? "Unknown"}</td><td>{row.coverage}%</td><td>{row.providers} identities</td><td><span className="pill">{row.mode}</span></td></tr>)}</tbody></table></div><h3 className="mt-7 mb-3">Shared provider exposure</h3>{workspace.portfolio.providers.map((p) => <button className="provider-row" key={p.id} onClick={() => { setView("graph"); void runSimulation(p.id); }}><span>{p.name}<small>{p.roles.join(" / ")}</small></span><b>{p.assets.length} assets</b><span className="accent">{p.concentration}%</span><ArrowRight size={14} /></button>)}</div></section>}
            {view === "analyst" && <section className="panel"><PanelHeading icon={<Bot size={17} />} title="Evidence-grounded infrastructure analyst" meta={selected?.domain ?? "NO ASSET"} /><div className="panel-body analyst-panel"><div className="analyst-intro"><div className="analyst-icon"><Bot size={26} /></div><h2>Ask the evidence. Not the hype.</h2><p>Retrieval searches the selected snapshot. An optional authenticated AI provider can synthesize cited evidence; without one, responses are explicitly labeled retrieval-only.</p></div><form onSubmit={askAnalyst}><label className="field-caption" htmlFor="analyst-question">YOUR QUESTION</label><textarea id="analyst-question" minLength={5} maxLength={1200} required value={question} onChange={(e) => setQuestion(e.target.value)} /><Button disabled={!selected || analystBusy}>{analystBusy ? <LoaderCircle size={15} className="spin" /> : <Bot size={15} />}Analyze evidence<ArrowRight size={15} /></Button></form>{answer && <div className="analyst-answer"><span className="pill">{answer.mode === "llm-rag" ? "LLM + RETRIEVAL" : "EVIDENCE RETRIEVAL / NO LLM"}</span><div className="answer-text">{answer.answer}</div><h3>Retrieved citations</h3>{answer.citations.map((citation) => <div className="citation" key={citation.id}><span>[{citation.id}]</span><strong>{citation.source}</strong><p>{citation.value}</p></div>)}</div>}</div></section>}
            {intel && <section className="panel mt-5"><PanelHeading icon={<TerminalSquare size={17} />} title="Evidence register" meta={`${intel.evidence.length} OBSERVATIONS / ${intel.mode.toUpperCase()}`} /><div className="evidence-topline"><span>{selected?.domain} <span className="muted">/ recorded {new Date(intel.collected_at).toISOString().slice(0, 16).replace("T", " ")} UTC</span></span><div className="export-actions"><ArrowDownToLine size={14} />{["json", "csv", "pdf"].map((format) => <button disabled={exporting} onClick={() => exportReport(format)} key={format}>{format.toUpperCase()}</button>)}</div></div><div className="table-scroll evidence-table"><table><thead><tr><th>SIGNAL</th><th>OBSERVATION</th><th>PROVENANCE</th><th>CONFIDENCE</th></tr></thead><tbody>{intel.evidence.map((evidence) => <tr key={evidence.id}><td><span className="evidence-id">{evidence.id}</span></td><td>{evidence.value}</td><td>{evidence.source}</td><td><span className="confidence-dot" />{evidence.confidence}</td></tr>)}</tbody></table></div><details className="scope-details"><summary><CircleHelp size={14} /> Methodology, WAF status and observation limits</summary><ul>{intel.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul></details></section>}
          </motion.div></AnimatePresence>
          {!workspace.snapshots.length && <EmptyState text="Your workspace is empty. Submit a public domain above to create your first evidence snapshot." />}
        </>}
        {!workspace && !loading && <div className="loading-panel"><TriangleAlert size={24} /><span>The API is unavailable. Check your backend URL and health endpoint.</span><Button variant="secondary" onClick={() => loadWorkspace("demo")}>Retry connection</Button></div>}
        <footer><span><Network size={13} /> SHADOW INTERNET</span><span>Public signals. Explicit uncertainty. Reproducible evidence.</span><span>Built for the curious.</span></footer>
      </div>
    </main>
  </div>;
}

function Stat({ title, value, suffix, icon, foot, warning }: { title: string; value: string; suffix?: string; icon: ReactNode; foot: string; warning?: boolean }) {
  return <div className={`stat-card ${warning ? "warning" : ""}`}><div className="stat-label">{title}{icon}</div><div className="stat-value">{value}<small>{suffix}</small></div><div className="stat-foot"><span className="tiny-dot" />{foot}</div></div>;
}
function PanelHeading({ icon, title, meta }: { icon: ReactNode; title: string; meta?: string }) {
  return <div className="panel-heading"><h2>{icon}{title}</h2>{meta && <span>{meta}</span>}</div>;
}
function EmptyState({ text }: { text: string }) {
  return <div className="empty-state"><Network size={24} /><p>{text}</p></div>;
}
