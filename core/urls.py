from django.urls import path

from . import views

app_name = 'core'

urlpatterns = [
    path('', views.home, name='home'),
    path('carta/', views.letter, name='letter'),
    path('etsi/', views.etsi, name='etsi'),
    path('esiem/', views.event_info, name='event'),
    path('expositores/', views.exhibitors, name='exhibitors'),
    path('empresas/', views.directory, name='directory'),
    path('catedras/', views.chairs, name='chairs'),
    path('organizadores/', views.organizers, name='organizers'),
    path('siguenos/', views.follow, name='follow'),
    path('legal/<slug:page>/', views.legal, name='legal'),
]
