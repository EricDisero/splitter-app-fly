from django.urls import path
from django.http import HttpResponse

from . import views

def robots_txt(request):
    return HttpResponse("User-agent: *\nDisallow: /\n", content_type="text/plain")

urlpatterns = [
    path("", views.HomePage.as_view(), name="home"),
    path("robots.txt", robots_txt),
    #path("setting/", views.SettingsPage.as_view(), name="setting"),
    path("split/", views.SplitFile.as_view(), name="split"),
    path("upload_audio/", views.UploadFile.as_view(), name="upload_audio"),
    path("validate_keygen/", views.ValidateKeygen.as_view(), name="validate_keygen"),
    path("download/", views.DownloadFile.as_view(), name="download"),
    path("cleanup_s3/", views.CleanupS3View.as_view(), name="cleanup_s3"),
    path("logout/", views.LogoutView.as_view(), name="logout"),
]