(function (global) {
  'use strict';

  const CURATED = [
    { id: 'mcc', parent_id: null, display_name: 'חבר', short_name: 'חבר', aliases: ['MCC', 'mcc', 'חבר'], color: '#f59e0b', sort_order: 10 },
    { id: 'mcc-sheli', parent_id: 'mcc', display_name: 'חבר שלי', short_name: 'חבר שלי', aliases: ['חבר שלי'], color: '#f59e0b', sort_order: 11 },
    { id: 'mcc-teamim', parent_id: 'mcc', display_name: 'חבר טעמים', short_name: 'חבר טעמים', aliases: ['חבר טעמים'], color: '#f59e0b', sort_order: 12 },
    { id: 'hot', parent_id: null, display_name: 'מועדון הוט', short_name: 'HOT', aliases: ['HOT', 'hot', 'מועדון הוט'], color: '#f43f5e', sort_order: 20 },
    { id: 'htzone', parent_id: null, display_name: 'הייטק זון', short_name: 'HTzone', aliases: ['HTzone', 'htzone'], color: '#06b6d4', sort_order: 30 },
    { id: 'buyme', parent_id: null, display_name: 'Buyme', short_name: 'BUYME', aliases: ['BUYME'], alias_patterns: ['BUYME'], color: '#3b82f6', sort_order: 40 },
    { id: 'max', parent_id: null, display_name: 'MAX', short_name: 'MAX', aliases: ['MAX'], color: '#8b5cf6', sort_order: 50 },
    { id: 'max-giftcard', parent_id: 'max', display_name: 'GiftCard max', short_name: 'GiftCard max', aliases: ['GiftCard max'], color: '#8b5cf6', sort_order: 51 },
    { id: 'max-super-giftcard', parent_id: 'max', display_name: 'Super GiftCard max', short_name: 'Super GiftCard max', aliases: ['Super GiftCard max'], color: '#8b5cf6', sort_order: 52 },
    { id: 'max-food', parent_id: 'max', display_name: 'Giftcard Food', short_name: 'Giftcard Food', aliases: ['Giftcard Food'], color: '#8b5cf6', sort_order: 53 },
    { id: 'max-executive', parent_id: 'max', display_name: 'כרטיס הטבות executive', short_name: 'MAX executive', aliases: ['כרטיס הטבות executive'], color: '#8b5cf6', sort_order: 54 },
    { id: 'discount-key', parent_id: null, display_name: 'מפתח דיסקונט', short_name: 'מפתח דיסקונט', aliases: ['מפתח דיסקונט'], color: '#0ea765', sort_order: 60 }
  ];

  function slug(value) {
    const normalized = String(value || '').trim().toLowerCase()
      .normalize('NFKD').replace(/[\u0300-\u036f]/g, '')
      .replace(/[^a-z0-9\u0590-\u05ff]+/g, '-').replace(/^-|-$/g, '');
    if (normalized) return `program-${normalized}`;
    let hash = 2166136261;
    for (const ch of String(value || 'program')) hash = Math.imul(hash ^ ch.charCodeAt(0), 16777619);
    return `program-${(hash >>> 0).toString(36)}`;
  }

  function fallbackColor(id) {
    let hash = 0;
    for (const ch of id) hash = ((hash << 5) - hash + ch.charCodeAt(0)) | 0;
    return `hsl(${Math.abs(hash) % 360} 68% 52%)`;
  }

  function build(sourceLabels) {
    const programs = CURATED.map((p) => ({ ...p, aliases: [...(p.aliases || [])] }));
    const aliases = new Map();
    programs.forEach((p) => p.aliases.forEach((a) => aliases.set(String(a).trim().toLowerCase(), p.id)));

    function resolve(label) {
      const raw = String(label || '').trim();
      const exact = aliases.get(raw.toLowerCase());
      if (exact) return exact;
      const pattern = programs.find((p) => (p.alias_patterns || []).some((x) => raw.toUpperCase().includes(x.toUpperCase())));
      if (pattern) return pattern.id;
      const id = slug(raw);
      if (!programs.some((p) => p.id === id)) {
        programs.push({ id, parent_id: null, display_name: raw || 'מועדון', short_name: raw || 'מועדון', aliases: raw ? [raw] : [], color: fallbackColor(id), sort_order: 1000 });
        if (raw) aliases.set(raw.toLowerCase(), id);
      }
      return id;
    }

    const observedIds = new Set((sourceLabels || []).filter(Boolean).map(resolve));
    const byId = new Map(programs.map((p) => [p.id, p]));
    const children = new Map();
    programs.forEach((p) => {
      if (p.parent_id) children.set(p.parent_id, [...(children.get(p.parent_id) || []), p.id]);
    });
    const parents = programs.filter((p) => !p.parent_id).sort((a, b) => (a.sort_order || 999) - (b.sort_order || 999) || a.display_name.localeCompare(b.display_name, 'he'));
    const descendants = (id) => {
      const direct = children.get(id) || [];
      return direct.length ? direct.flatMap((child) => [child, ...descendants(child)]) : [];
    };
    const selectableIds = Array.from(observedIds);
    const matches = (selected, programId) => selected.has(programId);
    return { programs, byId, parents, children, descendants, selectableIds, observedIds, resolve, matches };
  }

  function aggregateCounts(registry, directCounts) {
    const result = { ...directCounts };
    registry.parents.forEach((parent) => {
      const ids = [parent.id, ...registry.descendants(parent.id)];
      result[parent.id] = ids.reduce((sum, id) => sum + (directCounts[id] || 0), 0);
    });
    return result;
  }


  // --- Club selection persistence (cookies) -------------------------------
  // Stores only program/club identifiers (e.g. "mcc", "discount-key") so the
  // visitor's club filter choice survives between sessions. No personal data
  // is ever written. Everything is best-effort: when cookies are unavailable
  // or blocked the site simply falls back to the default (all clubs).
  const SELECTION_COOKIE = 'icc_selected_clubs';
  const SELECTION_COOKIE_MAX_AGE = 60 * 60 * 24 * 365; // one year

  function cookiesAvailable() {
    return typeof document !== 'undefined' && typeof document.cookie === 'string';
  }

  function readSavedSelection() {
    if (!cookiesAvailable()) return null;
    try {
      const prefix = `${SELECTION_COOKIE}=`;
      const entry = document.cookie.split('; ').find((row) => row.startsWith(prefix));
      if (!entry) return null;
      const parsed = JSON.parse(decodeURIComponent(entry.slice(prefix.length)));
      if (!Array.isArray(parsed)) return null;
      const ids = parsed.filter((id) => typeof id === 'string' && id);
      return ids.length ? ids : null;
    } catch (e) {
      return null; // corrupted cookie: ignore and use the default selection
    }
  }

  function writeSelectionCookie(value, maxAge) {
    if (!cookiesAvailable()) return;
    try {
      document.cookie = `${SELECTION_COOKIE}=${encodeURIComponent(value)}; path=/; max-age=${maxAge}; samesite=lax`;
    } catch (e) {
      // Cookies blocked (private mode, browser settings): persistence is skipped.
    }
  }

  function saveSelection(ids) {
    writeSelectionCookie(JSON.stringify(ids), SELECTION_COOKIE_MAX_AGE);
  }

  function clearSavedSelection() {
    writeSelectionCookie('', 0);
  }

  // The initial selection for a page: the saved subset when one exists and is
  // still valid for the clubs observed in the current data, otherwise all clubs.
  function initialSelection(registry) {
    const selectable = registry.selectableIds || [];
    const saved = readSavedSelection();
    if (saved) {
      const valid = saved.filter((id) => selectable.includes(id));
      if (valid.length && valid.length < selectable.length) return new Set(valid);
      // A saved selection that no longer matches anything (or that matches
      // everything) is stale: drop it so new clubs are selected by default.
      clearSavedSelection();
    }
    return new Set(selectable);
  }

  // Persist after a user change. Selecting every club is the default state, so
  // it clears the cookie instead of freezing today's club list (which would
  // hide clubs added to the data later).
  function persistSelection(registry, selected) {
    const selectable = registry.selectableIds || [];
    if (!selectable.length) return;
    const allSelected = selectable.every((id) => selected.has(id));
    if (allSelected || selected.size === 0) {
      clearSavedSelection();
      return;
    }
    saveSelection(Array.from(selected).filter((id) => selectable.includes(id)));
  }
  // -------------------------------------------------------------------------

  function renderFilters(container, registry, directCounts, selected, onChange, showCounts) {
    if (!container) return;
    const counts = aggregateCounts(registry, directCounts);
    const allSelected = registry.selectableIds.every((id) => selected.has(id));
    container.innerHTML = '';
    const makeButton = (program, ids, child) => {
      const chosen = ids.filter((id) => selected.has(id)).length;
      const button = document.createElement('button');
      button.type = 'button';
      button.className = `filter-chip program-filter${child ? ' child-program-filter' : ''}`;
      button.dataset.programId = program.id;
      button.setAttribute('aria-pressed', chosen === ids.length ? 'true' : 'false');
      if (chosen === ids.length) button.classList.add('active');
      if (chosen > 0 && chosen < ids.length) button.classList.add('partial');
      button.style.setProperty('--program-color', program.color || fallbackColor(program.id));
      button.innerHTML = `<span class="chip-checkbox">${chosen === ids.length ? '✓' : chosen ? '−' : ''}</span><span class="club-logo-tag">${program.short_name}</span><span class="chip-name">${program.display_name}</span>${showCounts ? `<span class="chip-count">${(counts[program.id] || 0).toLocaleString()}</span>` : ''}`;
      button.addEventListener('click', () => {
        const shouldSelect = !ids.every((id) => selected.has(id));
        ids.forEach((id) => shouldSelect ? selected.add(id) : selected.delete(id));
        if (selected.size === 0) registry.selectableIds.forEach((id) => selected.add(id));
        persistSelection(registry, selected);
        onChange();
      });
      return button;
    };
    const all = document.createElement('button');
    all.type = 'button'; all.className = `filter-chip${allSelected ? ' active' : ''}`; all.dataset.programId = 'ALL';
    all.innerHTML = `<span class="chip-checkbox">${allSelected ? '✓' : ''}</span><span class="chip-name">כל המועדונים</span>${showCounts ? `<span class="chip-count">${(directCounts.ALL != null ? directCounts.ALL : Object.entries(directCounts).filter(([id]) => id !== 'ALL').reduce((sum, [,count]) => sum + count, 0)).toLocaleString()}</span>` : ''}`;
    all.addEventListener('click', () => { selected.clear(); registry.selectableIds.forEach((id) => selected.add(id)); persistSelection(registry, selected); onChange(); });
    container.appendChild(all);
    registry.parents.forEach((parent) => {
      const descendants = registry.descendants(parent.id);
      const ids = [parent.id, ...descendants].filter((id) => registry.observedIds.has(id));
      if (!ids.length) return;
      const group = document.createElement('div'); group.className = 'program-filter-group';
      group.appendChild(makeButton(parent, ids, false));
      // Child programs remain distinct in records/cards, but filters are parent-only.
      container.appendChild(group);
    });
  }

  global.ProgramRegistry = { CURATED, build, aggregateCounts, renderFilters, fallbackColor, initialSelection, persistSelection, clearSavedSelection, readSavedSelection, SELECTION_COOKIE };
})(window);
