from django.contrib import admin

from .models import EventSettings


@admin.register(EventSettings)
class EventSettingsAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return not EventSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
