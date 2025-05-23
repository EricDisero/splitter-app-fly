from django.urls import reverse
from django.shortcuts import redirect
from .utils import is_access_valid, check_ghl_access, get_current_user
from django.utils import timezone
from datetime import timedelta
import logging

logger = logging.getLogger("general_logger")

class LicenseMiddleware:
    """Middleware to ensure access validation across the application"""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Skip access check for these paths
        exempt_paths = [
            reverse('validate_keygen'),  # Keep the same URL name
            reverse('home'),
            '/admin/',
            '/.well-known/',
            '/static/',
        ]

        # Check if the current path is exempt
        path = request.path
        if any(path.startswith(exempt) for exempt in exempt_paths):
            return self.get_response(request)

        # For all other paths, verify access
        if not is_access_valid(request):
            return redirect('home')

        return self.get_response(request)

from django.http import HttpResponse

class BlockBotMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.blocked_agents = [
            'Googlebot', 'bingbot', 'YandexBot', 'AhrefsBot',
            'MJ12bot', 'SemrushBot', 'DotBot', 'Baiduspider',
            'PetalBot', 'crawler', 'python-requests'
        ]

    def __call__(self, request):
        user_agent = request.META.get("HTTP_USER_AGENT", "")
        if any(bot.lower() in user_agent.lower() for bot in self.blocked_agents):
            return HttpResponse("Blocked bot", status=403)
        return self.get_response(request)
