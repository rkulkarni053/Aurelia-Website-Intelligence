const API_BASE = import.meta.env.VITE_API_BASE || "";

export async function api(path, options = {}) {
  const { timeoutMs, signal: outerSignal, ...fetchOptions } = options;
  const timeout = typeof timeoutMs === "number" ? timeoutMs : 0;
  const controller = timeout > 0 ? new AbortController() : null;
  let timer = null;
  if (controller) {
    timer = setTimeout(() => controller.abort(), timeout);
    if (outerSignal) {
      if (outerSignal.aborted) controller.abort();
      else outerSignal.addEventListener("abort", () => controller.abort(), { once: true });
    }
  }

  try {
    const response = await fetch(`${API_BASE}${path}`, {
      ...fetchOptions,
      signal: controller ? controller.signal : outerSignal,
    });

    if (!response.ok) {
      let detail = `${response.status} ${response.statusText}`;
      try {
        const body = await response.json();
        if (body.detail) {
          detail =
            typeof body.detail === "string"
              ? body.detail
              : JSON.stringify(body.detail);
        }
      } catch {
        /* ignore */
      }
      throw new Error(detail);
    }

    if (response.status === 204) return null;
    const text = await response.text();
    if (!text) return null;
    return JSON.parse(text);
  } catch (err) {
    if (err?.name === "AbortError") {
      throw new Error("Request timed out — try again");
    }
    throw err;
  } finally {
    if (timer) clearTimeout(timer);
  }
}

export function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

export function formatDate(value) {
  if (!value) return "—";
  return new Date(value).toLocaleString();
}

export function normalizeWebsiteUrl(raw) {
  let url = (raw || "").trim();
  if (!url) return "";
  if (!/^https?:\/\//i.test(url)) url = "https://" + url;
  return url;
}

export const WORKFLOW_LABELS = {
  created: "Created",
  crawling: "Crawling",
  evidence_collected: "Evidence collected",
  analyzing: "Analyzing",
  awaiting_approval: "Awaiting approval",
  approved: "Approved",
  implementation: "Implementation",
  verification: "Verification",
  completed: "Completed",
};

export const STORAGE_KEYS = {
  companyId: "wi_company_id",
  projectId: "wi_project_id",
  websiteId: "wi_website_id",
  crawlId: "wi_crawl_id",
  mode: "wi_mode",
  theme: "aurelia_theme",
};
