// Ensure CSRF tokens are included in all HTMX requests
document.body.addEventListener('htmx:configRequest', function(evt) {
    // Get CSRF token from cookie
    const csrftoken = getCookie('csrftoken');
    if (csrftoken) {
        evt.detail.headers['X-CSRFToken'] = csrftoken;
    }
});

// Helper function to get cookies
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}