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
