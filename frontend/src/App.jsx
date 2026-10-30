import { useEffect, useMemo, useState } from "react";
import AddModal from "./components/AddModal";
import Atmosphere from "./components/Atmosphere";
import CrawlProgress from "./components/CrawlProgress";
import { useDialogs } from "./components/Dialogs";
import Icon from "./components/Icon";
import NextStepBar from "./components/NextStepBar";
import Sidebar from "./components/Sidebar";
import StatusBar from "./components/StatusBar";
import TopNav from "./components/TopNav";
import Topbar from "./components/Topbar";
import AuditMode from "./components/modes/AuditMode";
import BrainMode from "./components/modes/BrainMode";
import DesignMode from "./components/modes/DesignMode";
import OpportunitiesMode from "./components/modes/OpportunitiesMode";
import OverviewMode from "./components/modes/OverviewMode";
import ProposalMode from "./components/modes/ProposalMode";
import SocialMode from "./components/modes/SocialMode";
import CrawlsView from "./components/views/CrawlsView";
import ProjectsView from "./components/views/ProjectsView";
import SettingsView from "./components/views/SettingsView";
import SitesView from "./components/views/SitesView";
import useRoute from "./hooks/useRoute";
import useTheme from "./hooks/useTheme";
import useWorkspace from "./hooks/useWorkspace";

const FUNNEL_TABS = [
  { id: "overview", label: "Overview", icon: "eye", step: 1 },
  { id: "diagnose", label: "Diagnose", icon: "clipboard", step: 2 },
  { id: "opportunities", label: "Opportunities", icon: "trend", step: 3 },
  { id: "design", label: "Design", icon: "brush", step: 4 },
  { id: "proposal", label: "Proposal", icon: "signature", step: 5 },
];

const MORE_TABS = [
  { id: "socials", label: "Socials", icon: "share" },
  { id: "deliver", label: "Deliver", icon: "check" },
  { id: "verify", label: "Verify", icon: "search" },
];

function resolveNextStep(mode, { completed, opportunities, demo, recommendations }) {
  if (!completed) return null;
  const approved = (opportunities || []).some((o) => o.status === "approved" || o.proposal_status === "in_proposal");
  if (mode === "overview") {
    return {
      mode: "diagnose",
      label: "Diagnose findings",
      hint: "Review evidence, then ask Aurelia for commercial recommendations.",
    };
  }
  if (mode === "diagnose") {
    return {
      mode: "opportunities",
      label: recommendations ? "Review opportunities" : "Generate opportunities",
      hint: recommendations
        ? "Turn findings into priced themes you can approve and sell."
        : "Cluster the audit into sellable opportunities.",
    };
  }
  if (mode === "opportunities") {
    return {
      mode: "design",
      label: approved ? "Build demo for scope" : "Open design studio",
      hint: approved
        ? "Generate a clickable demo grounded in the approved scope."
        : "Preview a remodel before you draft the proposal.",
    };
  }
  if (mode === "design") {
    return {
      mode: "proposal",
      label: demo ? "Draft proposal" : "Continue to proposal",
      hint: "Package the story, scope, and investment for the client.",
    };
  }
  return null;
}

const same = (a, b) => String(a ?? "") === String(b ?? "");

