// HTMX configuration
document.addEventListener("DOMContentLoaded", () => {
    // Auto-submit filter forms on change
    document.querySelectorAll(".auto-filter").forEach(el => {
        el.addEventListener("change", () => {
            el.closest("form").requestSubmit();
        });
    });
});

// Image carousel
function initCarousel(id) {
    const container = document.getElementById(id);
    if (!container) return;
    const imgs = container.querySelectorAll("img");
    let current = 0;
    const show = (i) => {
        imgs.forEach((img, idx) => img.style.display = idx === i ? "block" : "none");
    };
    show(0);
    container.querySelector(".carousel-prev")?.addEventListener("click", () => {
        current = (current - 1 + imgs.length) % imgs.length;
        show(current);
    });
    container.querySelector(".carousel-next")?.addEventListener("click", () => {
        current = (current + 1) % imgs.length;
        show(current);
    });
}

// Re-init carousel after HTMX swaps
document.addEventListener("htmx:afterSwap", (e) => {
    const carousel = e.target.querySelector("[data-carousel]");
    if (carousel) initCarousel(carousel.id);
});
