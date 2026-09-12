/* ==========================================================================
   app.js — ALL the behavior for the EagleGIS site (index.html)
   ==========================================================================

   Accessibility Fixes Applied:
   - Added role="button" and tabindex="0" to interactive cards (Meetings, News, Upcoming).
   - Added keyboard support (Enter/Space) for opening and closing detail panels.
   - Improved focus management when opening details.
   - Added ARIA attributes for expanded states.
   ========================================================================== */

/* ──────────────────────────────────────────────────────────────────────────
   1. SETTINGS
   ────────────────────────────────────────────────────────────────────────── */

const GITHUB_BASE = 'https://raw.githubusercontent.com/EagleGIS-FGCU/EagleGIS/main/';
const MANIFEST_URL = GITHUB_BASE + 'app/data/gold/site_manifest.json';
const ARCGIS_CSV_URL = GITHUB_BASE + 'app/data/gold/arcgis_agenda_map_data.csv';
const DATA_CACHE_TTL_MS = 24 * 60 * 60 * 1000;

let siteManifest = null;

const TYPES = {
    "Regular Council Meeting":                    {color:"#0052a5",bg:"#eff6ff",bd:"#93c5fd",short:"Regular Council",icon:"fa-gavel"},
    "Council Workshop":                           {color:"#c2410c",bg:"#fff7ed",bd:"#fdba74",short:"Workshop",icon:"fa-screwdriver-wrench"},
    "Special Called Meeting":                     {color:"#b91c1c",bg:"#fef2f2",bd:"#fca5a5",short:"Special Called",icon:"fa-bullhorn"},
    "Joint Meeting":                              {color:"#15803d",bg:"#f0fdf4",bd:"#86efac",short:"Joint",icon:"fa-handshake"},
    "Public Hearing":                             {color:"#6d28d9",bg:"#f5f3ff",bd:"#c4b5fd",short:"Public Hearing",icon:"fa-scale-balanced"},
    "Quasi-judicial Hearing":                     {color:"#4338ca",bg:"#eef2ff",bd:"#a5b4fc",short:"Quasi-judicial",icon:"fa-scale-balanced"},
    "Goal-setting / Strategic Planning Session":  {color:"#0f766e",bg:"#f0fdfa",bd:"#5eead4",short:"Strategic",icon:"fa-bullseye"},
    "PZDB Meeting":                               {color:"#374151",bg:"#f9fafb",bd:"#d1d5db",short:"PZDB",icon:"fa-building-columns"},
    "PZDB Public Information Meeting":            {color:"#0369a1",bg:"#f0f9ff",bd:"#7dd3fc",short:"PZDB Info",icon:"fa-circle-info"},
    "PZDB Public Hearing":                        {color:"#7e22ce",bg:"#faf5ff",bd:"#d8b4fe",short:"PZDB Hearing",icon:"fa-scale-balanced"},
    "PZDB Workshop":                              {color:"#854d0e",bg:"#fefce8",bd:"#fde68a",short:"PZDB Wkshp",icon:"fa-screwdriver-wrench"},
};
const FALLBACK_TYPE = {color:"#0052a5",bg:"#eff6ff",bd:"#93c5fd",short:"Other",icon:"fa-file"};
const t = type => TYPES[type] || FALLBACK_TYPE;

const LAND_USE = {
    residential:    {color:"#15803d",bg:"#f0fdf4",bd:"#86efac",short:"Residential",icon:"fa-house"},
    commercial:     {color:"#c2410c",bg:"#fff7ed",bd:"#fdba74",short:"Commercial",icon:"fa-store"},
    mixed_use:      {color:"#7c3aed",bg:"#f5f3ff",bd:"#c4b5fd",short:"Mixed Use",icon:"fa-city"},
    industrial:     {color:"#57534e",bg:"#fafaf9",bd:"#d6d3d1",short:"Industrial",icon:"fa-industry"},
    institutional:  {color:"#0369a1",bg:"#f0f9ff",bd:"#7dd3fc",short:"Institutional",icon:"fa-school"},
    infrastructure: {color:"#b45309",bg:"#fffbeb",bd:"#fcd34d",short:"Infrastructure",icon:"fa-road"},
    open_space:     {color:"#047857",bg:"#ecfdf5",bd:"#6ee7b7",short:"Open Space",icon:"fa-tree"},
    administrative: {color:"#64748b",bg:"#f8fafc",bd:"#cbd5e1",short:"Administrative",icon:"fa-clipboard"},
    other:          {color:"#6b7280",bg:"#f9fafb",bd:"#d1d5db",short:"Other",icon:"fa-tag"},
};
const lu = cat => LAND_USE[cat] || LAND_USE.other;

function mapArcgisMeetingType(meetingType, board) {
    if ((board || '').includes('Planning')) return 'PZDB Meeting';
    const map = {
        'Village Council': 'Regular Council Meeting',
        'Planning Zoning & Design Board': 'PZDB Meeting',
        'Public Hearing': 'Public Hearing',
        'Workshop': 'Council Workshop',
    };
    return map[meetingType] || meetingType || 'Other';
}

/** Normalize ArcGIS gold row into fields the UI expects. */
function normalizeArcgisRow(row) {
    const meetingType = mapArcgisMeetingType(row.MeetingType, row.Board);
    return {
        ...row,
        Title: row.ProjectTitle || row.ProjectName || '',
        MinutesURL: row.Document_Link || '',
        LocationName: row.Location || row.LocationName || '',
        MeetingType: meetingType,
        LandUseCategory: (row.LandUseCategory || 'other').trim() || 'other',
    };
}

function scheduleIdle(fn, timeoutMs = 2000) {
    if ('requestIdleCallback' in window) requestIdleCallback(fn, { timeout: timeoutMs });
    else setTimeout(fn, 100);
}

function loadDeferredMap() {
    const iframe = document.getElementById('map-iframe');
    if (!iframe || iframe.dataset.loaded || !iframe.dataset.src) return;
    iframe.src = iframe.dataset.src;
    iframe.dataset.loaded = '1';
}

const MEETINGS_PAGE_SIZE = 50;
let meetingsDisplayLimit = MEETINGS_PAGE_SIZE;
let _meetingsScrollObserver = null;

function versionedUrl(path, sha256) {
    // If path is already a full URL, don't prepend GITHUB_BASE
    const fullPath = (path.startsWith('http')) ? path : GITHUB_BASE + path;
    const v = sha256 ? String(sha256).slice(0, 12) : String(Date.now());
    return `${fullPath}?v=${v}`;
}

function readDataCache(key) {
    try {
        const raw = localStorage.getItem(key);
        if (!raw) return null;
        const { ts, data } = JSON.parse(raw);
        if (Date.now() - ts > DATA_CACHE_TTL_MS) return null;
        return data;
    } catch (e) { return null; }
}

function writeDataCache(key, data) {
    try {
        localStorage.setItem(key, JSON.stringify({ ts: Date.now(), data }));
    } catch (e) { /* quota exceeded */ }
}

async function fetchJson(url) {
    const res = await fetch(url);
    if (!res.ok) throw new Error('HTTP ' + res.status);
    return res.json();
}

function compareMeetingRows(a, b) {
    const byDate = (b.MeetingDate || '').localeCompare(a.MeetingDate || '');
    if (byDate !== 0) return byDate;
    const byItem = String(a.AgendaItemNumber || '').localeCompare(String(b.AgendaItemNumber || ''), undefined, { numeric: true });
    if (byItem !== 0) return byItem;
    return (a.ProjectTitle || a.ProjectName || '').localeCompare(b.ProjectTitle || b.ProjectName || '');
}

async function loadSiteManifest() {
    siteManifest = await fetchJson(MANIFEST_URL);
    return siteManifest;
}

async function loadArcgisRecords(manifest) {
    const meta = manifest.arcgis || {};
    const sha = meta.sha256 || '';
    const cacheKey = `eaglegis:arcgis:v2:${sha}`;
    const cached = readDataCache(cacheKey);
    if (cached) return cached;

    const csvPath = meta.csv || 'app/data/gold/arcgis_agenda_map_data.csv';
    return new Promise((resolve, reject) => {
        if (typeof Papa === 'undefined') {
            reject(new Error('PapaParse unavailable'));
            return;
        }
        Papa.parse(versionedUrl(csvPath, sha), {
            download: true, header: true, skipEmptyLines: true,
            complete: ({ data }) => {
                const rows = data.map(normalizeArcgisRow).sort(compareMeetingRows);
                writeDataCache(cacheKey, rows);
                resolve(rows);
            },
            error: reject,
        });
    });
}

function onMeetingsLoaded(data) {
    allData = data;
    populateYears();
    buildTypeFilters();
    buildLandUseFilters();
    run();
    setupSearch();
    setupFilters();
    setupLandUseFilters();
    setupFinalizedFilters();
    setupControls();
    setupBackTop();
    setupRecordListDelegation();
    setupMeetingsInfiniteScroll();
    scheduleIdle(() => buildMeetingSearchIndex());
    scheduleIdle(() => loadMinutesIndex(), 3000);
    scheduleIdle(loadDeferredMap, 1500);
}

/* ──────────────────────────────────────────────────────────────────────────
   2. MEETINGS TAB
   ────────────────────────────────────────────────────────────────────────── */

let meetingSearch = null;
let allData=[], active=new Set(['all']), landUseActive=new Set(['all']), activeFinalized=new Set(['all']), sortMode='newest', yearFilter='all', current=[];

const CIVIC_LINKS = {
    engageContact: 'https://esterotoday.com/contact/',
    villageEComment: 'https://estero-fl.gov/ecomment-cards/',
};

function meetingFinalizedState(row) {
    const raw = (row.Finalized || '').trim();
    if (raw === 'Yes' || raw === 'No' || raw === 'Cancelled') return raw;
    const st = (row.Status || '').toLowerCase();
    if (st === 'cancelled') return 'Cancelled';
    return (row.MinutesURL || '').trim() ? 'Yes' : 'No';
}