export default function App() {
  const dialogs = useDialogs();
  const { theme, toggleTheme } = useTheme();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [addOpen, setAddOpen] = useState(false);
  const [moreOpen, setMoreOpen] = useState(false);

  const [route, navigate] = useRoute((next) => {
    if (next.site && (!same(next.site, ws.websiteId) || (next.crawl && !same(next.crawl, ws.crawlId)))) {
      ws.actions.navigateTo({ websiteId: next.site, crawlId: next.crawl });
    }
  });

  const ws = useWorkspace({
    initial: { websiteId: route.site, crawlId: route.crawl },
    confirm: dialogs.confirm,
    prompt: dialogs.prompt,
    onModeChange: (mode) => navigate({ view: "dashboard", mode }),
  });
  const { actions } = ws;

  useEffect(() => {
    navigate({ site: ws.websiteId, crawl: ws.crawlId }, { replace: true });
  }, [ws.websiteId, ws.crawlId, navigate]);

  const { view, mode } = route;
  const hasWebsite = Boolean(ws.websiteId && ws.currentWebsite);
  const completed = ws.crawlStatus === "completed";
  const lastCrawlAt = ws.crawls[0]?.completed_at || ws.crawls[0]?.created_at || null;
  const moreActive = MORE_TABS.some((t) => t.id === mode);
  const nextStep = useMemo(
    () =>
      resolveNextStep(mode, {
        completed,
        opportunities: ws.opportunities,
        demo: ws.demo,
        recommendations: ws.recommendations,
      }),
    [mode, completed, ws.opportunities, ws.demo, ws.recommendations]
  );

  const goMode = (target) => {
    setMoreOpen(false);
    navigate({ view: "dashboard", mode: target });
  };

  const alerts = [
    ws.error ? { tone: "bad", text: ws.error } : null,
    ws.running ? { tone: "info", text: `Crawl in progress for ${ws.currentWebsite?.domain || "site"}` } : null,
    ws.brainStatus && !ws.brainStatus.ok
      ? { tone: "bad", text: "Ollama brain is offline — AI steps will use fallbacks." }
      : null,
    ws.brainStatus?.ok && !ws.brainStatus.model_ready
      ? { tone: "warn", text: `Model ${ws.brainStatus.configured_model} is not pulled yet.` }
      : null,
  ].filter(Boolean);

  const goDashboard = async (target) => {
    setSidebarOpen(false);
    navigate({ view: "dashboard", mode: target.mode || "overview" });
    await actions.navigateTo(target);
  };

  function onSideNavigate(target) {
    setSidebarOpen(false);
    if (target === "reports") return navigate({ view: "dashboard", mode: "proposal" });
    if (target === "dashboard") return navigate({ view: "dashboard", mode: mode === "proposal" ? "overview" : mode });
    if (target === "settings") actions.loadBrainStatus();
    navigate({ view: target });
  }

  async function runAdd(fn, value, roleOrOpts, maybeOpts) {
    const opts =
      roleOrOpts && typeof roleOrOpts === "object" && !Array.isArray(roleOrOpts)
        ? roleOrOpts
        : maybeOpts || {};
    const role =
      typeof roleOrOpts === "string" ? roleOrOpts : undefined;
    if (role !== undefined) await fn(value, role);
    else await fn(value);
    // Keep the modal open through company → project → website so the
    // full chain can be completed in one pass. Close after the last step.
    if (opts.close) {
      setAddOpen(false);
      navigate({ view: "dashboard", mode: "overview" });
    }
  }

  function renderModes() {
    if (ws.running && !completed) {
      return <CrawlProgress progress={ws.progress} crawl={ws.crawls.find((c) => same(c.id, ws.crawlId))} domain={ws.currentWebsite?.domain} />;
    }
    switch (mode) {
      case "design":
        return (
          <DesignMode
            designChat={ws.designChat}
            mockups={ws.mockups}
            demo={ws.demo}
            crawlId={ws.crawlId}
            busy={ws.busy}
            disabled={!completed}
            screenshots={ws.screenshots}
            onSend={actions.sendDesignChat}
            onGenerate={actions.generateMockups}
            onGenerateDemo={actions.generateDemo}
          />
        );
      case "socials":
        return (
          <SocialMode
            socialChat={ws.socialChat}
            busy={ws.busy}
            disabled={!completed}
            onSend={actions.sendSocialChat}
          />
        );
      case "diagnose":
      case "audit":
        return (
          <div className="mode-body diagnose-stack">
            <AuditMode
              findings={ws.findings}
              summary={ws.summary}
              annotated={ws.annotated}
              domain={ws.annotatedDomain || ws.currentWebsite?.domain}
              crawlId={ws.crawlId}
              reports={ws.reports}
              busy={ws.busy}
              onRebuildProof={actions.rebuildProof}
              category={route.category}
              onCategoryChange={(category) => navigate({ category }, { replace: true })}
            />
            {mode === "diagnose" ? (
              <BrainMode
                recommendations={ws.recommendations}
                meta={ws.brainMeta}
                loading={ws.busy.brain}
                onAsk={actions.askBrain}
                demo={ws.demo}
                opportunities={ws.opportunities}
                checklist={null}
                onToggleChecklist={actions.toggleChecklistItem}
                onOpenDesign={() => {
                  navigate({ view: "dashboard", mode: "design" });
                  actions.generateDemo();
                }}
              />
            ) : null}
          </div>
        );
      case "opportunities":
        return (
          <OpportunitiesMode
            opportunities={ws.opportunities}
            sell={ws.sellRecommendation}
            loading={ws.busy.opportunities}
            busy={ws.busy}
            onGenerate={actions.generateOpportunities}
            onPatch={actions.patchOpportunity}
            onAcceptSell={actions.acceptSellRecommendation}
            onBuildProposal={() => {
              navigate({ view: "dashboard", mode: "proposal" });
              actions.generateProposal();
            }}
            onOpenDiagnose={() => navigate({ view: "dashboard", mode: "diagnose" })}
            onOpenDesign={() => {
              navigate({ view: "dashboard", mode: "design" });
              actions.generateDemo();
            }}
          />
        );
      case "brain":
        return (
          <BrainMode
            recommendations={ws.recommendations}
            meta={ws.brainMeta}
            loading={ws.busy.brain}
            onAsk={actions.askBrain}
            demo={ws.demo}
            opportunities={ws.opportunities}
            checklist={ws.checklist}
            onToggleChecklist={actions.toggleChecklistItem}
            onOpenDesign={() => {
              navigate({ view: "dashboard", mode: "design" });
              actions.generateDemo();
            }}
          />
        );
      case "deliver":
        return (
          <BrainMode
            recommendations={ws.recommendations}
            meta="Implementation checklist"
            loading={false}
            onAsk={actions.askBrain}
            demo={null}
            opportunities={ws.opportunities}
            checklist={ws.checklist}
            onToggleChecklist={actions.toggleChecklistItem}
            onOpenDesign={() => navigate({ view: "dashboard", mode: "design" })}
          />
        );
      case "verify":
        return (
          <OverviewMode
            summary={ws.summary}
            scores={ws.scores}
            crawlMeta={ws.crawlMeta}
            comparison={ws.comparison}
            crawls={ws.crawls}
            crawlId={ws.crawlId}
            history={ws.history}
            conversionPath={ws.conversionPath}
            competitors={ws.competitors}
            upgrades={ws.upgrades}
            verification={ws.verification}
            busy={ws.busy}
            onOpenAudit={(category = "") => navigate({ view: "dashboard", mode: "diagnose", category })}
            onSelectCrawl={actions.changeCrawl}
            onVerify={actions.generateVerification}
          />
        );
      case "proposal":
        return (
          <ProposalMode
            proposal={ws.proposal}
            domain={ws.currentWebsite?.domain}
            crawlId={ws.crawlId}
            loading={ws.busy.proposal}
            busy={ws.busy}
            onGenerate={actions.generateProposal}
            onExportPdf={actions.exportPdf}
            onSave={actions.saveProposal}
          />
        );
      default:
        return (
          <OverviewMode
            summary={ws.summary}
            scores={ws.scores}
            crawlMeta={ws.crawlMeta}
            comparison={ws.comparison}
            crawls={ws.crawls}
            crawlId={ws.crawlId}
            history={ws.history}
            conversionPath={ws.conversionPath}
            competitors={ws.competitors}
            upgrades={ws.upgrades}
            verification={ws.verification}
            busy={ws.busy}
            onOpenAudit={(category = "") => navigate({ view: "dashboard", mode: "diagnose", category })}
            onSelectCrawl={actions.changeCrawl}
            onVerify={actions.generateVerification}
          />
        );
    }
  }

  function renderDashboard() {
    return (
      <>
        <Topbar
          hasWebsite={hasWebsite}
          website={ws.currentWebsite}
          crawlStatus={ws.crawlStatus}
          companies={ws.companies}
          projects={ws.visibleProjects}
          websites={ws.projectWebsites}
          crawls={ws.crawls}
          companyId={ws.companyId}
          projectId={ws.projectId}
          websiteId={ws.websiteId}
          crawlId={ws.crawlId}
          workflow={ws.workflow}
          busy={ws.busy}
          completed={completed}
          mode={mode}
          onCompanyChange={actions.changeCompany}
          onProjectChange={actions.changeProject}
          onWebsiteChange={actions.changeWebsite}
          onCrawlChange={actions.changeCrawl}
          onRefresh={actions.refresh}
          onAskBrain={actions.askBrain}
          onProposal={actions.generateProposal}
          onPdf={actions.exportPdf}
          onCrawl={actions.createCrawl}
          onAdvanceWorkflow={actions.advanceWorkflow}
          onGoMode={goMode}
        />

        {!hasWebsite ? (
          <div className="empty-state">
            <div className="empty-icon">
              <Icon name="globe" size={26} />
            </div>
            <h3>{ws.projectId ? "This project has no website yet" : "Pick a website to begin"}</h3>
            <p>
              {ws.projectId
                ? "Add a URL to this project before you can crawl, design, or propose."
                : "Search for a site above, or add a company, project, and URL."}
            </p>
            <button type="button" className="action-btn primary solo" onClick={() => setAddOpen(true)}>
              <Icon name="plus" size={15} />
              <span>Add website</span>
            </button>
          </div>
        ) : !ws.crawlId && !ws.running ? (
          <div className="empty-state">
            <div className="empty-icon">
              <Icon name="play" size={24} />
            </div>
            <h3>Ready to crawl</h3>
            <p>
              No crawls yet for {ws.currentWebsite?.domain}. A typical small site finishes in about
              5–30 seconds; larger sites take longer because we also run browser, accessibility,
              and score checks.
            </p>
            <button type="button" className="action-btn primary solo" onClick={actions.createCrawl}>
              <Icon name="play" size={14} />
              <span>Run crawl</span>
            </button>
          </div>
        ) : (
          <>
            <div className="mode-toolbar">
              <nav className="mode-tabs funnel-tabs" role="tablist" aria-label="Sales funnel">
                {FUNNEL_TABS.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    role="tab"
                    aria-selected={mode === item.id}
                    className={`mode-tab${mode === item.id ? " active" : ""}`}
                    onClick={() => goMode(item.id)}
                  >
                    <span className="mode-step">{item.step}</span>
                    {item.label}
                  </button>
                ))}
                <div className={`mode-more${moreOpen || moreActive ? " open" : ""}`}>
                  <button
                    type="button"
                    className={`mode-tab more-trigger${moreActive ? " active" : ""}`}
                    aria-expanded={moreOpen}
                    aria-haspopup="menu"
                    onClick={() => setMoreOpen((v) => !v)}
                  >
                    More
                  </button>
                  {moreOpen ? (
                    <div className="mode-more-menu" role="menu">
                      {MORE_TABS.map((item) => (
                        <button
                          key={item.id}
                          type="button"
                          role="menuitem"
                          className={mode === item.id ? "active" : ""}
                          onClick={() => goMode(item.id)}
                        >
                          <Icon name={item.icon} size={15} />
                          {item.label}
                        </button>
                      ))}
                    </div>
                  ) : null}
                </div>
              </nav>
              {nextStep ? (
                <NextStepBar
                  label={nextStep.label}
                  hint={nextStep.hint}
                  onClick={() => {
                    goMode(nextStep.mode);
                    if (nextStep.mode === "opportunities" && !(ws.opportunities || []).length) {
                      actions.generateOpportunities();
                    }
                    if (nextStep.mode === "design") actions.generateDemo();
                    if (nextStep.mode === "proposal") actions.generateProposal();
                  }}
                />
              ) : null}
            </div>
            {renderModes()}
          </>
        )}
      </>
    );
  }

  return (
    <>
      <Atmosphere />
      <div className="app">
        <Sidebar
          open={sidebarOpen}
          view={view}
          mode={mode}
          counts={{
            projects: ws.portfolio?.summary?.projects || ws.projects.length,
            websites: ws.portfolio?.summary?.websites || ws.websites.length,
          }}
          onNavigate={onSideNavigate}
          onClose={() => setSidebarOpen(false)}
          onOpenAdd={() => setAddOpen(true)}
        />

        <div className="main">
          <TopNav
            portfolio={ws.portfolio}
            alerts={alerts}
            theme={theme}
            onToggleTheme={toggleTheme}
            onSelect={goDashboard}
            onMenu={() => setSidebarOpen(true)}
          />

          <main className="workspace">
            {ws.error ? (
              <div className="error" role="alert">
                <span>{ws.error}</span>
                <button type="button" className="icon-btn" onClick={ws.clearError} aria-label="Dismiss">
                  <Icon name="close" size={13} />
                </button>
              </div>
            ) : null}

            {view === "dashboard" && renderDashboard()}
            {view === "projects" && (
              <ProjectsView
                portfolio={ws.portfolio}
                activeProjectId={ws.projectId}
                onNavigate={goDashboard}
                onRename={actions.renameEntity}
                onDelete={actions.deleteEntity}
                onOpenAdd={() => setAddOpen(true)}
              />
            )}
            {view === "sites" && (
              <SitesView
                portfolio={ws.portfolio}
                activeWebsiteId={ws.websiteId}
                onNavigate={goDashboard}
                onOpenAdd={() => setAddOpen(true)}
              />
            )}
            {view === "crawls" && (
              <CrawlsView
                website={ws.currentWebsite}
                crawls={ws.crawls}
                crawlId={ws.crawlId}
                history={ws.history}
                busy={ws.busy}
                onSelect={async (id) => {
                  navigate({ view: "dashboard", mode: "overview" });
                  await actions.changeCrawl(id);
                }}
                onCrawl={actions.createCrawl}
              />
            )}
            {view === "settings" && (
              <SettingsView brainStatus={ws.brainStatus} onRecheck={actions.loadBrainStatus} />
            )}
          </main>

          <StatusBar
            refreshedAt={ws.refreshedAt}
            lastCrawlAt={lastCrawlAt}
            brainStatus={ws.brainStatus}
            onRefresh={actions.refresh}
          />
        </div>
      </div>

      <AddModal
        open={addOpen}
        onClose={() => setAddOpen(false)}
        companies={ws.companies}
        companyId={ws.companyId}
        projectId={ws.projectId}
        onSelectCompany={actions.changeCompany}
        onAddCompany={(name) => runAdd(actions.addCompany, name)}
        onAddProject={(name) => runAdd(actions.addProject, name)}
        onAddWebsite={(url, role) => runAdd(actions.addWebsite, url, role, { close: true })}
        onError={ws.setError}
      />
    </>
  );
}
