// ── Scraping live updates ─────────────────────────────────────────────────────

// Global tracking for SSE so we don't duplicate
var _scrapingSource = null;

function startScrapingLog() {
    if (_scrapingSource) {
        _scrapingSource.close();
    }
    _scrapingSource = new EventSource('/scraping/stream');

    _scrapingSource.onmessage = function (e) {
        if (!e.data || !e.data.trim()) return; // keepalive ping
        var msg;
        try { msg = JSON.parse(e.data); } catch (_) { return; }

        _handleScrapingEvent(msg);

        if (msg.type === 'done') {
            _scrapingSource.close();
            _scrapingSource = null;
            document.getElementById('live-log-indicator').classList.remove('bg-green-500');
            document.getElementById('live-log-indicator').classList.add('bg-gray-300');
            
            var statusDiv = document.getElementById('scraping-status');
            var currLabel = document.getElementById('current-running-label');
            if (currLabel) currLabel.textContent = 'Aguardando tarefas...';
            
            if (statusDiv) {
                var parts = msg.total_found + ' encontrados';
                if (msg.total_new)     parts += ' &middot; +' + msg.total_new + ' novos';
                if (msg.total_updated) parts += ' &middot; ~' + msg.total_updated + ' atualizados';
                if (msg.total_removed) parts += ' &middot; -' + msg.total_removed + ' removidos';
                if (msg.duration !== undefined) parts += ' &middot; ' + msg.duration + 's';
                statusDiv.innerHTML = '<span class="text-gray-400">' + parts + '</span>';
                
                // Clear any leftover spinners on the table by hard reloading table body or letting trigger clean it
                document.querySelectorAll('[id^="site-status-"]').forEach(function (e) {
                    if (e.innerHTML.includes('svg')) e.innerHTML = '<span class="text-gray-300">—</span>';
                });
                
                setTimeout(function () { 
                    statusDiv.innerHTML = '<p class="text-gray-400 text-xs" id="current-running-label">Aguardando tarefas...</p>'; 
                    htmx.ajax('GET', '/scraping/last-run', {target: '#last-run-log', swap: 'innerHTML'});
                }, 8000);
            }
        }
    };

    _scrapingSource.onerror = function () { 
        if (_scrapingSource) _scrapingSource.close(); 
        setTimeout(startScrapingLog, 5000); // Reconnect loop if backend drops
        document.getElementById('live-log-indicator').classList.remove('bg-green-500');
        document.getElementById('live-log-indicator').classList.add('bg-gray-300');
    };
    
    document.getElementById('live-log-indicator').classList.remove('bg-gray-300');
    document.getElementById('live-log-indicator').classList.add('bg-green-500');
}

function _appendTerminalLog(text) {
    var cont = document.getElementById('live-terminal-log');
    if (!cont) return;
    
    // Clear initial waiting message
    if (cont.innerHTML.includes('Aguardando tarefas')) {
        cont.innerHTML = '';
    }
    
    var li = document.createElement('li');
    li.textContent = text;
    cont.appendChild(li);
    cont.scrollTop = cont.scrollHeight;
}

function _handleScrapingEvent(msg) {
    var base = msg.base;

    if (msg.type === 'init_state') {
        var state = msg.state;
        
        var cont = document.getElementById('live-terminal-log');
        if (cont && state.logs && state.logs.length > 0) {
            cont.innerHTML = '';
            state.logs.forEach(function(l) { _appendTerminalLog(l); });
        }
        
        if (state.status === 'running') {
            document.getElementById('live-log-indicator').classList.replace('bg-gray-300', 'bg-green-500');
            
            var cl = document.getElementById('current-running-label');
            if (cl && state.label) {
                cl.textContent = state.label;
            }
            
            // Set spinners for pending
            state.pending.forEach(function(p) {
                var c = document.getElementById('site-status-' + p.base);
                if (c && !c.innerHTML.includes('svg')) {
                    c.innerHTML = '<span class="text-xs text-gray-400">Aguardando...</span>';
                }
            });
            // Set spinner for active
            if (state.base && state.base !== 'enrichment') {
                var c = document.getElementById('site-status-' + state.base);
                if (c) c.innerHTML = _scrapingSpinner();
            }
        } else {
            document.getElementById('live-log-indicator').classList.replace('bg-green-500', 'bg-gray-300');
        }
    }
    else if (msg.type === 'terminal_log') {
        _appendTerminalLog(msg.text);
    }
    else if (msg.type === 'site_start') {
        var statusCell = document.getElementById('site-status-' + base);
        if (statusCell) statusCell.innerHTML = _scrapingSpinner();
        var cl = document.getElementById('current-running-label');
        if (cl) cl.textContent = msg.display + ' (' + msg.transaction_type + ')';
        
        var date = new Date();
        var timeStr = date.getHours().toString().padStart(2, '0') + ':' + 
                      date.getMinutes().toString().padStart(2, '0') + ':' + 
                      date.getSeconds().toString().padStart(2, '0');
        _appendTerminalLog('[' + timeStr + '] ' + msg.display + ' (' + msg.transaction_type + ') -> Iniciando...');
    }
    else if (msg.type === 'enrich_start') {
        var statusCell = document.getElementById('site-status-' + base);
        if (statusCell && base !== 'batch') statusCell.innerHTML = _scrapingSpinner();
        var cl = document.getElementById('current-running-label');
        if (cl) cl.textContent = 'Enrichment (' + msg.total + ')';
        
        var date = new Date();
        var timeStr = date.getHours().toString().padStart(2, '0') + ':' + 
                      date.getMinutes().toString().padStart(2, '0') + ':' + 
                      date.getSeconds().toString().padStart(2, '0');
        _appendTerminalLog('[' + timeStr + '] Enrichment (' + msg.total + ' items) -> Iniciando...');
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
    return '<svg class="animate-spin h-3.5 w-3.5 text-yellow-400 inline" fill="none" viewBox="0 0 24 24">'
        + '<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>'
        + '<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 22 6.477 22 12h-4z"></path>'
        + '</svg>';
}

document.addEventListener('DOMContentLoaded', function() {
    if (document.getElementById('scraping-status')) {
        startScrapingLog();
    }
});


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
        if (!_scrapingSource || _scrapingSource.readyState === EventSource.CLOSED) {
            startScrapingLog();
        }
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
