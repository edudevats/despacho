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

    // Initialize Tom Select for product/material dropdowns
    const productSelects = document.querySelectorAll('select[name="product_id"], select[name="material_id"]');
    if (productSelects.length > 0 && typeof TomSelect !== 'undefined') {
        productSelects.forEach(select => {
            new TomSelect(select, {
                create: false,
                sortField: {
                    field: "text",
                    direction: "asc"
                },
                placeholder: "-- Seleccionar --",
                allowEmptyOption: true
            });
        });
    }
});
