/**
 * Israeli Credit Card Discount Finder - Frontend App
 * Features:
 * - Instant typing search with Hebrew normalization & fuzzy match
 * - Multi-word tag and query matching
 * - Hierarchical, data-driven program filters
 * - Multi-discount store option cards
 * - Direct navigation to official discount pages
 * - Fully responsive & mobile-optimized
 */

(function () {
    'use strict';

    let programRegistry = ProgramRegistry.build([]);
    const COOKIE_NAME = 'df_filter_selection';

    function saveFilterCookie() {
        const clubs = Array.from(state.selectedClubs);
        document.cookie = COOKIE_NAME + '=' + encodeURIComponent(JSON.stringify({
            clubs: clubs,
            discountType: state.selectedDiscountType || '',
            sortBy: state.sortBy || 'discount_desc',
            fuzzyThreshold: state.fuzzyThreshold || 0.72,
        })) + ';path=/;max-age=' + (60 * 60 * 24 * 30) + ';SameSite=Lax';
    }

    function loadFilterCookie() {
        const match = document.cookie.split(';').map(c => c.trim()).find(c => c.startsWith(COOKIE_NAME + '='));
        if (!match) return null;
        try {
            return JSON.parse(decodeURIComponent(match.slice(COOKIE_NAME.length + 1)));
        } catch (e) {
            return null;
        }
    }

    // State
    const state = {
        allBusinesses: [],
        filteredBusinesses: [],
        searchQuery: '',
        selectedClubs: new Set(), // Canonical leaf program ids
        selectedDiscountType: '', // '' = all types
        sortBy: 'discount_desc',
        fuzzyThreshold: 0.72, // 0.50 to 1.00
        pageSize: 48,
        renderedCount: 0,
        isLoading: true,
        clubCounts: {},
        totalDiscounts: 0,
    };

    // Resolve exact source labels without flattening child programs.
    function canonicalClub(raw) {
        return programRegistry.resolve(raw);
    }

    function programInfo(id) {
        return programRegistry.byId.get(id) || { id, display_name: id, short_name: id, color: ProgramRegistry.fallbackColor(id) };
    }

    // DOM Elements
    const elements = {
        searchInput: document.getElementById('searchInput'),
        clearSearchBtn: document.getElementById('clearSearchBtn'),
        quickTags: document.getElementById('quickTags'),
        sortSelect: document.getElementById('sortSelect'),
        fuzzyRange: document.getElementById('fuzzyRange'),
        fuzzyValLabel: document.getElementById('fuzzyValLabel'),
        cardsGrid: document.getElementById('cardsGrid'),
        loadingSkeleton: document.getElementById('loadingSkeleton'),
        emptyState: document.getElementById('emptyState'),
        emptyQuery: document.getElementById('emptyQuery'),
        resetSearchBtn: document.getElementById('resetSearchBtn'),
        loadMoreContainer: document.getElementById('loadMoreContainer'),
        loadMoreBtn: document.getElementById('loadMoreBtn'),
        resultsCountText: document.getElementById('resultsCountText'),
        activeFilterBadge: document.getElementById('activeFilterBadge'),
        totalDealsCount: document.getElementById('totalDealsCount'),
        totalStoresCount: document.getElementById('totalStoresCount'),
        programFilters: document.getElementById('programFilters'),
        backToTopBtn: document.getElementById('backToTopBtn'),
    };

    // Hebrew text normalization for fast & accurate instant search
    function normalizeHebrew(text) {
        if (!text) return '';
        return text
            .toString()
            .toLowerCase()
            .replace(/[\u0591-\u05C7]/g, '') // Remove Hebrew Niqqud
            .replace(/["״'׳\-–—_.,/\\|]/g, ' ') // Remove quotes and punctuation
            .replace(/\s+/g, ' ') // Normalize whitespace
            .trim();
    }

    // Levenshtein / fuzzy similarity score (0 to 1)
    function similarity(s1, s2) {
        if (s1 === s2) return 1.0;
        if (!s1 || !s2) return 0.0;
        const l1 = s1.length;
        const l2 = s2.length;
        if (Math.abs(l1 - l2) > 3 && !s1.includes(s2) && !s2.includes(s1)) return 0.0;

        const track = Array(l2 + 1)
            .fill(null)
            .map(() => Array(l1 + 1).fill(null));

        for (let i = 0; i <= l1; i += 1) track[0][i] = i;
        for (let j = 0; j <= l2; j += 1) track[j][0] = j;

        for (let j = 1; j <= l2; j += 1) {
            for (let i = 1; i <= l1; i += 1) {
                const indicator = s1[i - 1] === s2[j - 1] ? 0 : 1;
                track[j][i] = Math.min(
                    track[j][i - 1] + 1, // deletion
                    track[j - 1][i] + 1, // insertion
                    track[j - 1][i - 1] + indicator // substitution
                );
            }
        }
        const dist = track[l2][l1];
        return 1 - dist / Math.max(l1, l2);
    }

    // Check if query matches a business name (supports multi-word exact & fuzzy)
    function matchesQuery(business, normalizedQuery) {
        if (!normalizedQuery) return true;

        const normalizedName = business._normalizedName;
        if (normalizedName.includes(normalizedQuery)) return true;

        const queryWords = normalizedQuery.split(' ').filter((w) => w.length > 0);
        if (queryWords.length === 0) return true;

        // Check if all query words appear in the business name
        if (queryWords.every((qw) => normalizedName.includes(qw))) {
            return true;
        }

        // If threshold is set to 100% (1.0), only exact substring match
        if (state.fuzzyThreshold >= 0.99) return false;

        // Fuzzy match across words
        const nameWords = normalizedName.split(' ').filter((w) => w.length > 0);
        const allWordsMatched = queryWords.every((qw) => {
            if (qw.length < 2) return normalizedName.includes(qw);
            return nameWords.some((nw) => similarity(qw, nw) >= state.fuzzyThreshold);
        });

        return allWordsMatched;
    }

    // Program name formatting helpers
    function getClubFullName(programId) { return programInfo(programId).display_name; }
    function getClubShortName(programId) { return programInfo(programId).short_name; }

    function cleanDiscountText(value) {
        if (!value) return '';
        const container = document.createElement('div');
        container.innerHTML = String(value).replace(/<br\s*\/?\s*>/gi, ' ');
        return (container.textContent || '').replace(/\s+/g, ' ').trim();
    }

    // Process raw array of discount items into grouped business records
    function processRawDiscounts(dataList) {
        const names = new Map();
        const clubCounts = {};

        dataList.forEach((d) => {
            if (!d.business_name || !d.club) return;
            const club = canonicalClub(d.club);
            clubCounts.ALL = (clubCounts.ALL || 0) + 1;
            clubCounts[club] = (clubCounts[club] || 0) + 1;

            const name = d.business_name.trim();
            if (!names.has(name)) {
                names.set(name, {
                    business_name: name,
                    discounts: [],
                    clubs: new Set(),
                    best_discount: null,
                    best_discount_value: 0,
                    _normalizedName: normalizeHebrew(name),
                });
            }

            const entry = names.get(name);
            entry.discounts.push({
                club: club,
                discount: cleanDiscountText(d.discount),
                discount_url: d.discount_url || '',
                discount_type: d.discount_type || null,
                discount_value: d.discount_value != null ? Number(d.discount_value) : null,
            });
            entry.clubs.add(club);
        });

        const businesses = [];
        names.forEach((entry) => {
            const percents = [];
            entry.discounts.forEach((disc) => {
                const text = disc.discount || '';
                // Treat as voucher when explicit type or voucher-like text appears
                const isVoucher = ((disc.discount_type || '').toLowerCase() === 'voucher') || /שובר|voucher|gift\s*card|גיפט|כרטיס\s*מתנה|שובר\s*מתנה/i.test(text);
                if (isVoucher) return;

                if (disc.discount_value != null) {
                    percents.push(Number(disc.discount_value));
                    return;
                }

                // Only extract numeric percent values when percent is explicit
                // e.g. "10%", "10 אחוז", or the word "percent" is present.
                const match = text.match(/(\d+(?:\.\d+)?)\s*(%|אחוז(?:ים)?|percent)/i);
                if (match) {
                    percents.push(parseFloat(match[1]));
                }
                // Do not fallback to grabbing arbitrary numbers (phone numbers, codes, etc.)
            });

            if (percents.length > 0) {
                const maxVal = Math.max(...percents);
                entry.best_discount_value = maxVal;
                entry.best_discount = `${maxVal}%`;
            } else {
                // No numeric percent discounts found (likely only vouchers).
                // Do not set a textual best_discount when only vouchers exist
                // so the UI can hide the best-discount rectangle.
                entry.best_discount_value = 0;
                entry.best_discount = null;
            }

            entry.clubs = Array.from(entry.clubs).sort();
            businesses.push(entry);
        });

        return { businesses, clubCounts, total: clubCounts.ALL };
    }

    // Fetch initial dataset from local API or raw GitHub JSON (GitHub Pages mode)
    async function loadData() {
        const DATA_SOURCES = [
            // 1. Published site static data (GitHub Pages or server /data mount)
            'data/all_combined_discounts.json',
            // 2. Local API businesses endpoint
            '/businesses',
            // 3. Relative legacy fallbacks
            '../data/all_combined_discounts.json',
            'data/all_combined_discounts.json',
            './data/all_combined_discounts.json',
            // 4. Raw GitHub fallback (least preferred)
            'https://raw.githubusercontent.com/yohaybn/israeli-cc-discounts/main/data/all_combined_discounts.json',
        ];

        let loaded = false;

        for (const source of DATA_SOURCES) {
            try {
                const res = await fetch(source);
                if (!res.ok) continue;
                const data = await res.json();
                const labels = Array.isArray(data)
                    ? data.map((d) => d.club)
                    : ((data && data.results) || []).flatMap((b) => (b.discounts || []).map((d) => d.club));
                programRegistry = ProgramRegistry.build(labels);
                state.selectedClubs = ProgramRegistry.initialSelection(programRegistry);

                // If response is from /businesses API endpoint
                if (data && data.results && Array.isArray(data.results)) {
                    state.allBusinesses = data.results.map((b) => ({
                        ...b,
                        _normalizedName: normalizeHebrew(b.business_name),
                    }));
                    // Normalize club keys inside discounts and clubs arrays when API returns businesses
                    state.allBusinesses.forEach((biz) => {
                        if (biz.discounts && Array.isArray(biz.discounts)) {
                            biz.discounts.forEach((d) => {
                                d.club = canonicalClub(d.club);
                            });
                        }
                        if (biz.clubs && Array.isArray(biz.clubs)) {
                            biz.clubs = biz.clubs.map((c) => canonicalClub(c));
                        }
                    });
                    // Fetch clubs info if from API
                    try {
                        const clubsRes = await fetch('/clubs').then((r) => r.json());
                        state.totalDiscounts = clubsRes.total || 0;
                        const clubCountsMap = {};
                        (clubsRes.clubs || []).forEach((c) => {
                            clubCountsMap[c.club] = c.count;
                        });
                        state.clubCounts = { ALL: state.totalDiscounts };
                        Object.entries(clubCountsMap).forEach(([label, count]) => {
                            const id = canonicalClub(label);
                            state.clubCounts[id] = (state.clubCounts[id] || 0) + count;
                        });
                    } catch (e) {
                        // ignore API clubs error
                    }
                } else if (Array.isArray(data)) {
                    // Raw discounts array from JSON file
                    const { businesses, clubCounts, total } = processRawDiscounts(data);
                    state.allBusinesses = businesses;
                    state.clubCounts = clubCounts;
                    state.totalDiscounts = total;
                }

                loaded = true;
                break;
            } catch (err) {
                // Try next source
            }
        }

        if (!loaded) {
            elements.resultsCountText.textContent = 'שגיאה בטעינת הנתונים. נסו לרענן את העמוד.';
            elements.loadingSkeleton.classList.add('hidden');
            return;
        }

        // Update stats counters and render hierarchy-aware filters.
        elements.totalDealsCount.textContent = state.totalDiscounts.toLocaleString();
        elements.totalStoresCount.textContent = state.allBusinesses.length.toLocaleString();
        ProgramRegistry.renderFilters(elements.programFilters, programRegistry, state.clubCounts, state.selectedClubs, () => {
            updateFilterChipsUI();
            applyFiltersAndSort();
        }, true);

        state.isLoading = false;
        elements.loadingSkeleton.classList.add('hidden');
        elements.cardsGrid.classList.remove('hidden');

        updateFilterChipsUI();
        applyFiltersAndSort();
    }

    // Re-render hierarchy-aware filters.
    function updateFilterChipsUI() {
        ProgramRegistry.renderFilters(elements.programFilters, programRegistry, state.clubCounts, state.selectedClubs, () => {
            updateFilterChipsUI();
            applyFiltersAndSort();
        }, true);
    }

    // Filter and sort businesses based on current state
    function applyFiltersAndSort() {
        const query = normalizeHebrew(state.searchQuery);
        const isAllSelected = programRegistry.selectableIds.every((id) => state.selectedClubs.has(id));

        let results = state.allBusinesses.filter((biz) => {
            // Club multi-filter: business must belong to at least one selected club
            if (!isAllSelected) {
                const hasSelectedClub = biz.clubs.some((c) => state.selectedClubs.has(c));
                if (!hasSelectedClub) return false;
            }
            // Search query filter
            // Discount type filter at business-level: require at least one discount matching type
            if (state.selectedDiscountType) {
                const hasType = (biz.discounts || []).some((d) => (d.discount_type || '') === state.selectedDiscountType);
                if (!hasType) return false;
            }
            return matchesQuery(biz, query);
        });

        // Apply sorting
        if (state.sortBy === 'discount_desc') {
            results.sort((a, b) => (b.best_discount_value || 0) - (a.best_discount_value || 0));
        } else if (state.sortBy === 'name_asc') {
            results.sort((a, b) => a.business_name.localeCompare(b.business_name, 'he'));
        } else if (state.sortBy === 'deals_desc') {
            results.sort((a, b) => (b.discounts ? b.discounts.length : 0) - (a.discounts ? a.discounts.length : 0));
        }

        state.filteredBusinesses = results;
        state.renderedCount = 0;
        elements.cardsGrid.innerHTML = '';

        updateResultsMeta();
        renderNextBatch();
    }

    // Render cards batch
    function renderNextBatch() {
        const total = state.filteredBusinesses.length;
        if (total === 0) {
            elements.cardsGrid.classList.add('hidden');
            elements.loadMoreContainer.classList.add('hidden');
            elements.emptyState.classList.remove('hidden');

            const isAllSelected = programRegistry.selectableIds.every((id) => state.selectedClubs.has(id));
            let filterNames = '';
            if (!isAllSelected) {
                filterNames = Array.from(state.selectedClubs).map(getClubShortName).join(', ');
            }
            elements.emptyQuery.textContent = state.searchQuery || filterNames || '';
            return;
        }

        elements.emptyState.classList.add('hidden');
        elements.cardsGrid.classList.remove('hidden');

        const nextLimit = Math.min(state.renderedCount + state.pageSize, total);
        const batch = state.filteredBusinesses.slice(state.renderedCount, nextLimit);

        const fragment = document.createDocumentFragment();
        batch.forEach((biz) => {
            fragment.appendChild(createBusinessCard(biz));
        });

        elements.cardsGrid.appendChild(fragment);
        state.renderedCount = nextLimit;

        if (state.renderedCount < total) {
            elements.loadMoreContainer.classList.remove('hidden');
        } else {
            elements.loadMoreContainer.classList.add('hidden');
        }
    }

    // Create DOM card element for a business
    function createBusinessCard(biz) {
        const card = document.createElement('div');
        card.className = 'business-card';

        const isAllSelected = programRegistry.selectableIds.every((id) => state.selectedClubs.has(id));
        // Filter discounts list based on active club selection
        let discountsToShow = (biz.discounts || []).filter((d) => {
            if (isAllSelected) return true;
            return state.selectedClubs.has(d.club);
        });

        if (discountsToShow.length === 0) {
            discountsToShow = biz.discounts || [];
        }

        const discountCount = discountsToShow.length;
        const hasMultiple = discountCount > 1;

        // Card Header
        const header = document.createElement('div');
        header.className = 'card-header';

        const titleArea = document.createElement('div');
        titleArea.className = 'card-title-area';

        const title = document.createElement('h3');
        title.className = 'business-name';
        title.textContent = biz.business_name;
        titleArea.appendChild(title);

        if (hasMultiple) {
            const multiTag = document.createElement('span');
            multiTag.className = 'multi-badge';
            multiTag.innerHTML = `⚡ ${discountCount} הטבות`;
            titleArea.appendChild(multiTag);
        }

        header.appendChild(titleArea);

        // Best discount / Voucher pill — computed from currently filtered discounts
        const filteredPercents = [];
        discountsToShow.forEach((disc) => {
            const text = disc.discount || '';
            const isVoucher = ((disc.discount_type || '').toLowerCase() === 'voucher') || /שובר|voucher/i.test(text);
            if (isVoucher) return;
            if (disc.discount_value != null) {
                filteredPercents.push(Number(disc.discount_value));
                return;
            }
            const match = text.match(/(\d+(?:\.\d+)?)\s*(%|אחוז(?:ים)?|percent)/i);
            if (match) {
                filteredPercents.push(parseFloat(match[1]));
            }
        });
        const bestFilteredValue = filteredPercents.length > 0 ? Math.max(...filteredPercents) : 0;
        const bestFilteredText = bestFilteredValue > 0 ? `${bestFilteredValue}%` : null;
        const hasPercentBest = bestFilteredValue > 0;
        const voucherCount = discountsToShow.filter((d) => ((d.discount_type || '').toLowerCase() === 'voucher' || /שובר|voucher/i.test(d.discount || ''))).length;
        const hasVoucher = voucherCount > 0;

        if (hasPercentBest) {
            const bestPill = document.createElement('div');
            bestPill.className = 'best-discount-pill';
            bestPill.innerHTML = `
                <span class="best-disc-val">${escapeHtml(bestFilteredText)}</span>
                <span class="best-disc-lbl">הנחה מרבית</span>
            `;
            header.appendChild(bestPill);
        } else if (hasVoucher) {
            const voucherPill = document.createElement('div');
            voucherPill.className = 'voucher-pill';
            voucherPill.innerHTML = `
                <span class="voucher-icon">🎁</span>
                <span class="voucher-label">שובר</span>
                <span class="voucher-count">${voucherCount > 1 ? `(${voucherCount})` : ''}</span>
            `;
            header.appendChild(voucherPill);
        }

        card.appendChild(header);

        // Discounts List
        const list = document.createElement('div');
        list.className = 'discounts-list';

        discountsToShow.forEach((disc) => {
            const clubLower = disc.club;
            const info = programInfo(clubLower);
            const optionLink = document.createElement('a');
            optionLink.className = 'discount-option-item';
            optionLink.dataset.programId = clubLower;
            optionLink.style.setProperty('--program-color', info.color);
            optionLink.href = disc.discount_url || '#';
            optionLink.target = '_blank';
            optionLink.rel = 'noopener noreferrer';
            const clubShort = getClubShortName(disc.club);
            optionLink.title = `מעבר להטבה`;

            const isVoucher = ((disc.discount_type || '').toLowerCase() === 'voucher') || /שובר|voucher/i.test(disc.discount || '');
            const discountTitle = isVoucher ? (disc.discount || 'שובר') : (disc.discount || '');

            // Removed club name from description per UI change request
            optionLink.innerHTML = `
                <div class="option-left-content">
                    <span class="option-club-badge" data-program-id="${escapeHtml(clubLower)}" style="--program-color:${escapeHtml(info.color)}">${escapeHtml(clubShort)}</span>
                    <div class="option-text-wrap">
                        <span class="option-discount-title" title="${escapeHtml(discountTitle)}">${escapeHtml(discountTitle)}</span>
                    </div>
                </div>
                <span class="option-action-btn">
                    <span>${isVoucher ? 'פרטים' : 'להטבה'}</span>
                    <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                        <line x1="7" y1="17" x2="17" y2="7"></line>
                        <polyline points="7 7 17 7 17 17"></polyline>
                    </svg>
                </span>
            `;

            list.appendChild(optionLink);
        });

        card.appendChild(list);
        return card;
    }

    function escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // Update status meta line
    function updateResultsMeta() {
        const total = state.filteredBusinesses.length;
        let countDiscounts = 0;
        const isAllSelected = programRegistry.selectableIds.every((id) => state.selectedClubs.has(id));

        state.filteredBusinesses.forEach((b) => {
            if (isAllSelected) {
                countDiscounts += b.discounts ? b.discounts.length : 0;
            } else {
                (b.discounts || []).forEach((d) => {
                    if (state.selectedClubs.has(d.club)) countDiscounts += 1;
                });
            }
        });

        if (state.searchQuery || !isAllSelected) {
            elements.resultsCountText.innerHTML = `נמצאו <strong>${total.toLocaleString()}</strong> עסקים עם <strong>${countDiscounts.toLocaleString()}</strong> הטבות מתאימות`;
        } else {
            elements.resultsCountText.innerHTML = `מציג <strong>${total.toLocaleString()}</strong> עסקים ורשתות (סה״כ ${countDiscounts.toLocaleString()} הטבות)`;
        }

        if (!isAllSelected) {
            const clubNames = Array.from(state.selectedClubs).map(getClubShortName).join(', ');
            elements.activeFilterBadge.innerHTML = `
                <span>מסונן לפי: <strong>${escapeHtml(clubNames)}</strong></span>
                <button id="clearClubFilterBtn" class="clear-club-filter-btn" title="בטל סינון מועדונים" aria-label="בטל סינון מועדונים">✕</button>
            `;
            elements.activeFilterBadge.classList.remove('hidden');

            const clearFilterBtn = document.getElementById('clearClubFilterBtn');
            if (clearFilterBtn) {
                clearFilterBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    state.selectedClubs = new Set(programRegistry.selectableIds);
                    ProgramRegistry.clearSavedSelection();
                    updateFilterChipsUI();
                    applyFiltersAndSort();
                });
            }
        } else {
            elements.activeFilterBadge.classList.add('hidden');
        }
    }

    // Debounce utility
    function debounce(func, wait) {
        let timeout;
        return function (...args) {
            clearTimeout(timeout);
            timeout = setTimeout(() => func.apply(this, args), wait);
        };
    }

    // Event Listeners
    function setupEvents() {
        // Instant typing search
        const debouncedSearch = debounce((val) => {
            state.searchQuery = val;
            applyFiltersAndSort();
        }, 120);

        elements.searchInput.addEventListener('input', (e) => {
            const val = e.target.value;
            if (val.length > 0) {
                elements.clearSearchBtn.classList.remove('hidden');
            } else {
                elements.clearSearchBtn.classList.add('hidden');
            }
            debouncedSearch(val);
        });

        // Clear search button
        elements.clearSearchBtn.addEventListener('click', () => {
            elements.searchInput.value = '';
            elements.clearSearchBtn.classList.add('hidden');
            state.searchQuery = '';
            elements.searchInput.focus();
            applyFiltersAndSort();
        });

        // Quick tags (multi-word chips)
        if (elements.quickTags) {
            elements.quickTags.addEventListener('click', (e) => {
                const tag = e.target.closest('.quick-tag');
                if (!tag) return;
                const query = tag.getAttribute('data-query') || tag.textContent.trim();
                elements.searchInput.value = query;
                elements.clearSearchBtn.classList.remove('hidden');
                state.searchQuery = query;
                elements.searchInput.focus();
                applyFiltersAndSort();
            });
        }

        // Discount type selector
        const discountTypeSelect = document.getElementById('discountTypeSelect');
        if (discountTypeSelect) {
            discountTypeSelect.addEventListener('change', (e) => {
                state.selectedDiscountType = e.target.value || '';
                applyFiltersAndSort();
            });
        }

        // Sort dropdown
        elements.sortSelect.addEventListener('change', (e) => {
            state.sortBy = e.target.value;
            applyFiltersAndSort();
        });

        // Fuzzy search sensitivity slider
        if (elements.fuzzyRange) {
            elements.fuzzyRange.addEventListener('input', (e) => {
                const val = parseInt(e.target.value, 10);
                state.fuzzyThreshold = val / 100;

                let labelText = `${val}%`;
                if (val >= 95) {
                    labelText += ' (מדויק)';
                } else if (val >= 78) {
                    labelText += ' (קפדני)';
                } else if (val >= 68) {
                    labelText += ' (מאוזן)';
                } else {
                    labelText += ' (גמיש מאוד)';
                }
                elements.fuzzyValLabel.textContent = labelText;
                applyFiltersAndSort();
            });
        }

        // Load more button
        elements.loadMoreBtn.addEventListener('click', () => {
            renderNextBatch();
        });

        // Reset search button from empty state
        elements.resetSearchBtn.addEventListener('click', () => {
            elements.searchInput.value = '';
            elements.clearSearchBtn.classList.add('hidden');
            state.searchQuery = '';
            state.selectedClubs = new Set(programRegistry.selectableIds);
            ProgramRegistry.clearSavedSelection();
            updateFilterChipsUI();
            applyFiltersAndSort();
            elements.searchInput.focus();
        });

        // Floating Back to Top Button
        if (elements.backToTopBtn) {
            window.addEventListener('scroll', () => {
                if (window.scrollY > 400) {
                    elements.backToTopBtn.classList.remove('hidden');
                } else {
                    elements.backToTopBtn.classList.add('hidden');
                }
            }, { passive: true });

            elements.backToTopBtn.addEventListener('click', () => {
                window.scrollTo({ top: 0, behavior: 'smooth' });
            });
        }

        // Keyboard Shortcuts: '/' to focus search, 'Escape' to clear
        document.addEventListener('keydown', (e) => {
            if (e.key === '/' && document.activeElement !== elements.searchInput) {
                e.preventDefault();
                elements.searchInput.focus();
                elements.searchInput.select();
            } else if (e.key === 'Escape' && document.activeElement === elements.searchInput) {
                if (elements.searchInput.value) {
                    elements.searchInput.value = '';
                    elements.clearSearchBtn.classList.add('hidden');
                    state.searchQuery = '';
                    applyFiltersAndSort();
                } else {
                    elements.searchInput.blur();
                }
            }
        });
    }

    // Initialize
    setupEvents();
    loadData();
})();
