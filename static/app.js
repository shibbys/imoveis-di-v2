// ── Scraping live updates ─────────────────────────────────────────────────────

function startScrapingLog() {
    var source = new EventSource('/scraping/stream');
    var statusEl = document.getElementById('scraping-live-status');

    source.onmessage = function (e) {
        if (!e.data || !e.data.trim()) return; // keepalive ping
        var msg;
        try { msg = JSON.parse(e.data); } catch (_) { return; }

        _handleScrapingEvent(msg);

        if (msg.type === 'done') {
            source.close();
            var statusDiv = document.getElementById('scraping-status');
            if (statusDiv) {
                var parts = msg.total_found + ' encontrados';
                if (msg.total_new)     parts += ' &middot; +' + msg.total_new + ' novos';
                if (msg.total_updated) parts += ' &middot; ~' + msg.total_updated + ' atualizados';
                if (msg.total_removed) parts += ' &middot; -' + msg.total_removed + ' removidos';
                parts += ' &middot; ' + msg.duration + 's';
                statusDiv.innerHTML = '<span class="text-gray-400">' + parts + '</span>';
                setTimeout(function () { statusDiv.innerHTML = ''; }, 8000);
            }
        }
    };

    source.onerror = function () { source.close(); };
}

function _handleScrapingEvent(msg) {
    var base = msg.base;

    if (msg.type === 'site_start') {
        // Show spinner in the status cell of this row
        var statusCell = document.getElementById('site-status-' + base);
        if (statusCell) statusCell.innerHTML = _scrapingSpinner();
    }

    else if (msg.type === 'base_done') {
        // Reload the entire row from the server with fresh DB data
        htmx.ajax('GET', '/configuracoes/site-row/' + base, {
            target: '#site-group-' + base,
            swap: 'outerHTML',
        });
    }
}

function _scrapingSpinner() {
    return '<svg class="animate-spin h-3.5 w-3.5 text-blue-400 inline" fill="none" viewBox="0 0 24 24">'
        + '<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>'
        + '<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 22 6.477 22 12h-4z"></path>'
        + '</svg>';
}


// ── Sort table by column ──────────────────────────────────────────────────────

// Sort table by column. Called from th onclick handlers.
function sortBy(field) {
    var sf = document.getElementById('sort-field');
    var sd = document.getElementById('sort-dir');
    if (!sf || !sd) return;
    var prev = sf.value;
    var prevDir = sd.value;
    sf.value = field;
    sd.value = (prev === field && prevDir === 'asc') ? 'desc' : 'asc';
    document.getElementById('filter-form').requestSubmit();
}

// Highlight the selected row when a detail panel is opened.
document.addEventListener('htmx:beforeRequest', function (e) {
    var el = e.detail.elt;
    if (el && el.hasAttribute && el.hasAttribute('data-imovel-row')) {
        document.querySelectorAll('[data-imovel-row]').forEach(function (r) {
            r.style.removeProperty('background-color');
        });
        el.style.backgroundColor = '#dbeafe'; // tailwind blue-100
    }
});

// Image carousel
function initCarousel(id) {
    var container = document.getElementById(id);
    if (!container) return;
    var imgs = container.querySelectorAll('img');
    var current = 0;
    var show = function (i) {
        imgs.forEach(function (img, idx) {
            img.style.display = idx === i ? 'block' : 'none';
        });
        var counter = document.getElementById('carousel-counter-' + id.replace('carousel-', ''));
        if (counter) counter.textContent = (i + 1) + '/' + imgs.length;
    };
    show(0);
    var prev = container.querySelector('.carousel-prev');
    var next = container.querySelector('.carousel-next');
    if (prev) prev.addEventListener('click', function () {
        current = (current - 1 + imgs.length) % imgs.length;
        show(current);
    });
    if (next) next.addEventListener('click', function () {
        current = (current + 1) % imgs.length;
        show(current);
    });
}

// After any detail-panel swap, sync the row's status dropdown to match
// (handles quick-action status changes without needing OOB table row updates).
document.addEventListener('htmx:afterSwap', function (e) {
    // Start SSE when the scraping trigger response is swapped into #scraping-status.
    if (e.target.id === 'scraping-status' && document.getElementById('scraping-live-status')) {
        startScrapingLog();
    }

    if (e.target.id === 'detalhe-panel') {
        var detail = e.target.querySelector('[data-imovel-id]');
        if (!detail) return;
        var id = detail.getAttribute('data-imovel-id');
        var status = detail.getAttribute('data-status');
        var row = document.getElementById('imovel-' + id);
        if (!row) return;
        var sel = row.querySelector('select[name=status]');
        if (sel && sel.value !== status) sel.value = status;
    }
    // Re-init carousel when the detail panel loads
    var carousel = e.target.querySelector('[data-carousel]');
    if (carousel) initCarousel(carousel.id);
});
