const DATA_URL = "games.json";

const qs = (selector, root = document) => root.querySelector(selector);
const qsa = (selector, root = document) => [...root.querySelectorAll(selector)];

const state = {
  data: null,
  issueByTitle: new Map(),
  search: ""
};

function platformClass(platformClassName) {
  if (platformClassName === "native-arm64") return "platform-native";
  if (platformClassName === "crossover") return "platform-crossover";
  return "platform-whisky";
}

function statusClass(status) {
  if (status === "working") return "badge-working";
  if (status === "working-partial") return "badge-working-partial";
  return "badge-partial";
}

function voteLabel(count) {
  const safe = Number.isFinite(count) ? count : 0;
  return `${safe} vote${safe === 1 ? "" : "s"}`;
}

function renderTested(tested) {
  const grid = qs("[data-tested-grid]");
  const template = qs("#tested-card-template");
  grid.textContent = "";

  tested.forEach((game) => {
    const node = template.content.firstElementChild.cloneNode(true);
    const media = qs(".media", node);
    const badge = qs(".badge", node);

    if (game.image) {
      const img = document.createElement("img");
      img.src = game.image;
      img.alt = game.imageAlt;
      img.loading = "lazy";
      media.append(img);
    } else {
      media.classList.add("placeholder");
      media.dataset.title = `${game.title}\\A ${game.recipe}`;
      media.setAttribute("aria-label", game.imageAlt);
    }

    badge.textContent = game.statusLabel;
    badge.classList.add(statusClass(game.status));
    const platform = qs(".platform-badge", node);
    platform.textContent = game.platformLabel || game.recipe;
    platform.classList.add(platformClass(game.platformClass));
    qs(".year", node).textContent = game.year;
    qs("h3", node).textContent = game.title;
    qs(".summary", node).textContent = game.summary;
    qs(".recipe", node).textContent = game.recipe;
    qs(".repo-link", node).href = game.repo;
    grid.append(node);
  });
}

function issueFor(game) {
  return state.issueByTitle.get(game.issueTitle.toLowerCase());
}

function renderWishlist() {
  const grid = qs("[data-wishlist-grid]");
  const template = qs("#wishlist-card-template");
  const terms = state.search.trim().toLowerCase();
  grid.textContent = "";

  state.data.wishlist
    .filter((game) => {
      if (!terms) return true;
      return [game.title, game.year, game.family, game.whyHard].join(" ").toLowerCase().includes(terms);
    })
    .forEach((game) => {
      const issue = issueFor(game);
      const node = template.content.firstElementChild.cloneNode(true);
      qs(".family", node).textContent = game.family;
      qs(".year", node).textContent = game.year;
      qs("h3", node).textContent = game.title;
      qs("p", node).textContent = game.whyHard;

      const link = qs(".vote-button", node);
      link.href = issue?.html_url || game.issueUrl || `https://github.com/${state.data.meta.owner}/${state.data.meta.repo}/issues?q=${encodeURIComponent(game.issueTitle)}`;
      link.setAttribute("aria-label", `Vote for ${game.title} on GitHub`);

      qs(".vote-count", node).textContent = voteLabel(issue?.reactions?.["+1"] || 0);
      grid.append(node);
    });
}

function renderStats() {
  const tested = state.data.tested;
  const working = tested.length;
  const wishlist = state.data.wishlist.length;
  const votes = [...state.issueByTitle.values()].reduce((sum, issue) => sum + (issue.reactions?.["+1"] || 0), 0);

  qs('[data-stat="working"]').textContent = working;
  qs('[data-stat="wishlist"]').textContent = wishlist;
  qs('[data-stat="votes"]').textContent = votes;
}

async function fetchIssues(meta) {
  const url = `https://api.github.com/repos/${meta.owner}/${meta.repo}/issues?labels=wishlist&state=open&per_page=100`;
  const response = await fetch(url, {
    headers: {
      Accept: "application/vnd.github+json"
    }
  });
  if (!response.ok) {
    throw new Error(`GitHub API ${response.status}`);
  }
  return response.json();
}

function applyIssues(issues) {
  state.issueByTitle = new Map(
    issues
      .filter((issue) => !issue.pull_request)
      .map((issue) => [issue.title.toLowerCase(), issue])
  );
}

function initTheme() {
  const stored = localStorage.getItem("theme");
  const preferredLight = window.matchMedia("(prefers-color-scheme: light)").matches;
  const theme = stored || (preferredLight ? "light" : "dark");
  document.documentElement.dataset.theme = theme;
  qs("[data-theme-toggle]").textContent = theme === "light" ? "☾" : "☼";

  qs("[data-theme-toggle]").addEventListener("click", () => {
    const next = document.documentElement.dataset.theme === "light" ? "dark" : "light";
    document.documentElement.dataset.theme = next;
    localStorage.setItem("theme", next);
    qs("[data-theme-toggle]").textContent = next === "light" ? "☾" : "☼";
  });
}

async function init() {
  initTheme();
  const response = await fetch(DATA_URL);
  state.data = await response.json();
  renderTested(state.data.tested);
  renderStats();
  renderWishlist();

  qs("[data-search]").addEventListener("input", (event) => {
    state.search = event.target.value;
    renderWishlist();
  });

  try {
    const issues = await fetchIssues(state.data.meta);
    applyIssues(issues);
    renderStats();
    renderWishlist();
    qs("[data-api-state]").textContent = `Live GitHub feed: ${issues.length} wishlist issues loaded.`;
  } catch (error) {
    qs("[data-api-state]").textContent = `Live GitHub feed unavailable (${error.message}); vote links still open the issue search.`;
  }
}

init();
