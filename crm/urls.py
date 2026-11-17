from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import api, views

app_name = 'crm'

router = DefaultRouter()
router.register('companies', api.CompanyViewSet, basename='company')
router.register('contacts', api.ContactViewSet, basename='contact')
router.register('notes', api.NoteViewSet, basename='note')
router.register('objectives', api.ObjectiveViewSet, basename='objective')
router.register('log-entries', api.LogEntryViewSet, basename='log-entry')
router.register('attendees', api.AttendeeViewSet, basename='attendee')
router.register('email-templates', api.EmailTemplateListView, basename='email-template')

urlpatterns = [
    path('panel/', views.panel, name='panel'),
    path('api/', include(router.urls)),
]
