// FGCU Traffic System - Main JavaScript

// Simple loading animation for navigation cards
document.addEventListener('DOMContentLoaded', function() {
    const cards = document.querySelectorAll('.nav-card');
    cards.forEach((card, index) => {
        card.style.opacity = '0';
        card.style.transform = 'translateY(20px)';
        setTimeout(() => {
            card.style.transition = 'all 0.4s ease';
            card.style.opacity = '1';
            card.style.transform = 'translateY(0)';
        }, index * 100);
    });
});
