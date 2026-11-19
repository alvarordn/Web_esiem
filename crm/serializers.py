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
            'signer_name', 'signer_capacity', 'max_attendees',
            'attendees_confirmed_at', 'materials_confirmed_at', 'portal_access',
        ]
        # The attendee limit is changed in the Django admin / the DB, not through the panel;
        # the confirmations through the `confirm-section` endpoint.
        read_only_fields = ['max_attendees', 'attendees_confirmed_at', 'materials_confirmed_at']

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
    """What a company user may change about its own company: everything it sent in the
    participation form (company data, contract signer and the designated contact, i.e. the primary
    contact), to fix mistakes. The organizers' fields (status, stand, public summary) stay read-only."""

    # Designated contact of the participation form = the primary CompanyContact.
    CONTACT_FIELDS = {'contact_name': 'name', 'contact_email': 'email', 'contact_phone': 'phone'}
    CONTACT_LABELS = {'contact_name': 'persona de contacto', 'contact_email': 'email de contacto',
                      'contact_phone': 'teléfono de contacto'}
    contact_name = serializers.CharField(max_length=200, required=False, write_only=True)
    contact_email = serializers.EmailField(required=False, write_only=True)
    contact_phone = serializers.CharField(max_length=40, required=False, allow_blank=True, write_only=True)

    class Meta(CompanySerializer.Meta):
        fields = [name for name in CompanySerializer.Meta.fields if name != 'portal_access'] + [
            'contact_name', 'contact_email', 'contact_phone']
        read_only_fields = ['status', 'stand_number', 'summary', 'max_attendees',
                            'attendees_confirmed_at', 'materials_confirmed_at']

    def to_representation(self, company):
        data = super().to_representation(company)
        contact = company.primary_contact
        for key, attr in self.CONTACT_FIELDS.items():
            data[key] = getattr(contact, attr) if contact else ''
        return data

    def validate_cif(self, value):
        from accounts.forms import normalize_cif

        cif = normalize_cif(value)
        if not cif:
            raise serializers.ValidationError('Introduce el CIF de la empresa.')
        others = Company.objects.filter(edition=self.instance.edition).exclude(pk=self.instance.pk).exclude(cif='')
        if any(normalize_cif(other) == cif for other in others.values_list('cif', flat=True)):
            raise serializers.ValidationError('Ya hay otra empresa con ese CIF en esta edición.')
        return cif

    def validate_contact_email(self, value):
        value = value.lower()
        contact = self.instance.primary_contact
        clash = self.instance.contacts.filter(email__iexact=value)
        if contact:
            clash = clash.exclude(pk=contact.pk)
        if clash.exists():
            raise serializers.ValidationError('Ya hay otro contacto de la empresa con ese email.')
        return value

    def update(self, company, validated_data):
        contact_data = {attr: validated_data.pop(key)
                        for key, attr in self.CONTACT_FIELDS.items() if key in validated_data}
        company = super().update(company, validated_data)
        if contact_data:
            contact = company.primary_contact
            if contact:
                for attr, value in contact_data.items():
                    setattr(contact, attr, value)
                contact.is_primary = True
                contact.save()
            elif contact_data.get('email'):
                CompanyContact.objects.create(company=company, is_primary=True, **contact_data)
        return company

    def field_label(self, key):
        if key in self.CONTACT_LABELS:
            return self.CONTACT_LABELS[key]
        return str(Company._meta.get_field(key).verbose_name)


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
            'attendee_count', 'max_attendees', 'dossier_state', 'logo_state', 'advert_state', 'banner_state',
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
            'email', 'phone', 'role', 'eats_at_event', 'has_allergies', 'allergies',
        ]
        # Company users never send it (it's forced server-side); organizers must.
        extra_kwargs = {'company': {'required': False}}

    def validate(self, attrs):
        # Allergies only make sense for someone who eats at the event, and then must be described.
        def value(name):
            if name in attrs:
                return attrs[name]
            return getattr(self.instance, name) if self.instance else EventAttendee._meta.get_field(name).default

        if not value('eats_at_event'):
            attrs['has_allergies'] = False
        if not value('has_allergies'):
            attrs['allergies'] = ''
        elif not value('allergies').strip():
            raise serializers.ValidationError({'allergies': 'Indica qué alergias tiene.'})
        return attrs


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


class MailingCompanySerializer(CompanyListSerializer):
    """«Contactos» view: each company with what it has done (to filter by) and its contacts."""

    contacts = ContactSerializer(many=True, read_only=True)

    class Meta(CompanyListSerializer.Meta):
        fields = CompanyListSerializer.Meta.fields + [
            'max_attendees', 'attendees_confirmed_at', 'materials_confirmed_at', 'contacts']


# Emails the «Contactos» view sends to several companies at once. Acceptance / rejection decide a
# company's status, so they stay in each company's own composer.
BULK_EMAIL_KINDS = ['summary', 'attendees', 'dossier']


class BulkEmailSerializer(serializers.Serializer):
    contacts = serializers.ListField(child=serializers.IntegerField(), allow_empty=False)
    subject = serializers.CharField(max_length=255)
    body = serializers.CharField()
    template = serializers.CharField(required=False, allow_blank=True, default='')
    kind = serializers.ChoiceField(choices=BULK_EMAIL_KINDS, default='summary')
    # Already sent from the organizer's own mail client: only log it, don't send.
    manual = serializers.BooleanField(default=False)

    def validate(self, attrs):
        from .emailing import CREDENTIAL_PLACEHOLDERS

        if any(p in attrs['subject'] + attrs['body'] for p in CREDENTIAL_PLACEHOLDERS):
            raise serializers.ValidationError(
                'El usuario y la contraseña del portal solo se envían desde la ficha de cada empresa (correo de aceptación).')
        return attrs


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
