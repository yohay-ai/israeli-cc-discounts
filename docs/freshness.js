(function () {
    'use strict';

    const element = document.getElementById('dataFreshness');
    if (!element) return;

    function formatTimestamp(value) {
        const timestamp = new Date(value);
        if (Number.isNaN(timestamp.getTime())) return null;
        return new Intl.DateTimeFormat('he-IL', {
            dateStyle: 'short',
            timeStyle: 'short',
        }).format(timestamp);
    }

    function renderFreshness(value) {
        const timestamp = new Date(value);
        const formatted = formatTimestamp(value);
        if (!formatted) throw new Error('Invalid freshness timestamp');

        const ageHours = Math.max(0, (Date.now() - timestamp.getTime()) / 3600000);
        element.classList.remove('is-stale', 'is-outdated');
        if (ageHours >= 168) {
            element.classList.add('is-outdated');
            element.textContent = `הנתונים לא עודכנו יותר משבוע · עדכון אחרון: ${formatted}`;
        } else if (ageHours >= 48) {
            element.classList.add('is-stale');
            element.textContent = `ייתכן שהנתונים אינם עדכניים · עדכון אחרון: ${formatted}`;
        } else {
            element.textContent = `עדכון נתונים אחרון: ${formatted}`;
        }
    }

    async function loadFreshness() {
        const sources = ['data/data_freshness.json', '/api/info'];
        for (const source of sources) {
            try {
                const response = await fetch(source);
                if (!response.ok) continue;
                const data = await response.json();
                const value = data.published_at || data.metadata?.all_combined?.last_updated;
                if (value) {
                    renderFreshness(value);
                    return;
                }
            } catch (error) {
                // Try the next source.
            }
        }
        element.textContent = 'מועד עדכון הנתונים אינו זמין כרגע';
        element.classList.add('is-stale');
    }

    loadFreshness();
}());
