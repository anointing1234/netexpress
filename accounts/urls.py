from django.urls import path,re_path
from django.conf import settings
from django.conf.urls.static import static
from . import views
from django.views.static import serve 
from django.shortcuts import redirect

def redirect_home(request):
    return redirect("/", permanent=True)


urlpatterns = [ 
    path('',views.home_view,name='home'),
    path("home/", redirect_home),
    path('about_us/',views.about_us,name='about_us'),
    path('services/',views.services,name='services'),
    path('tracking/',views.tracking,name='tracking'),
    path('contact/',views.contact,name='contact'),
    re_path(r'^media/(?P<path>.*)$', serve,{'document_root': settings.MEDIA_ROOT}),
    re_path(r'^static/(?P<path>.*)$', serve,{'document_root': settings.STATIC_ROOT}),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)



