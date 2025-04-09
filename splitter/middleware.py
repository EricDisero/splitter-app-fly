from django.urls import reverse
from django.shortcuts import redirect
from .utils import is_license_valid


class LicenseMiddleware:
    """Middleware to ensure license validation across the application"""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Skip license check for these paths
        exempt_paths = [
            reverse('validate_keygen'),  # License validation endpoint
            reverse('home'),  # Home page (which handles license check)
            '/admin/',  # Admin pages
            '/.well-known/',  # Let's Encrypt verification
            '/static/',  # Static files
        ]

        # Check if the current path is exempt
        path = request.path
        if any(path.startswith(exempt) for exempt in exempt_paths):
            return self.get_response(request)

        # For all other paths, verify license
        if not is_license_valid(request):
            # Redirect to home page if no valid license
            return redirect('home')

        # Continue processing if license is valid
        return self.get_response(request)