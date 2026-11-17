from django.contrib import admin

from .models import (
    Company,
    CompanyContact,
    CompanyDocumentation,
    CRMNote,
    EmailHistory,
    EventAttendee,
    Objective,
    OrganizationLogEntry,
)


class ContactInline(admin.TabularInline):
    model = CompanyContact
    extra = 0


class AttendeeInline(admin.TabularInline):
    model = EventAttendee
    extra = 0


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ['name', 'edition', 'cif', 'sector', 'status', 'stand_number']
    list_filter = ['edition', 'status', 'sector']
    search_fields = ['name', 'cif', 'contacts__email']
    inlines = [ContactInline, AttendeeInline]


@admin.register(CRMNote)
class CRMNoteAdmin(admin.ModelAdmin):
    list_display = ['created_at', 'edition', 'company', 'author', 'kind']
    list_filter = ['edition', 'kind']
    search_fields = ['company__name', 'text']
    readonly_fields = ['created_at']


@admin.register(EmailHistory)
class EmailHistoryAdmin(admin.ModelAdmin):
    list_display = ['sent_at', 'edition', 'company', 'subject', 'sender', 'template', 'manual']
    list_filter = ['edition']
    search_fields = ['company__name', 'subject']
    readonly_fields = ['edition', 'company', 'sender', 'subject', 'body', 'recipients', 'template', 'manual', 'sent_at']


@admin.register(Objective)
class ObjectiveAdmin(admin.ModelAdmin):
    list_display = ['title', 'edition', 'deadline', 'days_before_event', 'done']
    list_filter = ['edition', 'done']
    search_fields = ['title']
    readonly_fields = ['days_before_event']  # computed from the deadline (current edition)


@admin.register(OrganizationLogEntry)
class OrganizationLogEntryAdmin(admin.ModelAdmin):
    list_display = ['created_at', 'edition', 'objective', 'author']
    list_filter = ['edition', 'objective']
    search_fields = ['text', 'objective__title']
    readonly_fields = ['created_at']


@admin.register(CompanyDocumentation)
class CompanyDocumentationAdmin(admin.ModelAdmin):
    list_display = ['company', 'edition', 'updated_at']
    list_filter = ['edition']
    search_fields = ['company__name']
