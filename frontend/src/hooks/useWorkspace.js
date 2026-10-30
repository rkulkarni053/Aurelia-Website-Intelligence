import { useEffect, useMemo, useRef, useState } from "react";
import { STORAGE_KEYS, api, formatDate, normalizeWebsiteUrl } from "../api";
import { isActiveCrawl } from "../lib/crawl";

const HISTORY_LIMIT = 10;
const POLL_MS = 2000;
const EMPTY_COMPARISON = {
  new: "—",
  resolved: "—",
  unchanged: "—",
  newItems: [],
  resolvedItems: [],
};
const EMPTY_META = { pages: "—", started: "—", completed: "—", pagesCrawled: "—" };
const EMPTY_CHAT = { messages: [], design_brief: null };
const EMPTY_SOCIAL_CHAT = { messages: [], social_content: null };
const same = (a, b) => String(a ?? "") === String(b ?? "");
const json = (body, method = "POST") => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

function readStored() {
  return {
    companyId: localStorage.getItem(STORAGE_KEYS.companyId) || "",
    projectId: localStorage.getItem(STORAGE_KEYS.projectId) || "",
    websiteId: localStorage.getItem(STORAGE_KEYS.websiteId) || "",
    crawlId: localStorage.getItem(STORAGE_KEYS.crawlId) || "",
  };
}

function brainMetaFrom(recs) {
  if (!recs) return "Local Ollama";
  return (
    [recs.source, recs.model, recs.scores?.overall != null ? `score ${recs.scores.overall}/10` : null]
      .filter(Boolean)
      .join(" · ") || "Local Ollama"
  );
}

/**
 * Picks a consistent company → project → website chain. A preferred website
 * wins over everything else so bookmarked links land on the right client.
 */
function resolveSelection(data, preferred) {
  const website = data.websites.find((w) => same(w.id, preferred.websiteId));
  let project = website
    ? data.projects.find((p) => same(p.id, website.project_id))
    : data.projects.find((p) => same(p.id, preferred.projectId));
  let companyId = project ? project.company_id || "" : preferred.companyId;

  if (!data.companies.some((c) => same(c.id, companyId)) && !(project && !project.company_id)) {
    companyId = data.companies[0]?.id || "";
  }
  if (!project) {
    project = data.projects.find((p) => same(p.company_id, companyId)) || null;
  }

  const sites = project ? data.websites.filter((w) => same(w.project_id, project.id)) : [];
  const websiteId = website && project && same(website.project_id, project.id) ? website.id : sites[0]?.id || "";

  return { companyId: companyId || "", projectId: project?.id || "", websiteId };
}

