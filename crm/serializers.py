from pathlib import Path

from django.utils import timezone
from rest_framework import serializers

from core.models import current_edition

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


class ContactSerializer(serializers.ModelSerializer):
    class Meta:
        model = CompanyContact
        fields = ['id', 'company', 'name', 'email', 'phone', 'position', 'is_primary']
        # Uniqueness per company is enforced by the DB constraint and checked in validate().
        validators = []

    def validate(self, attrs):
        company = attrs.get('company') or self.instance.company
        email = attrs.get('email', self.instance.email if self.instance else '')
        clash = CompanyContact.objects.filter(company=company, email__iexact=email)
        if self.instance:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise serializers.ValidationError({'email': 'Esta empresa ya tiene un contacto con ese email.'})
        return attrs

    def save(self, **kwargs):
        contact = super().save(**kwargs)
        if contact.is_primary:
            contact.company.contacts.exclude(pk=contact.pk).update(is_primary=False)
        return contact


class CompanySerializer(serializers.ModelSerializer):
    sector_display = serializers.CharField(source='get_sector_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    contacts = ContactSerializer(many=True, read_only=True)
    # Organizers only: the portal username/password given in the acceptance email, to resend them.
    portal_access = serializers.SerializerMethodField()

    class Meta:
        model = Company
        fields = [
            'id', 'name', 'cif', 'sector', 'sector_display', 'website', 'summary',
            'status', 'status_display', 'stand_number', 'contacts', 'updated_at',
            'address', 'city', 'postal_code', 'phone', 'fax',
            'signer_name', 'signer_capacity','portal_access',
        ]

    def validate_name(self, value):
        # The DB constraint is case-insensitive and per edition; report it as a form error.
        value = ' '.join(value.split())
        edition = self.instance.edition if self.instance else current_edition()
        clash = Company.objects.filter(edition=edition, name__iexact=value)
        if self.instance:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise serializers.ValidationError('Ya hay otra empresa con ese nombre en esta edición.')
        return value

    def get_portal_access(self, company):
        from .credentials import company_portal_user  # avoid an import cycle at module load

        user = company_portal_user(company)
        if not user:
            return None
        return {'username': user.username, 'password': company.portal_password, 'active': user.is_active}


class CompanyPortalSerializer(CompanySerializer):
    """What a company user may change about its own company: website and the contract/billing
    data. Identity (name, CIF, sector) and the organizers' fields (status, stand, public summary)
    stay read-only."""

    class Meta(CompanySerializer.Meta):
        fields = [name for name in CompanySerializer.Meta.fields if name != 'portal_access']
        read_only_fields = ['name', 'cif', 'sector', 'status', 'stand_number', 'summary']


def file_state(company, field_name):
    """'done' if the company provided the file (or confirmed the organizers' one),
    'pending' if the organizers uploaded it and the company hasn't confirmed it yet, else 'missing'."""
    doc = getattr(company, 'documentation', None)
    if not doc or not getattr(doc, field_name):
        return 'missing'
    if getattr(doc, f'{field_name}_by_organizer') and not getattr(doc, f'{field_name}_confirmed_at'):
        return 'pending'
    return 'done'


class CompanyListSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    attendee_count = serializers.IntegerField(read_only=True, default=0)
    dossier_state = serializers.SerializerMethodField()
    logo_state = serializers.SerializerMethodField()
    advert_state = serializers.SerializerMethodField()
    banner_state = serializers.SerializerMethodField()

    class Meta:
        model = Company
        fields = [
            'id', 'name', 'sector', 'status', 'status_display',
            'attendee_count', 'dossier_state', 'logo_state', 'advert_state', 'banner_state',
        ]

    def get_dossier_state(self, company):
        return file_state(company, 'dossier')

    def get_logo_state(self, company):
        return file_state(company, 'logo')

    def get_advert_state(self, company):
        return file_state(company, 'advert')

    def get_banner_state(self, company):
        return file_state(company, 'banner')


class NoteSerializer(serializers.ModelSerializer):
    author_name = serializers.SerializerMethodField()
    kind_display = serializers.CharField(source='get_kind_display', read_only=True)

    class Meta:
        model = CRMNote
        fields = ['id', 'company', 'author_name', 'created_at', 'text', 'kind', 'kind_display']
        read_only_fields = ['created_at']

    def get_author_name(self, note):
        return str(note.author) if note.author else 'Sistema'


class ObjectiveSerializer(serializers.ModelSerializer):
    entry_count = serializers.IntegerField(read_only=True, default=0)
    last_entry_at = serializers.DateTimeField(read_only=True, default=None)

    class Meta:
        model = Objective
        fields = ['id', 'title', 'deadline', 'days_before_event', 'done', 'entry_count', 'last_entry_at']
        read_only_fields = ['days_before_event']  # computed from the deadline on save


class LogEntrySerializer(serializers.ModelSerializer):
    author_name = serializers.SerializerMethodField()
    objective_title = serializers.CharField(source='objective.title', read_only=True, default='')

    class Meta:
        model = OrganizationLogEntry
        fields = ['id', 'objective', 'objective_title', 'author_name', 'created_at', 'text']
        read_only_fields = ['created_at']

    def get_author_name(self, entry):
        return str(entry.author) if entry.author else 'Sistema'


class AttendeeSerializer(serializers.ModelSerializer):
    class Meta:
        model = EventAttendee
        fields = [
            'id', 'company', 'first_name', 'last_name', 'dni', 'position',
            'email', 'phone', 'dietary_needs',
        ]
        # Company users never send it (it's forced server-side); organizers must.
        extra_kwargs = {'company': {'required': False}}


ALLOWED_EXTENSIONS = {
    'dossier': {'.pdf', '.doc', '.docx'},
    'logo': {'.png', '.svg', '.jpg', '.jpeg', '.webp'},
    'advert': {'.pdf', '.png', '.jpg', '.jpeg', '.webp', '.svg'},
    'banner': {'.png', '.jpg', '.jpeg', '.webp', '.svg', '.pdf'},
}


class DocumentationSerializer(serializers.ModelSerializer):
    stand_number = serializers.CharField(source='company.stand_number', read_only=True)
    # Write-only: the company ticks/unticks "this is the file we want to use" on organizer uploads.
    dossier_confirmed = serializers.BooleanField(write_only=True, required=False)
    logo_confirmed = serializers.BooleanField(write_only=True, required=False)
    advert_confirmed = serializers.BooleanField(write_only=True, required=False)
    banner_confirmed = serializers.BooleanField(write_only=True, required=False)

    class Meta:
        model = CompanyDocumentation
        fields = [
            'dossier', 'logo', 'advert', 'banner',
            'dossier_by_organizer', 'dossier_confirmed_at', 'dossier_confirmed',
            'logo_by_organizer', 'logo_confirmed_at', 'logo_confirmed',
            'advert_by_organizer', 'advert_confirmed_at', 'advert_confirmed',
            'banner_by_organizer', 'banner_confirmed_at', 'banner_confirmed',
            'power_outlets', 'chairs', 'needs_wifi', 'stand_notes', 'stand_number', 'updated_at',
        ]
        read_only_fields = [
            'dossier_by_organizer', 'dossier_confirmed_at',
            'logo_by_organizer', 'logo_confirmed_at',
            'advert_by_organizer', 'advert_confirmed_at',
            'banner_by_organizer', 'banner_confirmed_at',
        ]

    def validate(self, attrs):
        for field_name, extensions in ALLOWED_EXTENSIONS.items():
            upload = attrs.get(field_name)
            if upload and Path(upload.name).suffix.lower() not in extensions:
                raise serializers.ValidationError(
                    {field_name: f'Formato no permitido. Usa: {", ".join(sorted(extensions))}.'}
                )
        user = self.context['request'].user
        for field_name in ALLOWED_EXTENSIONS:
            key = f'{field_name}_confirmed'
            if key not in attrs:
                continue
            if user.is_organizer:
                raise serializers.ValidationError({key: 'Solo la empresa puede confirmar el archivo.'})
            if field_name in attrs:
                raise serializers.ValidationError({key: 'No se puede confirmar un archivo a la vez que se sube otro.'})
            doc = self.instance
            if not (doc and getattr(doc, field_name) and getattr(doc, f'{field_name}_by_organizer')):
                raise serializers.ValidationError({key: 'Solo se pueden confirmar archivos subidos por la organización.'})
        return attrs

    def update(self, instance, validated_data):
        user = self.context['request'].user
        for field_name in ALLOWED_EXTENSIONS:
            confirmed = validated_data.pop(f'{field_name}_confirmed', None)
            if field_name in validated_data:
                setattr(instance, f'{field_name}_by_organizer', user.is_organizer)
                setattr(instance, f'{field_name}_confirmed_at', None)
            elif confirmed is not None:
                setattr(instance, f'{field_name}_confirmed_at', timezone.now() if confirmed else None)
        return super().update(instance, validated_data)


class EmailHistorySerializer(serializers.ModelSerializer):
    sender_name = serializers.SerializerMethodField()

    class Meta:
        model = EmailHistory
        fields = ['id', 'subject', 'body', 'recipients', 'template', 'manual', 'sent_at', 'sender_name']

    def get_sender_name(self, email):
        return str(email.sender) if email.sender else ''


class SendEmailSerializer(serializers.Serializer):
    recipients = serializers.ListField(child=serializers.EmailField(), allow_empty=False)
    subject = serializers.CharField(max_length=255)
    body = serializers.CharField()
    template = serializers.CharField(required=False, allow_blank=True, default='')
    kind = serializers.ChoiceField(choices=['acceptance', 'rejection', 'summary', 'attendees', 'dossier'], default='summary')
    # Acceptance only: the portal credentials written in the email (from the email-template endpoint).
    username = serializers.CharField(required=False, allow_blank=True, default='')
    password = serializers.CharField(required=False, allow_blank=True, default='', trim_whitespace=False)
    # Already sent from the organizer's own mail client: only log it, don't send.
    manual = serializers.BooleanField(default=False)