function updateCivicNotice(data) {
    const el = document.getElementById('pzdb-civic-notice');
    if (!el) return;
    const inMeetings = (typeof currentView === 'undefined') || currentView === 'meetings';
    el.hidden = !(inMeetings && data.some(r => (r.InProgress || '').trim() === 'Yes'));
}

const fmtDate = d => {
    if (!d) return '—';
    const dt = new Date(d+'T00:00:00');
    return isNaN(dt) ? d : dt.toLocaleDateString('en-US',{year:'numeric',month:'long',day:'numeric'});
};
const sCls = s => {
    if (!s) return '';
    const l=s.toLowerCase();
    return l==='accepted'?'s-accepted':l==='pending'?'s-pending':l==='cancelled'?'s-cancelled':'';
};
const noAct = t => !t||['No action found','Meeting Cancelled','No action extracted - verify PDF'].includes(t);

function highlight(text, termRaw) {
    if (!termRaw || !text) return text;
    const parts = String(termRaw).toLowerCase().trim().split(/\s+/).filter(Boolean);
    if (!parts.length) return text;
    const escaped = parts.map(p => p.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
    const re = new RegExp('(' + escaped.join('|') + ')', 'gi');
    return String(text).replace(re, '<span class="hl">$1</span>');
}

function showSkeleton() {
    document.getElementById('data-list').innerHTML = Array(5).fill('').map(()=>`
        <div class="skeleton-card">
            <div style="display:flex;justify-content:space-between;margin-bottom:8px;">
                <div class="skel-line" style="height:20px;width:30%;border-radius:5px;"></div>
                <div class="skel-line" style="height:14px;width:20%;border-radius:4px;"></div>
            </div>
            <div class="skel-line" style="height:12px;width:95%;"></div>
            <div class="skel-line" style="height:12px;width:75%;margin-bottom:10px;"></div>
            <div style="display:flex;justify-content:space-between;">
                <div class="skel-line" style="height:12px;width:40%;"></div>
                <div class="skel-line" style="height:24px;width:25%;border-radius:5px;"></div>
            </div>
        </div>`).join('');
}

async function init() {
    showSkeleton();
    try {
        const manifest = await loadSiteManifest();
        const data = await loadArcgisRecords(manifest);
        onMeetingsLoaded(data);
    } catch (err) {
        console.warn('Manifest/ArcGIS load failed; falling back to CSV:', err);
        if (typeof Papa === 'undefined') {
            document.getElementById('data-list').innerHTML =
                `<div class="empty"><i class="fa-solid fa-triangle-exclamation" style="color:#ef4444;"></i><p style="color:#ef4444;">Could not load data.<br>Agenda records failed to load.</p></div>`;
            return;
        }
        Papa.parse(ARCGIS_CSV_URL, {
            download: true, header: true, skipEmptyLines: true,
            complete: ({ data }) => onMeetingsLoaded(data.map(normalizeArcgisRow).sort(compareMeetingRows)),
            error: () => {
                document.getElementById('data-list').innerHTML =
                    `<div class="empty"><i class="fa-solid fa-triangle-exclamation" style="color:#ef4444;"></i><p style="color:#ef4444;">Could not load data.<br>The ArcGIS gold file failed to load.</p></div>`;
            },
        });
    }
}

function buildMeetingSearchIndex() {
    meetingSearch = null;
    if (typeof MiniSearch === 'undefined' || !allData.length) return;
    try {
        const ms = new MiniSearch({
            idField: 'id',
            fields: [
                'projectName', 'projectTitle', 'meetingType', 'meetingDate', 'meetingYear', 'status',
                'actionTaken', 'summary', 'staffCode', 'title', 'minutesUrl',
                'locationName', 'landUse', 'agendaItemType', 'coordinates',
            ],
        });
        const docs = allData.map((row, i) => ({
            id: String(i),
            projectName: row.ProjectName || '',
            projectTitle: row.ProjectTitle || '',
            meetingType: row.MeetingType || '',
            meetingDate: row.MeetingDate || '',
            meetingYear: row.MeetingYear || '',
            status: row.Status || '',
            actionTaken: row.ActionTaken || '',
            summary: row.Summary || '',
            staffCode: row.StaffCode || '',
            title: row.Title || '',
            minutesUrl: row.MinutesURL || '',
            locationName: row.LocationName || '',
            landUse: row.LandUseCategory || '',
            agendaItemType: row.AgendaItemType || '',
            coordinates: [row.Latitude, row.Longitude].filter(Boolean).join(' '),
        }));
        ms.addAll(docs);
        meetingSearch = ms;
    } catch (e) {
        console.warn('Meeting search index failed:', e);
        meetingSearch = null;
    }
}

function populateYears() {
    const years = [...new Set(allData.map(r=>r.MeetingYear).filter(Boolean))].sort((a,b)=>b-a);
    const sel = document.getElementById('year-filter');
    years.forEach(y => {
        const opt = document.createElement('option');
        opt.value = y; opt.textContent = y;
        sel.appendChild(opt);
    });
}

function buildTypeFilters() {
    const counts = new Map();
    allData.forEach(r => {
        const k = (r.MeetingType || '').trim() || 'Other';
        counts.set(k, (counts.get(k) || 0) + 1);
    });
    const ordered = [...counts.entries()].sort((a,b) => b[1]-a[1]);
    const row = document.getElementById('filter-row');

    const allBtn = row.querySelector('[data-type="all"]');
    if (allBtn) {
        const existing = allBtn.querySelector('.chip-count');
        const html = `<span class="chip-count">${allData.length}</span>`;
        if (existing) existing.outerHTML = html; else allBtn.insertAdjacentHTML('beforeend', html);
    }

    ordered.forEach(([type, n]) => {
        const meta = t(type);
        const btn = document.createElement('button');
        btn.className = 'filter-btn';
        btn.dataset.type = type;
        btn.style.cssText = `background:${meta.bg};color:${meta.color};border-color:${meta.bd};`;
        btn.innerHTML = `<i class="fa-solid ${meta.icon}" aria-hidden="true"></i> ${meta.short}<span class="chip-count">${n}</span>`;
        row.appendChild(btn);
    });
}

function buildLandUseFilters() {
    const row = document.getElementById('landuse-filter-row');
    if (!row) return;
    row.querySelectorAll('[data-landuse]:not([data-landuse="all"])').forEach(el => el.remove());

    const counts = new Map();
    allData.forEach(r => {
        const k = r.LandUseCategory || 'other';
        counts.set(k, (counts.get(k) || 0) + 1);
    });
    const ordered = [...counts.entries()].sort((a, b) => b[1] - a[1]);

    const allBtn = row.querySelector('[data-landuse="all"]');
    if (allBtn) {
        const html = `<span class="chip-count">${allData.length}</span>`;
        const existing = allBtn.querySelector('.chip-count');
        if (existing) existing.outerHTML = html; else allBtn.insertAdjacentHTML('beforeend', html);
    }

    ordered.forEach(([cat, n]) => {
        const meta = lu(cat);
        const btn = document.createElement('button');
        btn.className = 'filter-btn inactive';
        btn.dataset.landuse = cat;
        btn.style.cssText = `background:${meta.bg};color:${meta.color};border-color:${meta.bd};`;
        btn.innerHTML = `<i class="fa-solid ${meta.icon}" aria-hidden="true"></i> ${meta.short}<span class="chip-count">${n}</span>`;
        row.appendChild(btn);
    });
}

function compareRowsBySortMode(a, b) {
    if (sortMode === 'newest') return new Date(b.MeetingDate) - new Date(a.MeetingDate);
    if (sortMode === 'oldest') return new Date(a.MeetingDate) - new Date(b.MeetingDate);
    const typeCmp = (a.MeetingType || '').localeCompare(b.MeetingType || '');
    if (typeCmp !== 0) return typeCmp;
    return new Date(b.MeetingDate) - new Date(a.MeetingDate);
}

function run() {
    if (typeof currentView !== 'undefined') {
        if (currentView === 'news') {
            updateCivicNotice([]);
            if (typeof renderNews === 'function') renderNews();
            return;
        }
        if (currentView === 'upcoming') {
            updateCivicNotice([]);
            if (typeof renderUpcoming === 'function') renderUpcoming();
            return;
        }
    }
    const qRaw = document.getElementById('main-search').value.trim();
    const q = qRaw.toLowerCase();
    const useIndex = !!q && meetingSearch;

    const scores = new Map();
    let idSet = null;
    if (useIndex) {
        const hits = meetingSearch.search(qRaw, {
            prefix: true, fuzzy: 0.2, combineWith: 'AND',
            boost: { title: 1.7, actionTaken: 1.45, projectName: 1.25, meetingType: 1.15, locationName: 1.1, minutesUrl: 1.05 },
        });
        idSet = new Set(hits.map(h => parseInt(h.id, 10)));
        hits.forEach(h => scores.set(parseInt(h.id, 10), h.score));
    }

    let rows = allData.map((r, idx) => ({ r, idx })).filter(({ r, idx }) => {
        const matchesType = active.has('all') || active.has((r.MeetingType || '').trim() || 'Other');
        const matchesLandUse = landUseActive.has('all') || landUseActive.has(r.LandUseCategory || 'other');
        const matchesFinalized = activeFinalized.has('all') || activeFinalized.has(meetingFinalizedState(r).toLowerCase());
        const matchesYear = yearFilter === 'all' || r.MeetingYear === yearFilter;
        let matchesText = true;
        if (q) {
            if (useIndex && idSet) {
                matchesText = idSet.has(idx);
            } else {
                matchesText =
                    (r.ActionTaken || '').toLowerCase().includes(q) ||
                    (r.Summary || '').toLowerCase().includes(q) ||
                    (r.MeetingDate || '').toLowerCase().includes(q) ||
                    (r.MeetingType || '').toLowerCase().includes(q) ||
                    (r.ProjectName || '').toLowerCase().includes(q) ||
                    (r.ProjectTitle || '').toLowerCase().includes(q) ||
                    (r.LocationName || '').toLowerCase().includes(q) ||
                    (r.StaffCode || '').toLowerCase().includes(q) ||
                    (r.Title || '').toLowerCase().includes(q) ||
                    (r.Status || '').toLowerCase().includes(q) ||
                    (r.LandUseCategory || '').toLowerCase().includes(q) ||
                    (r.MinutesURL || '').toLowerCase().includes(q);
            }
        }
        return matchesType && matchesLandUse && matchesFinalized && matchesYear && matchesText;
    });

    if (useIndex && scores.size) {
        rows.sort((a, b) => {
            const sb = scores.get(b.idx) ?? 0;
            const sa = scores.get(a.idx) ?? 0;
            if (sb !== sa) return sb - sa;
            return compareRowsBySortMode(a.r, b.r);
        });
    } else {
        rows.sort((a, b) => compareRowsBySortMode(a.r, b.r));
    }

    current = rows.map(x => x.r);
    meetingsDisplayLimit = MEETINGS_PAGE_SIZE;
    stats(current);
    render(current);
    updateCivicNotice(current);
}

function stats(d) {
    document.getElementById('s-count').textContent = d.length;
    document.getElementById('s-years').textContent = new Set(d.map(r=>r.MeetingYear).filter(Boolean)).size||'—';
    document.getElementById('s-types').textContent = new Set(d.map(r=>r.LandUseCategory).filter(Boolean)).size||'—';
    const pdfCount = d.filter(r => r.MinutesURL || resolveMinutesPdf(r.MeetingType, r.MeetingDate)).length;
    document.getElementById('s-pdfs').textContent  = pdfCount;
    const badge = document.getElementById('tab-count-meetings');
    if (badge) badge.textContent = d.length;
}

function renderCard(row, i) {
    const {color,bg,bd,short,icon}=t(row.MeetingType);
    const landMeta = lu(row.LandUseCategory || 'other');
    const rawAction = noAct(row.ActionTaken) ? (row.Summary || null) : row.ActionTaken;
    const qForHl = document.getElementById('main-search').value.trim();
    const displayAction = rawAction
        ? highlight(rawAction.length>130?rawAction.slice(0,130)+'...':rawAction, qForHl)
        : `<span style="font-style:italic;color:#9ca3af;">View PDF for full item details.</span>`;
    const pdfUrl = row.MinutesURL || resolveMinutesPdf(row.MeetingType, row.MeetingDate);
    const fromManifest = !row.MinutesURL && pdfUrl;
    const cancelled = (row.Status || '').toLowerCase() === 'cancelled';
    const itemLabel = row.AgendaItemNumber ? `Item ${row.AgendaItemNumber}` : 'Agenda item';

    const finState = meetingFinalizedState(row);
    const finMeta = cancelled ? null : ({
        Yes: { cls: 'f-yes', icon: 'fa-circle-check', label: 'Minutes posted' },
        No: { cls: 'f-no', icon: 'fa-clock', label: 'Awaiting minutes' },
    })[finState];
    const finChip = finMeta
        ? `<span class="finalized-chip ${finMeta.cls}" title="${finMeta.label}"><i class="fa-solid ${finMeta.icon}" aria-hidden="true"></i>${finMeta.label}</span>`
        : '';
    const inProgress = (row.InProgress || '').trim() === 'Yes';
    const progNote = (row.InProgressNote || '').replace(/"/g, '&quot;');
    const progChip = inProgress
        ? `<span class="progress-chip" title="${progNote}"><i class="fa-solid fa-hard-hat" aria-hidden="true"></i>In progress</span>`
        : '';

    return `
    <div class="record-card${cancelled ? ' record-cancelled' : ''}" data-idx="${i}" role="button" tabindex="0" aria-label="${itemLabel} on ${row.MeetingDate}: ${short}">
        <div class="card-top">
            <span class="project-pill" style="background:${bg};color:${color};border-color:${bd};" title="${row.MeetingType||''}">
                <i class="fa-solid ${icon}" aria-hidden="true"></i>${short}
            </span>
            ${cancelled ? `<span class="status-chip s-cancelled">Cancelled</span>` : ''}
            ${finChip}${progChip}
            <span class="project-pill" style="background:${landMeta.bg};color:${landMeta.color};border-color:${landMeta.bd};font-size:10px;" title="Land use">
                <i class="fa-solid ${landMeta.icon}" aria-hidden="true"></i>${landMeta.short}
            </span>
            <span class="card-date">${highlight(row.MeetingDate||'—', qForHl)}</span>
        </div>
        <div class="card-title" style="font-size:12px;font-weight:600;color:#374151;margin-bottom:4px;">${highlight(row.Title || row.ProjectName || itemLabel, qForHl)}</div>
        <div class="card-action">${displayAction}</div>
        <div class="card-footer">
            <span class="card-loc"><i class="fa-solid fa-location-dot" style="color:${color};font-size:10px;" aria-hidden="true"></i>${highlight(row.LocationName||'—', qForHl)}</span>
            <div class="card-btns">
                <button class="btn-sm btn-outline detail-btn" data-idx="${i}" tabindex="-1">
                    <i class="fa-solid fa-circle-info" aria-hidden="true"></i>Details
                </button>
                ${pdfUrl
                    ?`<a class="btn-sm btn-solid" href="${pdfUrl}" target="_blank" rel="noopener" style="background:${color};" title="${fromManifest ? 'Canonical estero-fl.gov copy' : 'Mirror copy'}" aria-label="View PDF for ${row.MeetingDate}">
                        <i class="fa-solid fa-file-pdf" aria-hidden="true"></i>PDF${fromManifest ? '<sup style="font-size:7px;opacity:0.85;margin-left:2px;">VOE</sup>' : ''}
                      </a>`
                    :''}
            </div>
        </div>
    </div>`;
}

function render(data) {
    const list = document.getElementById('data-list');
    if (!data.length) {
        list.innerHTML=`<div class="empty"><i class="fa-solid fa-magnifying-glass" aria-hidden="true"></i><p>No matching records found.<br>Try adjusting your filters.</p></div>`;
        return;
    }

    const visible = data.slice(0, meetingsDisplayLimit);
    const hasMore = data.length > meetingsDisplayLimit;

    if (sortMode === 'type') {
        let html = '';
        let lastType = null;
        const groupCounts = data.reduce((acc, r) => {
            const k = r.MeetingType || 'Other';
            acc[k] = (acc[k] || 0) + 1;
            return acc;
        }, {});
        visible.forEach((row, i) => {
            const type = row.MeetingType || 'Other';
            if (type !== lastType) {
                const meta = t(type);
                html += `
                <div class="group-header" style="color:${meta.color};" role="presentation">
                    <i class="fa-solid ${meta.icon}" aria-hidden="true"></i>${type}
                    <span class="gh-count">${groupCounts[type]}</span>
                </div>`;
                lastType = type;
            }
            html += renderCard(row, i);
        });
        list.innerHTML = html + (hasMore ? meetingsScrollSentinelHtml() : '');
    } else {
        list.innerHTML = visible.map(renderCard).join('') + (hasMore ? meetingsScrollSentinelHtml() : '');
    }

    observeMeetingsSentinel();
}

function meetingsScrollSentinelHtml() {
    return `<div class="meetings-scroll-sentinel" aria-hidden="true"></div>`;
}

function setupMeetingsInfiniteScroll() {
    const list = document.getElementById('data-list');
    if (!list || _meetingsScrollObserver) return;
    _meetingsScrollObserver = new IntersectionObserver(entries => {
        if (!entries.some(e => e.isIntersecting)) return;
        if (currentView !== 'meetings' || meetingsDisplayLimit >= current.length) return;
        meetingsDisplayLimit += MEETINGS_PAGE_SIZE;
        render(current);
    }, { root: list, rootMargin: '160px' });
}

function observeMeetingsSentinel() {
    if (!_meetingsScrollObserver) return;
    const list = document.getElementById('data-list');
    _meetingsScrollObserver.disconnect();
    const sentinel = list.querySelector('.meetings-scroll-sentinel');
    if (sentinel) _meetingsScrollObserver.observe(sentinel);
}

function setupRecordListDelegation() {
    const list = document.getElementById('data-list');
    list.addEventListener('click', e => {
        if (currentView !== 'meetings') return;
        const detailBtn = e.target.closest('.detail-btn');
        if (detailBtn) {
            e.stopPropagation();
            openDetail(parseInt(detailBtn.dataset.idx, 10));
            return;
        }
        if (e.target.closest('a')) return;
        const card = e.target.closest('.record-card');
        if (card) openDetail(parseInt(card.dataset.idx, 10));
    });

    // Accessibility: Keyboard support for cards
    list.addEventListener('keydown', e => {
        if (e.key === 'Enter' || e.key === ' ') {
            const card = e.target.closest('.record-card, .news-card, .upcoming-card');
            if (card) {
                e.preventDefault();
                card.click();
            }
        }
    });
}

function openDetail(idx) {
    const row = current[idx];
    if (!row) return;
    document.querySelectorAll('.record-card').forEach(c=>c.classList.remove('active'));
    const card = document.querySelector(`.record-card[data-idx="${idx}"]`);
    if (card) { card.classList.add('active'); card.scrollIntoView({behavior:'smooth',block:'nearest'}); }

    const {color,bg,bd,icon} = t(row.MeetingType);
    const landMeta = lu(row.LandUseCategory || 'other');
    const qForHl = document.getElementById('main-search').value.trim();
    const actions = noAct(row.ActionTaken)
        ? (row.Summary
            ? `<div class="action-item">${highlight(row.Summary, qForHl)}</div>`
            : `<div class="action-empty"><i class="fa-solid fa-circle-info" style="margin-right:5px;" aria-hidden="true"></i>No action text available — view the PDF for full details.</div>`)
        : row.ActionTaken.split(' | ').filter(Boolean).map(a=>`<div class="action-item">${highlight(a.trim(), qForHl)}</div>`).join('');

    document.getElementById('detail-content').innerHTML=`
        <div class="detail-banner" style="background:${bg};border-color:${bd};">
            <div class="detail-banner-name" style="color:${color};">
                <i class="fa-solid ${icon}" aria-hidden="true"></i>${row.MeetingType||'Meeting'}
            </div>
            ${row.Title
                ? `<div style="margin-top:6px;font-size:13px;font-weight:600;color:${color};">${highlight(row.Title, qForHl)}</div>`
                : ''}
            <div class="detail-banner-meta" style="color:${color};margin-top:4px;">${fmtDate(row.MeetingDate)} · Item ${row.AgendaItemNumber || '—'}</div>
        </div>

        <div class="detail-grid">
            <div class="detail-cell full">
                <div class="dcl"><i class="fa-solid fa-diagram-project" aria-hidden="true"></i>Project</div>
                <div class="dcv" style="font-weight:600;font-size:13px;">${row.ProjectName||'—'}</div>
            </div>
            <div class="detail-cell">
                <div class="dcl"><i class="fa-solid fa-circle-check" aria-hidden="true"></i>Status</div>
                <span class="status-chip ${sCls(row.Status)}">${row.Status||'—'}</span>
            </div>
            <div class="detail-cell">
                <div class="dcl"><i class="fa-solid fa-tag" aria-hidden="true"></i>Land Use</div>
                <span class="status-chip" style="background:${landMeta.bg};color:${landMeta.color};border:1px solid ${landMeta.bd};">${landMeta.short}</span>
            </div>
            <div class="detail-cell">
                <div class="dcl"><i class="fa-solid fa-list-ol" aria-hidden="true"></i>Item Type</div>
                <div class="dcv">${row.AgendaItemType||'—'}</div>
            </div>
            <div class="detail-cell">
                <div class="dcl"><i class="fa-solid fa-user" aria-hidden="true"></i>Staff Code</div>
                <div class="dcv" style="font-family:'IBM Plex Mono',monospace;font-size:12px;">${row.StaffCode||'—'}</div>
            </div>
            <div class="detail-cell full">
                <div class="dcl"><i class="fa-solid fa-location-dot" aria-hidden="true"></i>Location</div>
                <div class="dcv" style="font-weight:500;font-size:12px;">${row.LocationName||'—'}</div>
                ${(row.Latitude && row.Longitude)
                    ? `<div style="font-family:'IBM Plex Mono',monospace;font-size:10px;color:#9ca3af;margin-top:3px;">${row.Latitude}, ${row.Longitude}${row.GeocodeConfidence ? ` · conf ${row.GeocodeConfidence}` : ''}</div>`
                    : ''}
            </div>
            <div class="detail-cell">
                <div class="dcl"><i class="fa-regular fa-calendar" aria-hidden="true"></i>Meeting Year</div>
                <div class="dcv">${row.MeetingYear||'—'}</div>
            </div>
            <div class="detail-cell">
                <div class="dcl"><i class="fa-solid fa-building-columns" aria-hidden="true"></i>Board</div>
                <div class="dcv">${row.Board||'—'}</div>
            </div>
        </div>

        <div class="action-section">
            <div class="action-header"><i class="fa-solid fa-list-check" aria-hidden="true"></i>Action Taken</div>
            <div class="action-box">${actions}</div>
        </div>

        ${(() => {
            const pdf = row.MinutesURL || resolveMinutesPdf(row.MeetingType, row.MeetingDate);
            const fromManifest = !row.MinutesURL && pdf;
            if (!pdf) return `<div class="no-pdf"><i class="fa-solid fa-ban" style="margin-right:6px;color:#9ca3af;" aria-hidden="true"></i>No PDF available for this record</div>`;
            const label = fromManifest ? 'View Approved Minutes (estero-fl.gov)' : 'View Full Meeting Minutes PDF';
            return `<a class="pdf-btn" href="${pdf}" target="_blank" rel="noopener" style="background:${color};">
                        <i class="fa-solid fa-file-pdf" aria-hidden="true"></i>${label}
                    </a>`;
        })()}`;

    document.getElementById('detail-panel').classList.add('open');
    document.getElementById('map-spot').style.marginLeft='380px';
    
    // Accessibility: Manage focus
    document.getElementById('close-detail').focus();
}

document.getElementById('close-detail').addEventListener('click',()=>{
    document.getElementById('detail-panel').classList.remove('open');
    document.getElementById('map-spot').style.marginLeft='0';
    document.querySelectorAll('.record-card, .news-card, .upcoming-card').forEach(c=>c.classList.remove('active'));
});

// Accessibility: Keyboard support for closing detail panel
document.getElementById('close-detail').addEventListener('keydown', e => {
    if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        document.getElementById('close-detail').click();
    }
});

function setupSearch() {
    let timer = null;
    document.getElementById('main-search').addEventListener('input', () => {
        clearTimeout(timer);
        timer = setTimeout(() => run(), 150);
    });
}

function setupFilters() {
    document.getElementById('filter-row').addEventListener('click', ev => {
        const btn = ev.target.closest('.filter-btn');
        if (!btn) return;
        const type = btn.dataset.type;
        if (type === 'all') {
            active = new Set(['all']);
            document.querySelectorAll('.filter-btn').forEach(b=>{
                b.classList.remove('inactive');
                b.setAttribute('aria-pressed', 'true');
            });
        } else {
            active.delete('all');
            const allBtn = document.querySelector('[data-type="all"]');
            allBtn.classList.add('inactive');
            allBtn.setAttribute('aria-pressed', 'false');

            if (active.has(type)) { 
                active.delete(type); 
                btn.classList.add('inactive'); 
                btn.setAttribute('aria-pressed', 'false');
            } else { 
                active.add(type); 
                btn.classList.remove('inactive'); 
                btn.setAttribute('aria-pressed', 'true');
            }
            if (active.size === 0) {
                active = new Set(['all']);
                document.querySelectorAll('.filter-btn').forEach(b=>{
                    b.classList.remove('inactive');
                    b.setAttribute('aria-pressed', 'true');
                });
            }
        }
        run();
    });
}

function setupLandUseFilters() {
    const row = document.getElementById('landuse-filter-row');
    if (!row) return;
    row.addEventListener('click', ev => {
        const btn = ev.target.closest('.filter-btn');
        if (!btn) return;
        const cat = btn.dataset.landuse;
        if (cat === 'all') {
            landUseActive = new Set(['all']);
            row.querySelectorAll('.filter-btn').forEach(b => {
                b.classList.remove('inactive');
                b.setAttribute('aria-pressed', 'true');
            });
        } else {
            landUseActive.delete('all');
            const allBtn = row.querySelector('[data-landuse="all"]');
            if (allBtn) {
                allBtn.classList.add('inactive');
                allBtn.setAttribute('aria-pressed', 'false');
            }
            if (landUseActive.has(cat)) {
                landUseActive.delete(cat);
                btn.classList.add('inactive');
                btn.setAttribute('aria-pressed', 'false');
            } else {
                landUseActive.add(cat);
                btn.classList.remove('inactive');
                btn.setAttribute('aria-pressed', 'true');
            }
            if (landUseActive.size === 0) {
                landUseActive = new Set(['all']);
                row.querySelectorAll('.filter-btn').forEach(b => {
                    b.classList.remove('inactive');
                    b.setAttribute('aria-pressed', 'true');
                });
            }
        }
        run();
    });
}

function setupFinalizedFilters() {
    const row = document.getElementById('finalized-filter-row');
    if (!row) return;
    row.addEventListener('click', ev => {
        const btn = ev.target.closest('.filter-btn');
        if (!btn) return;
        const val = btn.dataset.finalized;
        if (val === 'all') {
            activeFinalized = new Set(['all']);
            row.querySelectorAll('.filter-btn').forEach(b => {
                b.classList.remove('inactive');
                b.setAttribute('aria-pressed', 'true');
            });
        } else {
            activeFinalized.delete('all');
            const allBtn = row.querySelector('[data-finalized="all"]');
            if (allBtn) {
                allBtn.classList.add('inactive');
                allBtn.setAttribute('aria-pressed', 'false');
            }
            if (activeFinalized.has(val)) {
                activeFinalized.delete(val);
                btn.classList.add('inactive');
                btn.setAttribute('aria-pressed', 'false');
            } else {
                activeFinalized.add(val);
                btn.classList.remove('inactive');
                btn.setAttribute('aria-pressed', 'true');
            }
            if (activeFinalized.size === 0) {
                activeFinalized = new Set(['all']);
                row.querySelectorAll('.filter-btn').forEach(b => {
                    b.classList.remove('inactive');
                    b.setAttribute('aria-pressed', 'true');
                });
            }
        }
        run();
    });
}

function setupControls() {
    document.getElementById('year-filter').addEventListener('change', e=>{ yearFilter = e.target.value; run(); });
    document.getElementById('sort-select').addEventListener('change', e=>{ sortMode = e.target.value; run(); });
}

function setupBackTop() {
    const list = document.getElementById('data-list');
    const btn = document.getElementById('back-top');
    list.addEventListener('scroll', ()=>{ btn.classList.toggle('visible', list.scrollTop > 200); });
    btn.addEventListener('click', ()=>{ list.scrollTo({top:0, behavior:'smooth'}); });
}

/* ──────────────────────────────────────────────────────────────────────────
   3. COMMUNITY NEWS TAB
   ────────────────────────────────────────────────────────────────────────── */

const NEWS_API_BASE = 'https://esterotoday.com/wp-json/wp/v2/posts';
const NEWS_PAGE_SIZE = 20;
let newsData = [];
let newsCats = new Map();
let newsActiveCat = 'all';
let newsActivePillar = 'all';
let newsLoaded = false;
let newsActiveId = null;
let newsNextPage = 2;
let newsHasMore = true;
let newsLoadingMore = false;
let currentView = 'meetings';

const NEWS_PILLARS = [
    { slug: 'education',   label: 'Education',   icon: 'fa-graduation-cap', color: '#0369a1', bg: '#f0f9ff', bd: '#7dd3fc' },
    { slug: 'environment', label: 'Environment', icon: 'fa-leaf',           color: '#15803d', bg: '#f0fdf4', bd: '#86efac' },
    { slug: 'health',      label: 'Health',      icon: 'fa-heart-pulse',    color: '#b91c1c', bg: '#fef2f2', bd: '#fca5a5' },
    { slug: 'safety',      label: 'Safety',      icon: 'fa-shield-halved',  color: '#c2410c', bg: '#fff7ed', bd: '#fdba74' },
];

function stripHtml(html) {
    if (!html) return '';
    const tmp = document.createElement('div');
    tmp.innerHTML = html;
    return (tmp.textContent || tmp.innerText || '').replace(/\s+/g, ' ').trim();
}

function decodeEntities(html) {
    if (!html) return '';
    const tmp = document.createElement('textarea');
    tmp.innerHTML = html;
    return tmp.value;
}

function fmtNewsDate(iso) {
    if (!iso) return '';
    const d = new Date(iso);
    return isNaN(d) ? iso : d.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
}

function getFeaturedImage(post) {
    if (post.jetpack_featured_media_url) return post.jetpack_featured_media_url;
    const media = post._embedded && post._embedded['wp:featuredmedia'];
    if (media && media[0]) {
        const m = media[0];
        if (m.source_url) return m.source_url;
        if (m.media_details && m.media_details.sizes) {
            const s = m.media_details.sizes;
            return (s.medium_large || s.medium || s.large || s.full || {}).source_url || null;
        }
    }
    return null;
}

function getPostCategories(post) {
    const terms = post._embedded && post._embedded['wp:term'];
    if (!terms) return [];
    const flat = [];
    terms.forEach(group => { (group || []).forEach(term => { if (term && term.taxonomy === 'category') flat.push(term); }); });
    return flat;
}

function newsApiUrl(page) {
    const params = new URLSearchParams({ _embed: '1', per_page: String(NEWS_PAGE_SIZE), page: String(page) });
    return `${NEWS_API_BASE}?${params.toString()}`;
}

async function loadNews() {
    const list = document.getElementById('data-list');
    list.innerHTML = `<div class="empty"><i class="fa-solid fa-spinner fa-spin" aria-hidden="true"></i><p>Loading community news from EsteroToday.com...</p></div>`;
    try {
        const posts = await fetchWithSessionCache(newsApiUrl(1), 'news:p1', 5 * 60 * 1000);
        newsData = Array.isArray(posts) ? posts : [];
        newsNextPage = 2;
        newsHasMore = newsData.length === NEWS_PAGE_SIZE;
        recomputeNewsCats();
        newsLoaded = true;
        buildNewsCatFilters();
        document.getElementById('tab-count-news').textContent = newsData.length;
        renderNews();
    } catch (err) {
        console.warn('News load failed:', err);
        list.innerHTML = `<div class="empty"><i class="fa-solid fa-triangle-exclamation" style="color:#ef4444;" aria-hidden="true"></i><p style="color:#ef4444;">Could not load community news.<br><a href="https://esterotoday.com/" target="_blank" style="color:var(--accent);">Visit EsteroToday.com</a> directly.</p></div>`;
    }
}

async function loadMoreNews() {
    if (newsLoadingMore || !newsHasMore) return;
    newsLoadingMore = true;
    const btn = document.querySelector('.load-more-btn');
    if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin" aria-hidden="true"></i> Loading…'; }
    try {
        const posts = await fetchWithSessionCache(newsApiUrl(newsNextPage), `news:p${newsNextPage}`, 5 * 60 * 1000);
        const list2 = Array.isArray(posts) ? posts : [];
        if (!list2.length) { newsHasMore = false; }
        else { newsData = newsData.concat(list2); newsNextPage += 1; newsHasMore = list2.length === NEWS_PAGE_SIZE; }
        recomputeNewsCats();
        buildNewsCatFilters();
        document.getElementById('tab-count-news').textContent = newsData.length;
        renderNews();
    } catch (err) {
        console.info('No more news pages:', err && err.message);
        newsHasMore = false;
        renderNews();
    } finally { newsLoadingMore = false; }
}

function recomputeNewsCats() {
    newsCats = new Map();
    newsData.forEach(p => {
        getPostCategories(p).forEach(c => {
            const prev = newsCats.get(c.id) || { id: c.id, name: c.name, slug: c.slug, count: 0 };
            prev.count += 1;
            newsCats.set(c.id, prev);
        });
    });
}

function buildNewsCatFilters() {
    const row = document.getElementById('news-cat-row');
    row.querySelectorAll('[data-cat]:not([data-cat="all"])').forEach(el => el.remove());
    const allBtn = row.querySelector('[data-cat="all"]');
    const existing = allBtn.querySelector('.chip-count');
    const allHtml = `<span class="chip-count">${newsData.length}</span>`;
    if (existing) existing.outerHTML = allHtml; else allBtn.insertAdjacentHTML('beforeend', allHtml);

    const pillarSlugs = new Set(NEWS_PILLARS.map(p => p.slug.toLowerCase()));
    const generic = [...newsCats.values()].filter(c => !pillarSlugs.has((c.slug || '').toLowerCase()));
    generic.sort((a, b) => b.count - a.count);
    generic.forEach(c => {
        const btn = document.createElement('button');
        btn.className = 'filter-btn' + (newsActiveCat === String(c.id) ? '' : (newsActiveCat === 'all' ? '' : ' inactive'));
        btn.dataset.cat = String(c.id);
        btn.style.cssText = 'background:#f5f3ff;color:#6d28d9;border-color:#c4b5fd;';
        btn.innerHTML = `<i class="fa-solid fa-tag" aria-hidden="true"></i> ${decodeEntities(c.name)}<span class="chip-count">${c.count}</span>`;
        row.appendChild(btn);
    });

    const pillarRow = document.getElementById('news-pillar-row');
    pillarRow.innerHTML = '';
    NEWS_PILLARS.forEach(p => {
        const match = [...newsCats.values()].find(c => (c.slug || '').toLowerCase() === p.slug);
        const id = match ? String(match.id) : null;
        const count = match ? match.count : 0;
        const btn = document.createElement('button');
        const isActive = newsActivePillar === p.slug;
        btn.className = 'filter-btn' + (newsActivePillar === 'all' || isActive ? '' : ' inactive');
        btn.dataset.pillar = p.slug;
        if (id) btn.dataset.catId = id;
        btn.style.cssText = `background:${p.bg};color:${p.color};border-color:${p.bd};`;
        if (!id) btn.style.opacity = '0.55';
        btn.innerHTML = `<i class="fa-solid ${p.icon}" aria-hidden="true"></i> ${p.label}<span class="chip-count">${count}</span>`;
        pillarRow.appendChild(btn);
    });
}

function filterNews() {
    const q = document.getElementById('main-search').value.trim().toLowerCase();
    const pillarSlug = newsActivePillar !== 'all' ? newsActivePillar : null;
    return newsData.filter(p => {
        const cats = getPostCategories(p);
        if (newsActiveCat !== 'all') { const ids = cats.map(c => String(c.id)); if (!ids.includes(newsActiveCat)) return false; }
        if (pillarSlug) { const slugs = cats.map(c => (c.slug || '').toLowerCase()); if (!slugs.includes(pillarSlug)) return false; }
        if (!q) return true;
        const hay = (decodeEntities(p.title?.rendered || '') + ' ' + stripHtml(p.excerpt?.rendered || '') + ' ' + stripHtml(p.content?.rendered || '') + ' ' + cats.map(c => c.name).join(' ')).toLowerCase();
        return hay.includes(q);
    });
}

function renderNews() {
    const list = document.getElementById('data-list');
    const filtered = filterNews();
    if (!filtered.length) {
        list.innerHTML = `<div class="empty"><i class="fa-solid fa-magnifying-glass" aria-hidden="true"></i><p>No matching articles found.<br>Try a different search or topic.</p></div>`;
        return;
    }
    const qForHl = document.getElementById('main-search').value.trim();
    const cardsHtml = filtered.map(p => {
        const img = getFeaturedImage(p);
        const cats = getPostCategories(p);
        const title = decodeEntities(p.title?.rendered || 'Untitled');
        const excerpt = stripHtml(p.excerpt?.rendered || '');
        const trimmedExcerpt = excerpt.length > 160 ? excerpt.slice(0, 160) + '…' : excerpt;
        const thumb = img ? `<div class="news-thumb" data-bg="${img}"></div>` : `<div class="news-thumb"><i class="fa-solid fa-newspaper" aria-hidden="true"></i></div>`;
        const catPill = cats[0] ? `<span class="news-cat-pill">${decodeEntities(cats[0].name)}</span>` : '';
        // Accessibility: Added role="button" and tabindex="0"
        return `<div class="news-card" data-id="${p.id}" role="button" tabindex="0" aria-label="News: ${title}">
            ${thumb}
            <div class="news-body">
                <div class="news-title">${highlight(title, qForHl)}</div>
                <div class="news-meta">
                    ${catPill}
                    <span class="news-date"><i class="fa-regular fa-calendar" style="margin-right:3px;" aria-hidden="true"></i>${fmtNewsDate(p.date)}</span>
                </div>
                <div class="news-excerpt">${highlight(trimmedExcerpt, qForHl)}</div>
            </div>
        </div>`;
    }).join('');

    const loadMoreHtml = newsHasMore ? `<div class="load-more-row"><button class="load-more-btn"><i class="fa-solid fa-circle-down" aria-hidden="true"></i>Load more articles</button></div>` : '';
    list.innerHTML = cardsHtml + loadMoreHtml;

    list.querySelectorAll('.news-card').forEach(card => {
        card.addEventListener('click', () => openNewsDetail(parseInt(card.dataset.id, 10)));
        if (newsActiveId && parseInt(card.dataset.id, 10) === newsActiveId) card.classList.add('active');
    });
    const moreBtn = list.querySelector('.load-more-btn');
    if (moreBtn) moreBtn.addEventListener('click', loadMoreNews);
    lazyLoadThumbs(list);
}

let _thumbObserver = null;
function lazyLoadThumbs(scope) {
    const targets = scope.querySelectorAll('.news-thumb[data-bg]');
    if (!targets.length) return;
    if (!('IntersectionObserver' in window)) { targets.forEach(el => { el.style.backgroundImage = `url('${el.dataset.bg}')`; el.removeAttribute('data-bg'); }); return; }
    if (!_thumbObserver) {
        _thumbObserver = new IntersectionObserver(entries => {
            entries.forEach(entry => {
                if (!entry.isIntersecting) return;
                const el = entry.target;
                if (el.dataset.bg) { el.style.backgroundImage = `url('${el.dataset.bg}')`; el.removeAttribute('data-bg'); }
                _thumbObserver.unobserve(el);
            });
        }, { rootMargin: '200px' });
    }
    targets.forEach(el => _thumbObserver.observe(el));
}

function openNewsDetail(id) {
    const post = newsData.find(p => p.id === id);
    if (!post) return;
    newsActiveId = id;
    document.querySelectorAll('.news-card').forEach(c => c.classList.remove('active'));
    const card = document.querySelector(`.news-card[data-id="${id}"]`);
    if (card) { card.classList.add('active'); card.scrollIntoView({ behavior: 'smooth', block: 'nearest' }); }

    document.getElementById('detail-header-icon').innerHTML = '<i class="fa-solid fa-newspaper" aria-hidden="true"></i>';
    document.getElementById('detail-header-title').textContent = 'Community News';
    document.getElementById('detail-header-sub').textContent = 'EsteroToday.com · Engage Estero';

    const img = getFeaturedImage(post);
    const cats = getPostCategories(post);
    const title = decodeEntities(post.title?.rendered || 'Untitled');
    const hero = img ? `<div class="news-detail-hero" style="background-image:url('${img}');"></div>` : `<div class="news-detail-hero"><i class="fa-solid fa-newspaper" aria-hidden="true"></i></div>`;
    const catChips = cats.map(c => `<span class="news-cat-pill">${decodeEntities(c.name)}</span>`).join('');

    document.getElementById('detail-content').innerHTML = `
        ${hero}
        <div class="news-detail-title">${title}</div>
        <div class="news-detail-meta">
            ${catChips}
            <span class="news-date"><i class="fa-regular fa-calendar" style="margin-right:4px;" aria-hidden="true"></i>${fmtNewsDate(post.date)}</span>
        </div>
        <div class="news-detail-body">${post.content?.rendered || '<p style="font-style:italic;color:#9ca3af;">No content available — read on EsteroToday.com.</p>'}</div>
        <a class="pdf-btn" href="${post.link}" target="_blank" style="background:var(--accent);">
            <i class="fa-solid fa-arrow-up-right-from-square" aria-hidden="true"></i>Read Full Article on EsteroToday.com
        </a>
        <div style="margin-top:10px;text-align:center;font-size:10px;color:var(--subtle);">Article courtesy of <a href="https://esterotoday.com/" target="_blank" style="color:var(--accent);font-weight:600;">EsteroToday.com</a> · Engage Estero</div>`;

    document.getElementById('detail-panel').classList.add('open');
    document.getElementById('map-spot').style.marginLeft = '380px';
    document.getElementById('close-detail').focus();
}

function setupNewsControls() {
    document.getElementById('news-cat-row').addEventListener('click', ev => {
        const btn = ev.target.closest('.filter-btn');
        if (!btn) return;
        newsActiveCat = btn.dataset.cat;
        document.querySelectorAll('#news-cat-row .filter-btn').forEach(b => { b.classList.toggle('inactive', b.dataset.cat !== newsActiveCat && newsActiveCat !== 'all'); });
        if (newsActiveCat === 'all') document.querySelectorAll('#news-cat-row .filter-btn').forEach(b => b.classList.remove('inactive'));
        renderNews();
    });

    document.getElementById('news-pillar-row').addEventListener('click', ev => {
        const btn = ev.target.closest('.filter-btn');
        if (!btn) return;
        const slug = btn.dataset.pillar;
        newsActivePillar = (newsActivePillar === slug) ? 'all' : slug;
        document.querySelectorAll('#news-pillar-row .filter-btn').forEach(b => { b.classList.toggle('inactive', newsActivePillar !== 'all' && b.dataset.pillar !== newsActivePillar); });
        renderNews();
    });
}

function setView(view) {
    if (view === currentView) return;
    currentView = view;
    document.body.classList.toggle('news-view', view === 'news');
    document.body.classList.toggle('upcoming-view', view === 'upcoming');
    document.querySelectorAll('.view-tab').forEach(t => {
        const isActive = t.dataset.view === view;
        t.classList.toggle('active', isActive);
        t.setAttribute('aria-selected', isActive ? 'true' : 'false');
    });

    const search = document.getElementById('main-search');
    search.value = '';
    search.placeholder = view === 'news' ? 'Search community news articles…' : view === 'upcoming' ? 'Search upcoming meetings, agendas, locations…' : 'Search minutes, projects, locations, titles…';

    document.getElementById('detail-header-icon').innerHTML = '<i class="fa-solid fa-file-lines" aria-hidden="true"></i>';
    document.getElementById('detail-header-title').textContent = 'Meeting Detail';
    document.getElementById('detail-header-sub').textContent = 'Village of Estero Municipal Record';
    document.getElementById('detail-panel').classList.remove('open');
    document.getElementById('map-spot').style.marginLeft = '0';

    if (view === 'news') {
        newsActiveId = null; upcomingActiveId = null;
        document.getElementById('reports-panel').style.display = '';
        if (!newsLoaded) loadNews(); else renderNews();
        if (!reportsLoaded) loadReports();
    } else if (view === 'upcoming') {
        newsActiveId = null; upcomingActiveId = null;
        if (!upcomingLoaded) loadUpcoming(); else renderUpcoming();
    } else {
        newsActiveId = null; upcomingActiveId = null;
        run();
    }
}

function setupViewTabs() {
    document.querySelectorAll('.view-tab').forEach(tab => {
        tab.addEventListener('click', () => setView(tab.dataset.view));
    });
}

/* ──────────────────────────────────────────────────────────────────────────
   4. MINUTES INDEX
   ────────────────────────────────────────────────────────────────────────── */
let minutesIndex = null;
async function loadMinutesIndex() {
    if (minutesIndex) return minutesIndex;
    try {
        const sha = siteManifest?.minutes_index?.sha256 || '';
        const url = versionedUrl('app/data/minutes_index.json', sha);
        const res = await fetch(url, { cache: 'force-cache' });
        if (!res.ok) throw new Error('HTTP ' + res.status);
        minutesIndex = await res.json();
    } catch (e) { console.warn('minutes_index.json unavailable:', e); minutesIndex = { council: {}, pzdb: {} }; }
    if (allData && allData.length) { if (currentView === 'meetings') run(); else if (currentView === 'upcoming' && upcomingLoaded) renderUpcoming(); }
    return minutesIndex;
}

function meetingBodyKey(meetingType) {
    const t = (meetingType || '').toLowerCase();
    if (t.startsWith('pzdb') || t.includes('planning, zoning') || t.includes('planning zoning')) return 'pzdb';
    return 'council';
}

function resolveMinutesPdf(meetingType, isoDate) {
    if (!minutesIndex || !isoDate) return null;
    const key = meetingBodyKey(meetingType);
    return (minutesIndex[key] && minutesIndex[key][isoDate]) || null;
}

/* ──────────────────────────────────────────────────────────────────────────
   5. REPORTS & GOVERNING DOCS
   ────────────────────────────────────────────────────────────────────────── */
const REPORTS_API = 'https://esterotoday.com/wp-json/wp/v2/pages?slug=reports&_embed=1';
let reportsLoaded = false;
let reportsData = null;

async function loadReports() {
    if (reportsLoaded) return reportsData;
    try {
        const res = await fetchWithSessionCache(REPORTS_API, 'reports', 30 * 60 * 1000);
        const page = Array.isArray(res) ? res[0] : null;
        reportsData = extractReports(page?.content?.rendered || '');
    } catch (e) { console.warn('Reports load failed:', e); reportsData = { annual: [], governing: [] }; }
    reportsLoaded = true; renderReportsPanel(); return reportsData;
}

function extractReports(html) {
    const out = { annual: [], governing: [] }; if (!html) return out;
    const blurbRe = /title=["']([^"']*Annual Report[^"']*)["'][^\]]*url=["']([^"']+\.pdf[^"']*)["'][^\]]*image=["']([^"']+)["']/gi;
    const seenUrls = new Set(); let m;
    while ((m = blurbRe.exec(html)) !== null) {
        const url = m[2]; if (seenUrls.has(url)) continue; seenUrls.add(url);
        const yearMatch = m[1].match(/(20\d{2})/);
        out.annual.push({ year: yearMatch ? yearMatch[1] : m[1], label: m[1].trim(), url, cover: m[3] });
    }
    const fallbackRe = /https:\/\/esterotoday\.com\/wp-content\/uploads\/\d{4}\/\d{2}\/[^"']*Annual[^"']*\.pdf/gi;
    while ((m = fallbackRe.exec(html)) !== null) { if (!seenUrls.has(m[0])) { seenUrls.add(m[0]); const ym = m[0].match(/(20\d{2})/); out.annual.push({ year: ym ? ym[1] : '', label: 'Annual Report', url: m[0], cover: null }); } }
    out.annual.sort((a, b) => (b.year || '').localeCompare(a.year || ''));
    const knownDocs = [{ needle: 'bylaws', label: 'Bylaws', icon: 'fa-file-contract' }, { needle: 'articles of incorporation', label: 'Articles of Incorporation', icon: 'fa-scroll' }, { needle: 'fictitious', label: 'Fictitious Name Registration', icon: 'fa-id-card' }];
    const seenDocs = new Set();
    knownDocs.forEach(doc => {
        const re = new RegExp('href=["\\\' ]([^"\\\' ]*' + doc.needle + '[^"\\\' ]*\\.pdf[^"\\\' ]*)["\\\' ]', 'i');
        const dm = html.match(re); if (dm && !seenDocs.has(doc.label)) { seenDocs.add(doc.label); out.governing.push({ label: doc.label, url: dm[1], icon: doc.icon }); }
    });
    return out;
}

function renderReportsPanel() {
    const panel = document.getElementById('reports-panel'); if (!panel || !reportsData) return;
    const { annual, governing } = reportsData; if (!annual.length && !governing.length) { panel.dataset.empty = '1'; return; }
    delete panel.dataset.empty;
    const annualHtml = annual.map(r => `<a class="report-card" href="${r.url}" target="_blank" rel="noopener" title="${r.label}">${r.cover ? `<div class="report-cover" style="background-image:url('${r.cover}');"></div>` : `<div class="report-cover"><i class="fa-solid fa-file-pdf" aria-hidden="true"></i></div>`}<div class="report-year">${r.year || '—'}</div><div class="report-label">Annual Report</div></a>`).join('');
    const govHtml = governing.length ? `<ul class="governing-list">${governing.map(g => `<li><a href="${g.url}" target="_blank" rel="noopener"><i class="fa-solid ${g.icon}" aria-hidden="true"></i> ${g.label}</a></li>`).join('')}</ul>` : '';
    document.getElementById('reports-strip').innerHTML = annualHtml; document.getElementById('reports-governing').innerHTML = govHtml;
    panel.style.display = '';
}

function setupReportsPanel() {
    const panel = document.getElementById('reports-panel'); if (!panel) return;
    const head = panel.querySelector('.reports-head');
    head.addEventListener('click', () => {
        const isOpen = panel.classList.toggle('open');
        head.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
        if (isOpen && !reportsLoaded) loadReports();
    });
    // Accessibility: Keyboard support for reports panel header
    head.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); head.click(); } });
}

