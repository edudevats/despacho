// SAT Accounting App - Custom JavaScript

// Initialize any custom functionality here
document.addEventListener('DOMContentLoaded', function () {
    console.log('SAT Accounting App initialized');

    // Add active class to current navigation link
    const currentPath = window.location.pathname;
    const navLinks = document.querySelectorAll('.sidebar .nav-link');

    navLinks.forEach(link => {
        if (link.getAttribute('href') === currentPath) {
            link.classList.add('active');
        }
    });
});