export default function useWorkspace({ initial, confirm, prompt, onModeChange }) {
  const [error, setError] = useState("");
  const [companies, setCompanies] = useState([]);
  const [projects, setProjects] = useState([]);
  const [websites, setWebsites] = useState([]);
  const [portfolio, setPortfolio] = useState(null);
  const [selection, setSelection] = useState(() => {
    const stored = readStored();
    return initial?.websiteId
      ? { ...stored, websiteId: initial.websiteId, crawlId: initial.crawlId || "" }
      : stored;
  });
  const [crawls, setCrawls] = useState([]);
  const [history, setHistory] = useState([]);
  const [brainStatus, setBrainStatus] = useState(null);
  const [refreshedAt, setRefreshedAt] = useState(null);
  const [busy, setBusy] = useState({});
  const [crawlStatus, setCrawlStatus] = useState("");
  const [progress, setProgress] = useState(null);
  const [crawlMeta, setCrawlMeta] = useState(EMPTY_META);
  const [summary, setSummary] = useState(null);
  const [findings, setFindings] = useState([]);
  const [scores, setScores] = useState(null);
  const [annotated, setAnnotated] = useState([]);
  const [annotatedDomain, setAnnotatedDomain] = useState("");
  const [recommendations, setRecommendations] = useState(null);
  const [designChat, setDesignChat] = useState(EMPTY_CHAT);
  const [socialChat, setSocialChat] = useState(EMPTY_SOCIAL_CHAT);
  const [mockups, setMockups] = useState(null);
  const [demo, setDemo] = useState(null);
  const [proposal, setProposal] = useState(null);
  const [reports, setReports] = useState(null);
  const [comparison, setComparison] = useState(EMPTY_COMPARISON);
  const [checklist, setChecklist] = useState(null);
  const [competitors, setCompetitors] = useState(null);
  const [conversionPath, setConversionPath] = useState(null);
  const [upgrades, setUpgrades] = useState(null);
  const [verification, setVerification] = useState(null);
  const [opportunities, setOpportunities] = useState([]);
  const [sellRecommendation, setSellRecommendation] = useState(null);
  const [screenshots, setScreenshots] = useState([]);
  const [workflow, setWorkflow] = useState({ status: "", next: [] });

  // Async loaders run across renders, so they read the latest values from refs.
  const selectionRef = useRef(selection);
  const crawlsRef = useRef(crawls);
  const pollRef = useRef(null);
  crawlsRef.current = crawls;

  const { companyId, projectId, websiteId, crawlId } = selection;
  const setBusyKey = (key, value) => setBusy((b) => ({ ...b, [key]: value }));
  const clearError = () => setError("");

  function persist(patch) {
    const next = { ...selectionRef.current, ...patch };
    selectionRef.current = next;
    setSelection(next);
    for (const [key, storageKey] of Object.entries({
      companyId: STORAGE_KEYS.companyId,
      projectId: STORAGE_KEYS.projectId,
      websiteId: STORAGE_KEYS.websiteId,
      crawlId: STORAGE_KEYS.crawlId,
    })) {
      if (next[key]) localStorage.setItem(storageKey, next[key]);
      else localStorage.removeItem(storageKey);
    }
  }

  function resetCrawlPanels() {
    setSummary(null);
    setFindings([]);
    setScores(null);
    setReports(null);
    setAnnotated([]);
    setRecommendations(null);
    setDesignChat(EMPTY_CHAT);
    setSocialChat(EMPTY_SOCIAL_CHAT);
    setMockups(null);
    setDemo(null);
    setProposal(null);
    setComparison(EMPTY_COMPARISON);
    setChecklist(null);
    setCompetitors(null);
    setConversionPath(null);
    setUpgrades(null);
    setVerification(null);
    setOpportunities([]);
    setSellRecommendation(null);
    setScreenshots([]);
    setCrawlMeta(EMPTY_META);
  }

  function stopPolling() {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = null;
  }

  async function loadWorkflow(pid) {
    if (!pid) return setWorkflow({ status: "", next: [] });
    try {
      const data = await api(`/api/projects/${pid}/workflow`);
      setWorkflow({ status: data.status || "created", next: data.allowed_next || [] });
    } catch {
      setWorkflow({ status: "", next: [] });
    }
  }

  async function loadHistory(wid) {
    const data = await api(`/api/websites/${wid}/crawls/history?limit=${HISTORY_LIMIT}`).catch(() => []);
    if (same(selectionRef.current.websiteId, wid)) setHistory(Array.isArray(data) ? data : []);
  }

  async function loadBrainStatus() {
    setBrainStatus(null);
    const status = await api("/api/brain/status").catch((err) => ({ ok: false, error: err.message }));
    setBrainStatus(status);
  }

  async function loadCrawlData(wid, cid) {
    if (!wid || !cid) {
      resetCrawlPanels();
      setCrawlStatus("");
      return null;
    }

    const crawl = await api(`/api/websites/${wid}/crawls/${cid}`);
    const meta = {
      pages: `${crawl.pages_crawled || 0} / ${crawl.pages_discovered || 0}`,
      started: formatDate(crawl.started_at),
      completed: formatDate(crawl.completed_at),
      pagesCrawled: crawl.pages_crawled || 0,
    };

    if (crawl.status !== "completed") {
      resetCrawlPanels();
      setCrawlStatus(crawl.status || "");
      setCrawlMeta(meta);
      return crawl;
    }

    const base = `/api/websites/${wid}/crawls/${cid}`;
    const [
      sum, finds, pack, recs, chat, social, mocks, demoPayload, prop, reps,
      check, comps, conv, ups, ver, shots, opps, sell,
    ] = await Promise.all([
      api(`${base}/findings/summary`).catch(() => null),
      api(`${base}/findings`).catch(() => []),
      api(`${base}/evidence-pack`).catch(() => null),
      api(`${base}/recommendations`).catch(() => null),
      api(`${base}/design/chat`).catch(() => null),
      api(`${base}/social/chat`).catch(() => null),
      api(`${base}/mockups`).catch(() => null),
      api(`${base}/demo`).catch(() => null),
      api(`${base}/proposal`).catch(() => null),
      api(`${base}/reports`).catch(() => null),
      api(`${base}/checklist`).catch(() => null),
      api(`${base}/competitors`).catch(() => null),
      api(`${base}/conversion-path`).catch(() => null),
      api(`${base}/upgrades`).catch(() => null),
      api(`${base}/verification`).catch(() => null),
      api(`${base}/screenshots`).catch(() => null),
      api(`${base}/opportunities`).catch(() => null),
      api(`${base}/sell-recommendation`).catch(() => null),
    ]);

    // A newer selection may have started while these were in flight.
    if (!same(selectionRef.current.crawlId, cid)) return crawl;

    setCrawlStatus(crawl.status);
    setCrawlMeta(meta);
    setSummary(sum);
    setFindings(Array.isArray(finds) ? finds : []);
    setScores(pack?.scores || null);
    setAnnotated(pack?.annotated_screenshots || []);
    setAnnotatedDomain(pack?.website?.domain || "");
    setRecommendations(recs);
    setDesignChat(chat || EMPTY_CHAT);
    setSocialChat(social || EMPTY_SOCIAL_CHAT);
    setMockups(mocks);
    setDemo(demoPayload);
    setProposal(prop);
    setReports(reps);
    setChecklist(check);
    setCompetitors(comps);
    setConversionPath(conv);
    setUpgrades(ups);
    setVerification(ver);
    setScreenshots(shots?.screenshots || []);
    setOpportunities(opps?.opportunities || []);
    setSellRecommendation(sell);
    return crawl;
  }

  async function loadComparison(wid, current, sorted) {
    const idx = sorted.findIndex((c) => same(c.id, current));
    const previous = idx >= 0 ? sorted.slice(idx + 1).find((c) => c.status === "completed") : null;
    if (!wid || !current || !previous) return setComparison(EMPTY_COMPARISON);
    try {
      const data = await api(
        `/api/websites/${wid}/crawls/compare?crawl_a=${encodeURIComponent(previous.id)}&crawl_b=${encodeURIComponent(current)}`
      );
      setComparison({
        new: data.summary?.new ?? 0,
        resolved: data.summary?.resolved ?? 0,
        unchanged: data.summary?.unchanged ?? 0,
        newItems: data.new || [],
        resolvedItems: data.resolved || [],
      });
    } catch {
      setComparison(EMPTY_COMPARISON);
    }
  }

  function startPolling(wid, cid) {
    stopPolling();
    const tick = async () => {
      try {
        const [crawl, prog] = await Promise.all([
          api(`/api/websites/${wid}/crawls/${cid}`),
          api(`/api/websites/${wid}/crawls/${cid}/progress`).catch(() => null),
        ]);
        if (!same(selectionRef.current.crawlId, cid)) return stopPolling();
        setCrawlStatus(crawl.status || "");
        setProgress(prog);
        if (crawl.status === "completed" || crawl.status === "failed") {
          stopPolling();
          setProgress(null);
          setBusyKey("crawl", false);
          if (crawl.status === "completed") {
            await loadCrawlsForWebsite(wid, cid);
            refreshPortfolio();
          } else {
            setError(
              crawl.error_message
                ? "Crawl failed: " + crawl.error_message
                : "Crawl failed. Check the server logs for details."
            );
          }
        }
      } catch (err) {
        console.error(err);
      }
    };
    tick();
    pollRef.current = setInterval(tick, POLL_MS);
  }

  async function loadCrawlsForWebsite(wid, preferredCrawlId = "") {
    stopPolling();
    setProgress(null);
    if (!wid) {
      setHistory([]);
      setCrawls([]);
      persist({ websiteId: "", crawlId: "" });
      resetCrawlPanels();
      setCrawlStatus("");
      return;
    }

    const list = await api(`/api/websites/${wid}/crawls`).catch(() => []);
    const sorted = [...(list || [])].sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
    setCrawls(sorted);
    loadHistory(wid);

    if (!sorted.length) {
      persist({ websiteId: wid, crawlId: "" });
      resetCrawlPanels();
      setCrawlStatus("");
      return;
    }

    const nextCrawl = sorted.some((c) => same(c.id, preferredCrawlId)) ? preferredCrawlId : sorted[0].id;
    persist({ websiteId: wid, crawlId: nextCrawl });
    const crawl = await loadCrawlData(wid, nextCrawl);
    await loadComparison(wid, nextCrawl, sorted);
    if (crawl && isActiveCrawl(crawl.status)) startPolling(wid, nextCrawl);
  }

  async function refreshPortfolio() {
    const [nextCompanies, nextProjects, nextWebsites, nextPortfolio] = await Promise.all([
      api("/api/companies").catch(() => []),
      api("/api/projects").catch(() => []),
      api("/api/websites").catch(() => []),
      api("/api/companies/portfolio/all").catch(() => null),
    ]);
    const data = {
      companies: Array.isArray(nextCompanies) ? nextCompanies : [],
      projects: Array.isArray(nextProjects) ? nextProjects : [],
      websites: Array.isArray(nextWebsites) ? nextWebsites : [],
    };
    setCompanies(data.companies);
    setProjects(data.projects);
    setWebsites(data.websites);
    setPortfolio(nextPortfolio);
    setRefreshedAt(new Date());
    return data;
  }

  async function navigateTo(target = {}) {
    clearError();
    const data = await refreshPortfolio();
    const chosen = resolveSelection(data, {
      companyId: target.companyId ?? "",
      projectId: target.projectId ?? "",
      websiteId: target.websiteId ?? "",
    });
    persist({ ...chosen, crawlId: target.crawlId || "" });
    await loadWorkflow(chosen.projectId);
    await loadCrawlsForWebsite(chosen.websiteId, target.crawlId || "");
  }

  async function bootstrap(preferred = selectionRef.current) {
    clearError();
    await navigateTo(preferred);
  }

  useEffect(() => {
    bootstrap().catch((err) => setError("Could not load workspace: " + err.message));
    loadBrainStatus();
    return stopPolling;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function changeCompany(id) {
    await navigateTo({ companyId: id });
  }

  async function changeProject(id) {
    const project = projects.find((p) => same(p.id, id));
    await navigateTo({ companyId: project?.company_id || companyId, projectId: id });
  }

  async function changeWebsite(id) {
    persist({ websiteId: id, crawlId: "" });
    await loadCrawlsForWebsite(id, "");
  }

  async function changeCrawl(id) {
    stopPolling();
    setProgress(null);
    persist({ crawlId: id });
    const crawl = await loadCrawlData(selectionRef.current.websiteId, id);
    await loadComparison(selectionRef.current.websiteId, id, crawlsRef.current);
    if (crawl && isActiveCrawl(crawl.status)) startPolling(selectionRef.current.websiteId, id);
  }

  async function renameEntity(kind, id, currentName) {
    const name = await prompt({
      title: `Rename ${kind}`,
      label: `${kind[0].toUpperCase()}${kind.slice(1)} name`,
      initial: currentName || "",
      confirmLabel: "Rename",
    });
    if (!name || name === currentName) return;
    clearError();
    try {
      await api(`/api/${kind === "company" ? "companies" : "projects"}/${id}`, json({ name }, "PATCH"));
      await bootstrap();
    } catch (err) {
      setError(`Could not rename ${kind}: ` + err.message);
    }
  }

  async function deleteEntity(kind, id, name) {
    const ok = await confirm({
      title: `Delete ${kind} “${name || kind}”?`,
      message:
        kind === "company"
          ? "Its projects are kept and moved to Unassigned."
          : "This also removes its websites, crawls, and generated reports. This can't be undone.",
      confirmLabel: `Delete ${kind}`,
      danger: true,
    });
    if (!ok) return;
    clearError();
    try {
      await api(`/api/${kind === "company" ? "companies" : "projects"}/${id}`, { method: "DELETE" });
      const current = selectionRef.current;
      const removedProject = kind === "project" && same(current.projectId, id);
      await bootstrap({
        companyId: kind === "company" && same(current.companyId, id) ? "" : current.companyId,
        projectId: removedProject ? "" : current.projectId,
        websiteId: removedProject ? "" : current.websiteId,
        crawlId: removedProject ? "" : current.crawlId,
      });
    } catch (err) {
      setError(`Could not delete ${kind}: ` + err.message);
    }
  }

  async function addCompany(name) {
    if (!name?.trim()) throw new Error("Enter a company name.");
    const company = await api("/api/companies", json({ name: name.trim() }));
    await navigateTo({ companyId: company.id });
  }

  async function addProject(name) {
    if (!name?.trim()) throw new Error("Enter a project name.");
    // Prefer the live selection (modal stays open across steps).
    const cid = selectionRef.current.companyId || null;
    const body = { name: name.trim() };
    if (cid) body.company_id = cid;
    const project = await api("/api/projects", json(body));
    await navigateTo({ companyId: cid || "", projectId: project.id });
  }

  async function addWebsite(rawUrl, role = "primary") {
    const pid = selectionRef.current.projectId;
    const cid = selectionRef.current.companyId;
    if (!pid) throw new Error("Pick or create a project first.");
    const url = normalizeWebsiteUrl(rawUrl);
    if (!url) throw new Error("Enter a valid website URL.");
    const siteRole = role === "competitor" ? "competitor" : "primary";
    const website = await api(
      `/api/projects/${pid}/websites`,
      json({ url, role: siteRole })
    );
    await navigateTo({ companyId: cid || "", projectId: pid, websiteId: website.id });
  }

  async function createCrawl() {
    if (!websiteId) return setError("Select a website first.");
    clearError();
    setBusyKey("crawl", true);
    try {
      const crawl = await api(`/api/websites/${websiteId}/crawls`, { method: "POST" });
      setCrawlStatus(crawl.status || "queued");
      await loadCrawlsForWebsite(websiteId, crawl.id);
      startPolling(websiteId, crawl.id);
      onModeChange?.("overview");
    } catch (err) {
      setError("Could not start crawl: " + err.message);
      setBusyKey("crawl", false);
    }
  }

  async function runCrawlAction(key, mode, path, apply, failMessage, timeoutMs = 0) {
    if (!crawlId) return setError("No crawl selected yet.");
    clearError();
    if (mode) onModeChange?.(mode);
    setBusyKey(key, true);
    try {
      const data = await api(`/api/websites/${websiteId}/crawls/${crawlId}/${path}`, {
        method: "POST",
        ...(timeoutMs ? { timeoutMs } : {}),
      });
      await apply(data);
    } catch (err) {
      setError(`${failMessage}: ${err.message}`);
    } finally {
      setBusyKey(key, false);
    }
  }

  const askBrain = () =>
    runCrawlAction(
      "brain",
      "brain",
      "recommendations",
      async (data) => {
        setRecommendations(data);
        if (data.demo) setDemo(data.demo);
        if (data.mockups) setMockups(data.mockups);
        const [check, social] = await Promise.all([
          api(`/api/websites/${websiteId}/crawls/${crawlId}/checklist?rebuild=true`).catch(() => null),
          api(`/api/websites/${websiteId}/crawls/${crawlId}/social/chat`).catch(() => null),
        ]);
        if (check) setChecklist(check);
        if (social) setSocialChat(social);
        if (data.source === "rule_based_fallback" && data.error) {
          setError(
            "Local model timed out — using the crawl-based plan instead. "
            + "On CPU, Ask Brain skips the big model by default (profile-first).",
          );
        }
      },
      "Could not get recommendations",
      240000,
    );

  const generateMockups = () =>
    runCrawlAction("mockups", "design", "mockups", (data) => {
      setMockups(data);
      if (data.demo) setDemo(data.demo);
    }, "Could not generate mockups");

  const generateDemo = () =>
    runCrawlAction("demo", "design", "demo", (data) => setDemo(data), "Could not generate demo site");

  const generateProposal = () =>
    runCrawlAction("proposal", "proposal", "proposal", (data) => {
      setProposal(data);
      if (data.source === "rule_based_fallback" && data.error) {
        setError("Ollama unavailable for narrative — used template fallback. " + data.error);
      }
    }, "Could not generate proposal");

  const exportPdf = () =>
    runCrawlAction("pdf", null, "proposal/pdf", async (data) => {
      const refreshed = await api(`/api/websites/${websiteId}/crawls/${crawlId}/proposal`).catch(() => null);
      if (refreshed) setProposal(refreshed);
      if (data.url) window.open(data.url, "_blank", "noopener");
    }, "Could not export PDF");

  const rebuildProof = () =>
    runCrawlAction("proof", "audit", "reports/proof", async (data) => {
      const refreshed = await api(`/api/websites/${websiteId}/crawls/${crawlId}/reports`).catch(() => null);
      setReports(refreshed || data);
      if (data.url) window.open(data.url, "_blank", "noopener");
    }, "Could not rebuild proof pack");

  async function sendDesignChat(message, imagePath = null) {
    if (!crawlId) return setError("No crawl selected yet.");
    clearError();
    onModeChange?.("design");
    setBusyKey("chat", true);
    const preview = imagePath
      ? `${message || "Review this screenshot"} [${imagePath}]`
      : message;
    setDesignChat((prev) => ({
      ...prev,
      messages: [
        ...(prev.messages || []),
        { role: "user", content: preview, image_path: imagePath || undefined },
        { role: "assistant", content: "Working on it…", pending: true },
      ],
    }));
    const path = `/api/websites/${websiteId}/crawls/${crawlId}/design/chat`;
    const body = { message: message || "" };
    if (imagePath) body.image_path = imagePath;
    try {
      // CPU Ollama + optional demo regen: keep UI waiting past chat's
      // short backend LLM budget so rule fallback can still return.
      const timeoutMs = imagePath ? 300000 : 240000;
      const data = await api(path, { ...json(body), timeoutMs });
      setDesignChat(data);
      if (data.mockups) setMockups(data.mockups);
      if (data.demo) setDemo(data.demo);
    } catch (err) {
      setError("Site chat failed: " + err.message);
      setDesignChat((prev) => ({
        ...prev,
        messages: (prev.messages || []).filter((m) => !m.pending),
      }));
      const chat = await api(path).catch(() => null);
      if (chat) setDesignChat(chat);
    } finally {
      setBusyKey("chat", false);
    }
  }

  async function sendSocialChat(message) {
    if (!crawlId) return setError("No crawl selected yet.");
    clearError();
    onModeChange?.("socials");
    setBusyKey("socialChat", true);
    setSocialChat((prev) => ({
      ...prev,
      messages: [
        ...(prev.messages || []),
        { role: "user", content: message },
        { role: "assistant", content: "Working on it…", pending: true },
      ],
    }));
    const path = `/api/websites/${websiteId}/crawls/${crawlId}/social/chat`;
    try {
      const data = await api(path, { ...json({ message: message || "" }), timeoutMs: 120000 });
      setSocialChat({
        messages: data.messages || [],
        social_content: data.social_content || null,
        updated_at: data.updated_at,
        domain: data.domain,
        crawl_id: data.crawl_id,
      });
    } catch (err) {
      setError("Social chat failed: " + err.message);
      setSocialChat((prev) => ({
        ...prev,
        messages: (prev.messages || []).filter((m) => !m.pending),
      }));
      const chat = await api(path).catch(() => null);
      if (chat) setSocialChat(chat);
    } finally {
      setBusyKey("socialChat", false);
    }
  }

  async function saveProposal(patch) {
    if (!crawlId) return setError("No crawl selected yet.");
    clearError();
    setBusyKey("proposalSave", true);
    try {
      const data = await api(
        `/api/websites/${websiteId}/crawls/${crawlId}/proposal`,
        json(patch, "PATCH")
      );
      setProposal(data);
    } catch (err) {
      setError("Could not save proposal: " + err.message);
    } finally {
      setBusyKey("proposalSave", false);
    }
  }

  async function generateVerification() {
    if (!crawlId) return setError("No crawl selected yet.");
    clearError();
    setBusyKey("verification", true);
    try {
      const data = await api(
        `/api/websites/${websiteId}/crawls/${crawlId}/verification`,
        { method: "POST" }
      );
      setVerification(data);
      if (data.url) window.open(data.url, "_blank", "noopener");
    } catch (err) {
      setError("Could not build verification report: " + err.message);
    } finally {
      setBusyKey("verification", false);
    }
  }

  async function toggleChecklistItem(id, done) {
    if (!crawlId || !id) return;
    try {
      const data = await api(
        `/api/websites/${websiteId}/crawls/${crawlId}/checklist`,
        json({ items: [{ id, done }] }, "PATCH")
      );
      setChecklist(data);
    } catch (err) {
      setError("Could not update checklist: " + err.message);
    }
  }

  async function advanceWorkflow(status) {
    if (!projectId || !status) return;
    clearError();
    try {
      await api(`/api/projects/${projectId}/status`, json({ status }, "PATCH"));
      await loadWorkflow(projectId);
    } catch (err) {
      setError("Could not update workflow: " + err.message);
    }
  }

  async function generateOpportunities() {
    if (!crawlId) return setError("No crawl selected yet.");
    clearError();
    setBusyKey("opportunities", true);
    try {
      const data = await api(
        `/api/websites/${websiteId}/crawls/${crawlId}/opportunities/generate`,
        { method: "POST" }
      );
      setOpportunities(data.opportunities || []);
      const sell = await api(`/api/websites/${websiteId}/crawls/${crawlId}/sell-recommendation`).catch(() => null);
      setSellRecommendation(sell);
      onModeChange?.("opportunities");
    } catch (err) {
      setError("Could not generate opportunities: " + err.message);
    } finally {
      setBusyKey("opportunities", false);
    }
  }

  async function patchOpportunity(id, patch) {
    if (!crawlId || !id) return;
    clearError();
    setBusy((b) => ({ ...b, opportunityId: id }));
    try {
      const updated = await api(
        `/api/websites/${websiteId}/crawls/${crawlId}/opportunities/${id}`,
        json(patch, "PATCH")
      );
      setOpportunities((prev) => prev.map((o) => (same(o.id, id) ? { ...o, ...updated } : o)));
      const sell = await api(`/api/websites/${websiteId}/crawls/${crawlId}/sell-recommendation`).catch(() => null);
      setSellRecommendation(sell);
    } catch (err) {
      setError("Could not update opportunity: " + err.message);
    } finally {
      setBusy((b) => {
        const next = { ...b };
        delete next.opportunityId;
        return next;
      });
    }
  }

  async function acceptSellRecommendation(packageKey, customize = false) {
    if (!crawlId) return setError("No crawl selected yet.");
    clearError();
    setBusyKey("sell", true);
    try {
      const data = await api(
        `/api/websites/${websiteId}/crawls/${crawlId}/sell-recommendation/accept`,
        json({ package: packageKey || undefined, customize: Boolean(customize) })
      );
      setSellRecommendation(data);
      if (Array.isArray(data.opportunities)) setOpportunities(data.opportunities);
      else {
        const opps = await api(`/api/websites/${websiteId}/crawls/${crawlId}/opportunities`).catch(() => null);
        if (opps?.opportunities) setOpportunities(opps.opportunities);
      }
    } catch (err) {
      setError("Could not accept recommendation: " + err.message);
    } finally {
      setBusyKey("sell", false);
    }
  }

  const visibleProjects = useMemo(
    () => (companyId ? projects.filter((p) => same(p.company_id, companyId)) : projects),
    [projects, companyId]
  );

  const projectWebsites = useMemo(() => {
    const list = websites.filter((w) => same(w.project_id, projectId));
    if (websiteId && !list.some((w) => same(w.id, websiteId))) {
      const orphan = websites.find((w) => same(w.id, websiteId));
      if (orphan) return [orphan, ...list];
    }
    return list;
  }, [websites, projectId, websiteId]);

  const currentWebsite = websites.find((w) => same(w.id, websiteId));

  return {
    error,
    setError,
    clearError,
    companies,
    projects,
    websites,
    portfolio,
    visibleProjects,
    projectWebsites,
    currentWebsite,
    companyId,
    projectId,
    websiteId,
    crawlId,
    crawls,
    history,
    brainStatus,
    refreshedAt,
    busy,
    crawlStatus,
    progress,
    running: isActiveCrawl(crawlStatus) || Boolean(busy.crawl),
    crawlMeta,
    summary,
    findings,
    scores,
    annotated,
    annotatedDomain,
    recommendations,
    brainMeta: brainMetaFrom(recommendations),
    designChat,
    socialChat,
    mockups,
    demo,
    proposal,
    reports,
    comparison,
    checklist,
    competitors,
    conversionPath,
    upgrades,
    verification,
    opportunities,
    sellRecommendation,
    screenshots,
    workflow,
    actions: {
      refresh: () => bootstrap().catch((err) => setError("Could not refresh: " + err.message)),
      navigateTo,
      changeCompany,
      changeProject,
      changeWebsite,
      changeCrawl,
      renameEntity,
      deleteEntity,
      addCompany,
      addProject,
      addWebsite,
      createCrawl,
      askBrain,
      generateMockups,
      generateDemo,
      generateProposal,
      exportPdf,
      rebuildProof,
      sendDesignChat,
      sendSocialChat,
      saveProposal,
      generateVerification,
      toggleChecklistItem,
      advanceWorkflow,
      loadBrainStatus,
      generateOpportunities,
      patchOpportunity,
      acceptSellRecommendation,
    },
  };
}