/* ──────────────────────────────────────────────────────────────────────────
   6. UPCOMING MEETINGS
   ────────────────────────────────────────────────────────────────────────── */
const UPCOMING_API_BASE = 'https://estero-fl.gov/wp-json/tribe/events/v1/events';
let upcomingData = []; let upcomingCats = new Map(); let upcomingActiveCat = 'all'; let upcomingRange = 'upcoming'; let upcomingLoaded = false; let upcomingActiveId = null;
function isoDay(date) { return date.toISOString().slice(0, 10); }
function buildUpcomingUrl() {
    const now = new Date(); const back = new Date(now); back.setDate(back.getDate() - 90); const fwd = new Date(now); fwd.setDate(fwd.getDate() + 180);
    const params = new URLSearchParams({ per_page: '50', start_date: isoDay(back), end_date: isoDay(fwd) });
    return `${UPCOMING_API_BASE}?${params.toString()}`;
}
async function loadUpcoming() {
    const list = document.getElementById('data-list'); list.innerHTML = `<div class="empty"><i class="fa-solid fa-spinner fa-spin" aria-hidden="true"></i><p>Loading upcoming meetings from estero-fl.gov...</p></div>`;
    try {
        const data = await fetchWithSessionCache(buildUpcomingUrl(), 'upcoming', 10 * 60 * 1000); upcomingData = (data && data.events) || [];
        upcomingCats = new Map(); upcomingData.forEach(ev => { (ev.categories || []).forEach(c => { const prev = upcomingCats.get(c.id) || { id: c.id, name: c.name, slug: c.slug, count: 0 }; prev.count += 1; upcomingCats.set(c.id, prev); }); });
        upcomingLoaded = true; buildUpcomingCatFilters(); document.getElementById('tab-count-upcoming').textContent = upcomingData.length; renderUpcoming();
    } catch (err) { console.warn('Upcoming load failed:', err); list.innerHTML = `<div class="empty"><i class="fa-solid fa-triangle-exclamation" style="color:#ef4444;" aria-hidden="true"></i><p style="color:#ef4444;">Could not load upcoming meetings.<br><a href="https://estero-fl.gov/meetings/" target="_blank" style="color:var(--accent);">Visit estero-fl.gov/meetings</a> directly.</p></div>`; }
}
function buildUpcomingCatFilters() {
    const row = document.getElementById('upcoming-cat-row'); row.querySelectorAll('[data-cat]:not([data-cat="all"])').forEach(el => el.remove());
    const allBtn = row.querySelector('[data-cat="all"]'); const existing = allBtn.querySelector('.chip-count'); const html = `<span class="chip-count">${upcomingData.length}</span>`; if (existing) existing.outerHTML = html; else allBtn.insertAdjacentHTML('beforeend', html);
    const ordered = [...upcomingCats.values()].sort((a, b) => b.count - a.count); ordered.forEach(c => { const btn = document.createElement('button'); btn.className = 'filter-btn inactive'; btn.dataset.cat = String(c.id); btn.style.cssText = 'background:#f0fdf4;color:#15803d;border-color:#86efac;'; btn.innerHTML = `<i class="fa-solid fa-gavel" aria-hidden="true"></i> ${decodeEntities(c.name)}<span class="chip-count">${c.count}</span>`; row.appendChild(btn); });
}
function filterUpcoming() {
    const q = document.getElementById('main-search').value.trim().toLowerCase(); const todayIso = isoDay(new Date());
    return upcomingData.filter(ev => {
        if (upcomingActiveCat !== 'all') { const cats = (ev.categories || []).map(c => String(c.id)); if (!cats.includes(upcomingActiveCat)) return false; }
        const startIso = (ev.start_date || '').slice(0, 10); if (upcomingRange === 'upcoming' && startIso < todayIso) return false; if (upcomingRange === 'past' && startIso >= todayIso) return false;
        if (q) { const hay = (decodeEntities(ev.title || '') + ' ' + stripHtml(ev.description || '') + ' ' + (ev.categories || []).map(c => c.name).join(' ') + ' ' + (ev.venue && (ev.venue.venue || '') + ' ' + (ev.venue.address || ''))).toLowerCase(); if (!hay.includes(q)) return false; } return true;
    });
}
function fmtUpcomingTime(startIso) { if (!startIso) return ''; const d = new Date(startIso.replace(' ', 'T')); return isNaN(d) ? startIso : d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' }); }
function dateChip(startIso) { const d = new Date((startIso || '').replace(' ', 'T')); if (isNaN(d)) return { month: '—', day: '—', year: '' }; return { month: d.toLocaleDateString('en-US', { month: 'short' }), day: d.toLocaleDateString('en-US', { day: 'numeric' }), year: d.getFullYear().toString() }; }
function renderUpcoming() {
    const list = document.getElementById('data-list'); const filtered = filterUpcoming(); if (!filtered.length) { list.innerHTML = `<div class="empty"><i class="fa-regular fa-calendar" aria-hidden="true"></i><p>No meetings match your filters.<br>Try expanding the date range or category.</p></div>`; return; }
    const qForHl = document.getElementById('main-search').value.trim(); const todayIso = isoDay(new Date()); filtered.sort((a, b) => { const aStart = (a.start_date || '').slice(0, 10); const bStart = (b.start_date || '').slice(0, 10); if (upcomingRange === 'past') return bStart.localeCompare(aStart); return aStart.localeCompare(bStart); });
    list.innerHTML = filtered.map(ev => {
        const startIso = (ev.start_date || '').slice(0, 10); const isToday = startIso === todayIso; const isPast = startIso < todayIso; const stateCls = isToday ? 'today' : isPast ? 'past' : ''; const statusCls = isToday ? 'today' : isPast ? 'past' : 'future'; const statusText = isToday ? 'Today' : isPast ? 'Past' : 'Upcoming'; const chip = dateChip(ev.start_date); const title = decodeEntities(ev.title || 'Untitled meeting'); const cats = (ev.categories || []).map(c => decodeEntities(c.name)); const minutesUrl = isPast ? resolveMinutesPdf(cats.join(' '), startIso) : null;
        // Accessibility: Added role="button" and tabindex="0"
        return `<div class="upcoming-card ${stateCls}" data-id="${ev.id}" role="button" tabindex="0" aria-label="Upcoming Meeting: ${title}">
            <div class="upcoming-top">
                <div class="upcoming-date"><div class="ud-month">${chip.month}</div><div class="ud-day">${chip.day}</div><div class="ud-year">${chip.year}</div></div>
                <div class="upcoming-body">
                    <div class="upcoming-title">${highlight(title, qForHl)}</div>
                    <div class="upcoming-meta">
                        <span class="upcoming-status ${statusCls}">${statusText}</span>
                        <span class="upcoming-time"><i class="fa-regular fa-clock" aria-hidden="true"></i>${fmtUpcomingTime(ev.start_date) || '—'}</span>
                        ${cats[0] ? `<span class="news-cat-pill">${cats[0]}</span>` : ''}
                    </div>
                    <div class="upcoming-actions">
                        <a class="btn-sm btn-outline" href="${ev.url}" target="_blank" rel="noopener" title="View on estero-fl.gov" aria-label="View meeting details on estero-fl.gov">
                            <i class="fa-solid fa-arrow-up-right-from-square" aria-hidden="true"></i>Event
                        </a>
                        <button class="btn-sm btn-outline upcoming-ics" data-id="${ev.id}" title="Add to calendar (.ics)" aria-label="Add to calendar">
                            <i class="fa-regular fa-calendar-plus" aria-hidden="true"></i>Calendar
                        </button>
                        ${minutesUrl ? `<a class="btn-sm btn-solid" href="${minutesUrl}" target="_blank" rel="noopener" style="background:var(--accent);" aria-label="View Minutes PDF">
                                 <i class="fa-solid fa-file-pdf" aria-hidden="true"></i>Minutes
                               </a>` : ''}
                    </div>
                </div>
            </div>
        </div>`;
    }).join('');
    list.querySelectorAll('.upcoming-card').forEach(card => { card.addEventListener('click', e => { if (e.target.closest('a, button')) return; openUpcomingDetail(parseInt(card.dataset.id, 10)); }); if (upcomingActiveId && parseInt(card.dataset.id, 10) === upcomingActiveId) card.classList.add('active'); });
    list.querySelectorAll('.upcoming-ics').forEach(btn => { btn.addEventListener('click', e => { e.stopPropagation(); const ev = upcomingData.find(x => x.id === parseInt(btn.dataset.id, 10)); if (ev) downloadIcs(ev); }); });
}
function openUpcomingDetail(id) {
    const ev = upcomingData.find(e => e.id === id); if (!ev) return; upcomingActiveId = id; document.querySelectorAll('.upcoming-card').forEach(c => c.classList.remove('active')); const card = document.querySelector(`.upcoming-card[data-id="${id}"]`); if (card) { card.classList.add('active'); card.scrollIntoView({ behavior: 'smooth', block: 'nearest' }); }
    document.getElementById('detail-header-icon').innerHTML = '<i class="fa-regular fa-calendar" aria-hidden="true"></i>'; document.getElementById('detail-header-title').textContent = 'Upcoming Meeting'; document.getElementById('detail-header-sub').textContent = 'estero-fl.gov · Village Calendar';
    const startIso = (ev.start_date || '').slice(0, 10); const todayIso = isoDay(new Date()); const isPast = startIso < todayIso; const title = decodeEntities(ev.title || 'Untitled meeting'); const cats = (ev.categories || []).map(c => decodeEntities(c.name)); const venueName = ev.venue && (ev.venue.venue || ev.venue.address) ? decodeEntities(ev.venue.venue || ev.venue.address) : ''; const geo = ev.venue && ev.venue.geo_lat && ev.venue.geo_lng ? `${ev.venue.geo_lat}, ${ev.venue.geo_lng}` : ''; const descHtml = ev.description || ''; const minutesUrl = isPast ? resolveMinutesPdf(cats.join(' '), startIso) : null; const chip = dateChip(ev.start_date);
    document.getElementById('detail-content').innerHTML = `
        <div class="detail-banner" style="background:var(--accent-light);border-color:var(--accent-border);">
            <div class="detail-banner-name" style="color:var(--accent);"><i class="fa-solid fa-gavel" aria-hidden="true"></i>${title}</div>
            <div class="detail-banner-meta" style="color:var(--accent);margin-top:4px;">${chip.month} ${chip.day}, ${chip.year} · ${fmtUpcomingTime(ev.start_date) || 'TBD'}</div>
            ${cats.length ? `<div style="margin-top:8px;display:flex;flex-wrap:wrap;gap:5px;">${cats.map(c => `<span class="news-cat-pill">${c}</span>`).join('')}</div>` : ''}
        </div>
        <div class="detail-grid">
            ${venueName ? `<div class="detail-cell full"><div class="dcl"><i class="fa-solid fa-location-dot" aria-hidden="true"></i>Venue</div><div class="dcv" style="font-weight:500;font-size:12px;">${venueName}</div>${geo ? `<div style="font-family:'IBM Plex Mono',monospace;font-size:10px;color:#9ca3af;margin-top:3px;">${geo}</div>` : ''}</div>` : ''}
            <div class="detail-cell"><div class="dcl"><i class="fa-regular fa-clock" aria-hidden="true"></i>Start</div><div class="dcv" style="font-family:'IBM Plex Mono',monospace;font-size:11px;">${(ev.start_date || '—').replace('T', ' ')}</div></div>
            <div class="detail-cell"><div class="dcl"><i class="fa-regular fa-clock" aria-hidden="true"></i>End</div><div class="dcv" style="font-family:'IBM Plex Mono',monospace;font-size:11px;">${(ev.end_date || '—').replace('T', ' ')}</div></div>
        </div>
        ${descHtml ? `<div class="action-section"><div class="action-header"><i class="fa-solid fa-circle-info" aria-hidden="true"></i>Event Description</div><div class="action-box" style="font-size:12px;line-height:1.6;color:var(--muted);">${descHtml}</div></div>` : ''}
        ${minutesUrl ? `<a class="pdf-btn" href="${minutesUrl}" target="_blank" rel="noopener" style="background:var(--accent);margin-bottom:8px;"><i class="fa-solid fa-file-pdf" aria-hidden="true"></i>View Approved Minutes PDF</a>` : ''}
        <a class="pdf-btn" href="${ev.url}" target="_blank" rel="noopener" style="background:var(--muted);margin-bottom:8px;"><i class="fa-solid fa-arrow-up-right-from-square" aria-hidden="true"></i>Open on estero-fl.gov</a>
        <button class="pdf-btn" id="detail-ics" style="background:var(--surface2);color:var(--accent);border:1px solid var(--accent-border);"><i class="fa-regular fa-calendar-plus" aria-hidden="true"></i>Add to Calendar (.ics)</button>
        <div style="margin-top:10px;text-align:center;font-size:10px;color:var(--subtle);">Live from <a href="https://estero-fl.gov/meetings/" target="_blank" style="color:var(--accent);font-weight:600;">estero-fl.gov</a> · Tribe Events API</div>`;
    const icsBtn = document.getElementById('detail-ics'); if (icsBtn) icsBtn.addEventListener('click', () => downloadIcs(ev));
    document.getElementById('detail-panel').classList.add('open'); document.getElementById('map-spot').style.marginLeft = '380px';
    document.getElementById('close-detail').focus();
}
function downloadIcs(ev) { const fmt = s => (s || '').replace(/[-:T ]/g, '').slice(0, 15); const uid = `tribe-${ev.id}@estero-fl.gov`; const dt = new Date().toISOString().replace(/[-:.]/g, '').slice(0, 15) + 'Z'; const lines = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//EagleGIS//Village of Estero Upcoming//EN', 'BEGIN:VEVENT', `UID:${uid}`, `DTSTAMP:${dt}`, `DTSTART:${fmt(ev.start_date)}`, `DTEND:${fmt(ev.end_date || ev.start_date)}`, `SUMMARY:${decodeEntities(ev.title || 'Village Meeting').replace(/[\r\n,;]/g, ' ')}`, `URL:${ev.url || ''}`, ev.venue && ev.venue.venue ? `LOCATION:${decodeEntities(ev.venue.venue)}` : '', 'END:VEVENT', 'END:VCALENDAR'].filter(Boolean); const blob = new Blob([lines.join('\r\n')], { type: 'text/calendar' }); const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = `estero-meeting-${ev.id}.ics`; document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(a.href), 1000); }
function setupUpcomingControls() {
    document.getElementById('upcoming-cat-row').addEventListener('click', ev => { const btn = ev.target.closest('.filter-btn'); if (!btn) return; upcomingActiveCat = btn.dataset.cat; document.querySelectorAll('#upcoming-cat-row .filter-btn').forEach(b => { b.classList.toggle('inactive', upcomingActiveCat !== 'all' && b.dataset.cat !== upcomingActiveCat); }); renderUpcoming(); });
    document.getElementById('upcoming-range-row').addEventListener('click', ev => { const btn = ev.target.closest('.upcoming-range'); if (!btn) return; upcomingRange = btn.dataset.range; document.querySelectorAll('#upcoming-range-row .upcoming-range').forEach(b => { b.classList.toggle('inactive', b.dataset.range !== upcomingRange); }); renderUpcoming(); });
}

/* ──────────────────────────────────────────────────────────────────────────
   SessionStorage cache helper
   ────────────────────────────────────────────────────────────────────────── */
async function fetchWithSessionCache(url, key, ttlMs) {
    const cacheKey = `eaglegis:${key}:${url}`; try { const cached = sessionStorage.getItem(cacheKey); if (cached) { const { ts, data } = JSON.parse(cached); if (Date.now() - ts < ttlMs) return data; } } catch (e) { }
    const res = await fetch(url, { mode: 'cors' }); if (!res.ok) throw new Error('HTTP ' + res.status); const data = await res.json();
    try { sessionStorage.setItem(cacheKey, JSON.stringify({ ts: Date.now(), data })); } catch (e) { } return data;
}

/* ──────────────────────────────────────────────────────────────────────────
   7. STARTUP
   ────────────────────────────────────────────────────────────────────────── */
setupViewTabs(); setupNewsControls(); setupUpcomingControls(); setupReportsPanel();
window.addEventListener('load', () => { if (!document.getElementById('map-iframe')?.dataset.loaded) { scheduleIdle(loadDeferredMap, 800); } });
init();
