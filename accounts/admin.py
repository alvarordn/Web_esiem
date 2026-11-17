from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class EsiemUserAdmin(UserAdmin):
    list_display = ['username', 'email', 'get_full_name', 'company', 'is_company', 'is_staff_admin']
    list_filter = ['is_company', 'is_staff_admin', 'is_superuser']
    fieldsets = UserAdmin.fieldsets + (
        ('ESIEM', {'fields': ('is_company', 'is_staff_admin', 'company')}),
    )
