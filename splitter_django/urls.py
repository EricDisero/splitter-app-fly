"""
URL configuration for splitter_django project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
import os
from django.http import HttpResponse
from django.contrib import admin
from django.urls import path
from django.urls import re_path
from django.urls import include
from django.views.generic import RedirectView

from django.conf import settings
from django.conf.urls.static import static

def acme_challenge(request, challenge_file):
    """Serve ACME challenge files for Let's Encrypt."""
    challenge_dir = '/var/www/html/.well-known/acme-challenge'
    try:
        with open(os.path.join(challenge_dir, challenge_file), 'r') as f:
            content = f.read()
        return HttpResponse(content, content_type='text/plain')
    except FileNotFoundError:
        return HttpResponse("File not found", status=404)

urlpatterns = [
    re_path(r'^\.well-known/acme-challenge/(?P<challenge_file>.+)$', acme_challenge, name='acme_challenge'),
    path('admin/', admin.site.urls),
    path('', include('splitter.urls')),
    path('', RedirectView.as_view(url='home/', permanent=False))
    
] + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
