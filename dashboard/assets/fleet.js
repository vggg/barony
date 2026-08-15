/* fleet.js — the one data layer all three dashboard versions share.
 *
 * DRY: the three versions differ ONLY in presentation. Every number, label and
 * honesty caveat is derived here once, so a metric cannot say one thing on v1
 * and another on v3. Versions import `loadFleet()` and render the result.
 *
 * No framework, no build step, no server: this fetches the committed snapshot
 * at dashboard/data/fleet.json produced by dashboard/build-data.sh.
 */

/** Resolve data/fleet.json relative to the site root, from any version path. */
function dataURL() {
  // /v1/ , /v2/ , /v3/ and / all resolve to the same shared snapshot.
  const path = location.pathname;
  const depth = /\/v[123]\/?$|\/v[123]\/index\.html$/.test(path) ? '../' : './';
  return depth + 'data/fleet.json';
}

export async function loadFleet() {
  const res = await fetch(dataURL(), { cache: 'no-cache' });
  if (!res.ok) throw new Error(`could not load snapshot (${res.status})`);
  return decorate(await res.json());
}

/* ---------------------------------------------------------------- helpers */

export const fmt = {
  /** A metric with no observations renders as n/a — never as 0% or 100%. */
  metric(m) {
    if (!m.measured || m.value === null || m.value === undefined) return 'n/a';
    if (m.unit === 'ratio') return `${Math.round(m.value * 100)}%`;
    return String(m.value);
  },
  int(n) {
    return new Intl.NumberFormat('en').format(n ?? 0);
  },
  /** "3d ago" / "today" */
  age(days) {
    if (days === null || days === undefined) return '—';
    return days === 0 ? 'today' : `${days}d ago`;
  },
  when(iso) {
    if (!iso) return '—';
    const d = new Date(iso);
    return d.toLocaleString('en-GB', {
      day: '2-digit', month: 'short', year: 'numeric',
      hour: '2-digit', minute: '2-digit', timeZone: 'UTC',
    }) + ' UTC';
  },
  title(s) {
    return (s || '').replace(/[-_]/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
  },
};

/** Map a domain concept to a semantic status token the CSS understands. */
export function tone(kind, value) {
  switch (kind) {
    case 'project':
      return value === 'red' ? 'bad' : value === 'warn' ? 'warn' : 'good';
    case 'severity':
      return value === 'red' || value === 'bad' ? 'bad' : value === 'warn' ? 'warn' : 'good';
    case 'checks':
      return value === 'passing' ? 'good' : value === 'failing' ? 'bad' : 'warn';
    case 'mergeable':
      return value === 'MERGEABLE' ? 'good' : value === 'CONFLICTING' ? 'bad' : 'warn';
    default:
      return 'muted';
  }
}

/* Derived views, computed once so all three versions agree. */
function decorate(d) {
  const q = d.merge_queue || [];

  d.derived = {
    // Headline KPI row — identical across versions.
    kpis: [
      { key: 'projects', label: 'Projects',    value: d.kpis.projects,  tone: 'accent' },
      { key: 'agents',   label: 'Agents',      value: d.kpis.agents,    tone: 'accent' },
      { key: 'open_prs', label: 'Open PRs',    value: d.kpis.open_prs,  tone: q.some((p) => p.checks === 'failing') ? 'bad' : 'good' },
      { key: 'red',      label: 'Red findings',value: d.kpis.red_findings, tone: d.kpis.red_findings ? 'bad' : 'good' },
      { key: 'stalls',   label: 'Stalls',      value: d.kpis.stalls,    tone: d.kpis.stalls ? 'warn' : 'good' },
      { key: 'verdicts', label: 'Verdicts',    value: d.kpis.verdicts,  tone: d.kpis.verdicts > 1 ? 'good' : 'warn' },
    ],

    // The AI-summary surface: assembled from the snapshot, not invented.
    observerSummary: buildSummary(d),

    // Sparkline-able series for the ops-wall version. Where there is no real
    // series (one verdict is not a trend) the series is flagged sparse so the
    // UI can say so instead of drawing a confident line.
    series: buildSeries(d),

    greenPRs: q.filter((p) => p.checks === 'passing' && p.mergeable === 'MERGEABLE' && !p.draft).length,
    conflicted: q.filter((p) => p.mergeable === 'CONFLICTING').length,
    unmeasured: (d.health.metrics || []).filter((m) => !m.measured).length,
  };

  return d;
}

function buildSummary(d) {
  const lines = [];
  const k = d.kpis;
  const green = (d.merge_queue || []).filter(
    (p) => p.checks === 'passing' && p.mergeable === 'MERGEABLE' && !p.draft
  ).length;

  lines.push({
    tone: green ? 'action' : 'good',
    text: green
      ? `${green} of ${k.open_prs} open PRs are green and mergeable — the queue is waiting on the merge gate, not on CI.`
      : `${k.open_prs} open PRs; none currently green and mergeable.`,
  });

  if (k.stalls) {
    lines.push({
      tone: 'warn',
      text: `${k.stalls} stall findings: unmerged local branches and working copies behind origin/main. Branch churn is the dominant risk on this board.`,
    });
  }

  if (!d.health.coverage.measured) {
    lines.push({ tone: 'warn', text: d.health.coverage.note });
  }

  lines.push({
    tone: k.verdicts > 1 ? 'good' : 'warn',
    text:
      k.verdicts === 1
        ? 'Reviewer-quality metrics rest on a single recorded verdict (n=1). Treat mutation-kill and escape figures as unestablished, not as passing.'
        : `${k.verdicts} recorded verdicts back the reviewer-quality metrics.`,
  });

  if (!d.observer.active) {
    lines.push({ tone: 'muted', text: d.observer.note });
  }

  return lines;
}

function buildSeries(d) {
  // Real, per-project distributions — honest bars rather than invented history.
  const byProject = (d.health.projects || []).map((p) => ({
    label: p.name,
    stalls: p.stalls,
    verdicts: p.verdicts,
  }));

  const queueAges = (d.merge_queue || []).map((p) => p.age_days ?? 0);

  return {
    stallsByProject: { points: byProject.map((p) => p.stalls), labels: byProject.map((p) => p.label), sparse: false },
    queueAge: { points: queueAges, labels: (d.merge_queue || []).map((p) => `#${p.number}`), sparse: queueAges.length < 3 },
    verdicts: {
      points: byProject.map((p) => p.verdicts),
      labels: byProject.map((p) => p.label),
      sparse: true,
      note: 'Per-project verdicts read 0 — the plane is shared at the root (see coverage).',
    },
  };
}

/* Tiny DOM helper — enough to avoid a framework, small enough to read. */
export function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    if (k === 'class') node.className = v;
    else if (k === 'html') node.innerHTML = v;
    else if (k.startsWith('on')) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v);
  }
  for (const c of children.flat()) {
    if (c === null || c === undefined || c === false) continue;
    node.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return node;
}

/** Render a failure honestly rather than leaving an empty page. */
export function renderError(mount, err) {
  mount.innerHTML = '';
  mount.append(
    el('div', { class: 'load-error' },
      el('strong', {}, 'Could not load the fleet snapshot.'),
      el('p', {}, String(err.message || err)),
      el('p', {}, 'Serve this directory over HTTP — opening the file directly blocks fetch(). Try: python3 -m http.server -d dashboard 8080')
    )
  );
}

/** Minimal inline sparkline/bar SVG for the ops-wall version. */
export function sparkline(points, { width = 120, height = 28, kind = 'bar' } = {}) {
  const ns = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(ns, 'svg');
  svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
  svg.setAttribute('class', 'spark');
  svg.setAttribute('preserveAspectRatio', 'none');
  svg.setAttribute('role', 'img');

  const max = Math.max(1, ...points);
  if (kind === 'bar') {
    const gap = 2;
    const w = points.length ? (width - gap * (points.length - 1)) / points.length : width;
    points.forEach((p, i) => {
      const h = Math.max(1, (p / max) * (height - 2));
      const r = document.createElementNS(ns, 'rect');
      r.setAttribute('x', i * (w + gap));
      r.setAttribute('y', height - h);
      r.setAttribute('width', Math.max(1, w));
      r.setAttribute('height', h);
      r.setAttribute('class', 'spark-bar');
      svg.append(r);
    });
  } else {
    const step = points.length > 1 ? width / (points.length - 1) : width;
    const dPath = points
      .map((p, i) => `${i ? 'L' : 'M'}${i * step},${height - (p / max) * (height - 2)}`)
      .join(' ');
    const path = document.createElementNS(ns, 'path');
    path.setAttribute('d', dPath);
    path.setAttribute('class', 'spark-line');
    svg.append(path);
  }
  return svg;
}
