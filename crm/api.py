import smtplib

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count, Max, Q
from django.db.models.functions import Lower
from django.http import FileResponse
from django.utils import timezone
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.models import EventSettings, current_edition

from . import credentials as credentials_mod
from . import emailing, materials
from .models import (
    Company,
    CompanyContact,
    CompanyDocumentation,
    CRMNote,
    EventAttendee,
    Objective,
    OrganizationLogEntry,
)
from .permissions import IsOrganizer, IsOrganizerOrCompanyUser
from .serializers import (
    AttendeeSerializer,
    BulkEmailSerializer,
    CompanyListSerializer,
    CompanyPortalSerializer,
    CompanySerializer,
    ContactSerializer,
    DocumentationSerializer,
    EmailHistorySerializer,
    LogEntrySerializer,
    MailingCompanySerializer,
    NoteSerializer,
    ObjectiveSerializer,
    SendEmailSerializer,
)


EMAIL_KIND_LABELS = {
    'acceptance': 'Correo de aceptación',
    'rejection': 'Correo de rechazo',
    'summary': 'Correo de seguimiento',
    'attendees': 'Correo de solicitud de asistentes',
    'dossier': 'Correo de solicitud de materiales',
}

# CompanyDocumentation file fields and how the Bitácora names them.
FILE_LABELS = {'dossier': 'dossier', 'logo': 'logotipo', 'advert': 'anuncio', 'banner': 'diseño de la platabanda'}


# Sections a company confirms as final from its private area: the Company field holding the date,
# and how the Bitácora names them.
CONFIRMABLE_SECTIONS = {
    'attendees': ('attendees_confirmed_at', 'las personas que asistirán al evento'),
    'materials': ('materials_confirmed_at', 'el dossier y el material del stand'),
}


def ensure_section_open(user, company, section):
    """Company users can't change a section they already confirmed (organizers always can)."""
    field, label = CONFIRMABLE_SECTIONS[section]
    if not user.is_organizer and Company.objects.filter(pk=company.pk, **{f'{field}__isnull': False}).exists():
        raise PermissionDenied(f'Ya has confirmado {label}: no se pueden modificar. '
                               'Si necesitas algún cambio, contacta con la organización.')


class CompanyViewSet(viewsets.ModelViewSet):
    """The "Ficha 360º". Company users can only read and edit the public profile of their own company."""

    permission_classes = [IsOrganizerOrCompanyUser]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_permissions(self):
        if self.action in ('create', 'destroy', 'emails', 'send_email', 'email_template', 'portal_credentials',
                           'materials_zip', 'all_materials_zip'):
            return [IsOrganizer()]
        return super().get_permissions()

    def get_queryset(self):
        user = self.request.user
        qs = Company.objects.current().prefetch_related('contacts')
        if self.action == 'list':
            # Progress columns of the CRM overview (attendees and materials).
            qs = qs.select_related('documentation').annotate(attendee_count=Count('attendees', distinct=True))
        if not user.is_organizer:
            return qs.filter(pk=user.company_id)
        search = self.request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(cif__icontains=search) | Q(contacts__email__icontains=search)).distinct()
        return qs

    def get_serializer_class(self):
        if self.action == 'list':
            return CompanyListSerializer
        return CompanySerializer if self.request.user.is_organizer else CompanyPortalSerializer

    def perform_update(self, serializer):
        company = serializer.instance
        if self.request.user.is_organizer:
            serializer.save()
            return
        # Let the organizers know in the Bitácora when a company edits its own data
        # (CompanyPortalSerializer: company fields plus the designated contact).
        keys = list(serializer.validated_data)
        before = serializer.to_representation(company)
        serializer.save()
        after = serializer.to_representation(company)
        changed = [serializer.field_label(key) for key in keys if before.get(key) != after.get(key)]
        if changed:
            CRMNote.objects.create(
                company=company, author=self.request.user, kind=CRMNote.Kind.SYSTEM,
                text=f'La empresa ha actualizado sus datos generales: {", ".join(changed)}.',
            )

    def perform_destroy(self, instance):
        # Contacts, notes, attendees, emails and documentation cascade; the company's portal users
        # (never organizers) and uploaded files must be removed by hand.
        doc = CompanyDocumentation.objects.filter(company=instance).first()
        with transaction.atomic():
            get_user_model().objects.filter(company=instance, is_staff_admin=False, is_superuser=False).delete()
            instance.delete()
        if doc:
            for field_name in FILE_LABELS:
                if getattr(doc, field_name):
                    getattr(doc, field_name).delete(save=False)

    @action(detail=True, methods=['get', 'patch'])
    def documentation(self, request, pk=None):
        company = self.get_object()
        doc, _ = CompanyDocumentation.objects.get_or_create(company=company)
        if request.method == 'PATCH':
            ensure_section_open(request.user, company, 'materials')
            serializer = DocumentationSerializer(doc, data=request.data, partial=True, context={'request': request})
            serializer.is_valid(raise_exception=True)
            data = dict(serializer.validated_data)
            previous = {
                name: (bool(getattr(doc, name)) and getattr(doc, f'{name}_by_organizer'), getattr(doc, f'{name}_confirmed_at'))
                for name in FILE_LABELS
            }
            # Replacing a file removes the previous one from storage.
            for field_name in FILE_LABELS:
                if field_name in data and getattr(doc, field_name):
                    getattr(doc, field_name).delete(save=False)
            serializer.save()
            if not request.user.is_organizer:
                self._log_company_file_changes(company, request.user, data, previous)
            return Response(serializer.data)
        return Response(DocumentationSerializer(doc, context={'request': request}).data)

    @action(detail=True, methods=['post', 'delete'], url_path='confirm-section')
    def confirm_section(self, request, pk=None):
        """{section: attendees|materials}. POST: the company confirms that section as final and can no
        longer change it. DELETE: organizers reopen it so the company can fix something."""
        company = self.get_object()
        section = request.data.get('section') or request.query_params.get('section')
        if section not in CONFIRMABLE_SECTIONS:
            return Response({'section': f'Usa uno de: {", ".join(CONFIRMABLE_SECTIONS)}.'}, status=status.HTTP_400_BAD_REQUEST)
        field, label = CONFIRMABLE_SECTIONS[section]
        user = request.user
        if request.method == 'DELETE':
            if not user.is_organizer:
                raise PermissionDenied('Solo la organización puede reabrir una sección confirmada.')
            if getattr(company, field):
                setattr(company, field, None)
                company.save(update_fields=[field, 'updated_at'])
                CRMNote.objects.create(company=company, author=user, kind=CRMNote.Kind.SYSTEM,
                                       text=f'La organización ha reabierto {label}: la empresa puede volver a modificarlos.')
        else:
            if user.is_organizer:
                raise PermissionDenied('La confirmación la hace la propia empresa desde su área privada.')
            empty = (not company.attendees.exists() if section == 'attendees'
                     else not any(getattr(getattr(company, 'documentation', None), name, None) for name in FILE_LABELS))
            if empty:
                return Response({'detail': f'No hay nada que confirmar todavía en {label}.'}, status=status.HTTP_400_BAD_REQUEST)
            if not getattr(company, field):
                setattr(company, field, timezone.now())
                company.save(update_fields=[field, 'updated_at'])
                CRMNote.objects.create(company=company, author=user, kind=CRMNote.Kind.SYSTEM,
                                       text=f'La empresa ha confirmado {label} como definitivos.')
        return Response(self.get_serializer(company).data)

    @action(detail=True, methods=['get'], url_path='materials-zip')
    def materials_zip(self, request, pk=None):
        """All the materials (catálogo + stand) of one company in a ZIP."""
        company = self.get_object()
        archive = materials.build_zip([company], materials.ALL_FIELDS, f'Material de {company.name}')
        filename = f'{materials.safe_name(company.name)}_material.zip'
        return FileResponse(archive, as_attachment=True, filename=filename, content_type='application/zip')

    @action(detail=False, methods=['get'], url_path='materials-zip')
    def all_materials_zip(self, request):
        """?group=catalogo|stand: that material from every company, one folder per company."""
        group = request.query_params.get('group', '')
        if group not in materials.GROUPS:
            return Response({'group': f'Usa uno de: {", ".join(materials.GROUPS)}.'}, status=status.HTTP_400_BAD_REQUEST)
        title, fields = materials.GROUPS[group]
        companies = Company.objects.current().select_related('documentation').order_by('name')
        archive = materials.build_zip(companies, fields, f'{title} · todas las empresas')
        edition = materials.safe_name(EventSettings.load().edition_name)
        filename = f'{edition}_{group}_{timezone.localdate():%Y-%m-%d}.zip'
        return FileResponse(archive, as_attachment=True, filename=filename, content_type='application/zip')

    @staticmethod
    def _log_company_file_changes(company, user, data, previous):
        """Record in the Bitácora what the company did with files the organizers uploaded for it."""
        for name, label in FILE_LABELS.items():
            from_organizer, confirmed_at = previous[name]
            confirmed = data.get(f'{name}_confirmed')
            if name in data and from_organizer:
                text = f'La empresa ha sustituido el {label} que subió la organización.'
            elif confirmed is not None and confirmed != bool(confirmed_at):
                text = (f'La empresa ha confirmado el {label} que subió la organización.' if confirmed
                        else f'La empresa ha retirado la confirmación del {label} que subió la organización.')
            else:
                continue
            CRMNote.objects.create(company=company, author=user, kind=CRMNote.Kind.SYSTEM, text=text)

    @action(detail=True, methods=['get'])
    def emails(self, request, pk=None):
        company = self.get_object()
        return Response(EmailHistorySerializer(company.emails.select_related('sender'), many=True).data)

    def create(self, request, *args, **kwargs):
        # Companies only enter the CRM through the public participation form.
        return Response({'detail': 'Las empresas se dan de alta con el formulario de participación.'},
                        status=status.HTTP_405_METHOD_NOT_ALLOWED)

    @action(detail=True, methods=['get'], url_path='email-template')
    def email_template(self, request, pk=None):
        company = self.get_object()
        name = request.query_params.get('name') or emailing.DEFAULT_TEMPLATES.get(request.query_params.get('kind'), '')
        try:
            extra, credentials = None, None
            if emailing.uses_credentials(name):
                # The credentials the company already has (resending them), or fresh ones that are
                # only applied when the acceptance is sent.
                credentials = credentials_mod.current_credentials(company) or {
                    'username': credentials_mod.suggest_username(company),
                    'password': credentials_mod.generate_password()}
                extra = {'usuario': credentials['username'], 'contraseña': credentials['password']}
            data = emailing.render_template(name, company, request, extra)
        except FileNotFoundError:
            return Response({'detail': 'Plantilla no encontrada.'}, status=status.HTTP_404_NOT_FOUND)
        return Response({**data, 'credentials': credentials})

    @action(detail=True, methods=['get'], url_path='portal-credentials')
    def portal_credentials(self, request, pk=None):
        """The «Acceso al portal» box: the company's credentials, or a proposal while it isn't accepted.
        `locked` once it is accepted: they can only be resent, not changed. `password_known` is False
        for an accepted company whose password wasn't kept: a new one can be set by resending."""
        company = self.get_object()
        current = credentials_mod.current_credentials(company)
        data = current or {'username': credentials_mod.suggest_username(company),
                           'password': credentials_mod.generate_password()}
        return Response({**data, 'locked': company.status == Company.Status.CONFIRMED,
                         'password_known': current is not None})

    @action(detail=True, methods=['post'], url_path='send-email')
    def send_email(self, request, pk=None):
        company = self.get_object()
        serializer = SendEmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        allowed = {email.lower() for email in company.contacts.values_list('email', flat=True)}
        recipients = [r.lower() for r in data['recipients']]
        unknown = [r for r in recipients if r not in allowed]
        if unknown:
            return Response(
                {'recipients': [f'No es un contacto de la empresa: {", ".join(unknown)}']},
                status=status.HTTP_400_BAD_REQUEST,
            )

        kind = data['kind']
        if kind == 'acceptance':
            # The portal account in the email is created when the acceptance is sent (or registered).
            # Once accepted, the credentials are fixed: resending can't change them.
            if company.status == Company.Status.CONFIRMED:
                user = credentials_mod.company_portal_user(company)
                current = credentials_mod.current_credentials(company)
                if (user and data.get('username') != user.username) or (
                        current and data.get('password') != current['password']):
                    return Response({'detail': 'La empresa ya está aceptada: su usuario y contraseña no se pueden cambiar.'},
                                    status=status.HTTP_400_BAD_REQUEST)
            problem = credentials_mod.username_problem(company, data.get('username', ''))
            if problem or len(data.get('password', '')) < 8:
                return Response({'detail': problem or 'Falta la contraseña del portal: carga de nuevo la plantilla de aceptación.'},
                                status=status.HTTP_400_BAD_REQUEST)

        message = (company, request.user, recipients, data['subject'], data['body'], data['template'])
        if data['manual']:
            record, failed = emailing.log_email(*message, manual=True), {}
        elif not settings.EMAIL_AUTOMATIC_SENDING:
            return Response({'detail': 'El envío automático está desactivado. Usa «Abrir en Outlook».'},
                            status=status.HTTP_400_BAD_REQUEST)
        else:
            record, failed = emailing.send_company_email(*message)
        if record:
            # Every send is also written to the CRM log. First line is the summary, the message follows a blank line.
            header = (f'{EMAIL_KIND_LABELS[kind]} enviado{" desde Outlook" if data["manual"] else ""} '
                      f'a {", ".join(record.recipients)}.')
            header += self._apply_decision(company, kind, data)
            CRMNote.objects.create(company=company, author=request.user, kind=CRMNote.Kind.EMAIL,
                                   text=f'{header}\n\nAsunto: {record.subject}\n\n{record.body}')
        if failed:
            errors = '; '.join(f'{address}: {reason}' for address, reason in failed.items())
            prefix = f'Enviado a {", ".join(record.recipients)}. ' if record else ''
            return Response({'detail': f'{prefix}No se pudo enviar a {errors}.'}, status=status.HTTP_502_BAD_GATEWAY)
        return Response(EmailHistorySerializer(record).data, status=status.HTTP_201_CREATED)

    @staticmethod
    def _apply_decision(company, kind, data):
        """Acceptance/rejection emails decide the company's status. Returns the text for the Bitácora."""
        if kind == 'acceptance':
            with transaction.atomic():
                user = credentials_mod.grant_access(company, data['username'], data['password'])
                company.status = Company.Status.CONFIRMED
                company.save(update_fields=['status', 'updated_at'])
            return f' La empresa pasa a «Aceptada» y tiene acceso al portal con el usuario «{user.username}».'
        if kind == 'rejection':
            company.status = Company.Status.DECLINED
            company.save(update_fields=['status', 'updated_at'])
            revoked = credentials_mod.revoke_access(company)
            return ' La empresa pasa a «Rechazada».' + (' Se ha desactivado su acceso al portal.' if revoked else '')
        return ''


class CompanyScopedViewSet(viewsets.ModelViewSet):
    """Filters by ?company= and keeps company users inside their own company. Only companies of the
    current edition are reachable."""

    permission_classes = [IsOrganizerOrCompanyUser]

    def get_queryset(self):
        user = self.request.user
        qs = self.queryset.filter(company__edition=current_edition())
        if not user.is_organizer:
            qs = qs.filter(company_id=user.company_id)
        company_id = self.request.query_params.get('company')
        if company_id:
            qs = qs.filter(company_id=company_id)
        return qs

    def _save(self, serializer):
        user = self.request.user
        if not user.is_organizer:
            serializer.save(company=user.company)
        elif serializer.instance is None and 'company' not in serializer.validated_data:
            raise serializers.ValidationError({'company': 'Indica la empresa.'})
        elif serializer.validated_data.get('company', serializer.instance and serializer.instance.company).edition != current_edition():
            raise serializers.ValidationError({'company': 'La empresa es de una edición anterior de ESIEM.'})
        else:
            serializer.save()

    perform_create = _save
    perform_update = _save


class AttendeeViewSet(CompanyScopedViewSet):
    queryset = EventAttendee.objects.all()
    serializer_class = AttendeeSerializer

    def perform_create(self, serializer):
        # At most Company.max_attendees people per company (raised per company in the Django admin).
        user = self.request.user
        company_id = user.company_id if not user.is_organizer else getattr(serializer.validated_data.get('company'), 'pk', None)
        company = Company.objects.filter(pk=company_id).first()  # fresh: the limit is edited in the DB
        if company:
            ensure_section_open(user, company, 'attendees')
            if company.attendees.count() >= company.max_attendees:
                raise serializers.ValidationError({'non_field_errors': [
                    f'Se ha alcanzado el máximo de {company.max_attendees} personas asistentes para esta empresa.']})
        self._save(serializer)

    # Once the company confirmed its attendees, it can't edit or remove them either.
    def perform_update(self, serializer):
        ensure_section_open(self.request.user, serializer.instance.company, 'attendees')
        self._save(serializer)

    def perform_destroy(self, instance):
        ensure_section_open(self.request.user, instance.company, 'attendees')
        instance.delete()


class ContactViewSet(CompanyScopedViewSet):
    queryset = CompanyContact.objects.all()
    serializer_class = ContactSerializer
    permission_classes = [IsOrganizer]


class NoteViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    """CRM log: notes can be added and read, never edited or deleted."""

    serializer_class = NoteSerializer
    permission_classes = [IsOrganizer]

    def get_queryset(self):
        qs = CRMNote.objects.select_related('author').filter(company__edition=current_edition())
        company_id = self.request.query_params.get('company')
        return qs.filter(company_id=company_id) if company_id else qs

    def perform_create(self, serializer):
        if serializer.validated_data['company'].edition != current_edition():
            raise serializers.ValidationError({'company': 'La empresa es de una edición anterior de ESIEM.'})
        serializer.save(author=self.request.user)


class ObjectiveViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, mixins.UpdateModelMixin,
                       viewsets.GenericViewSet):
    """Event-organization goals of the «Registro» tab."""

    serializer_class = ObjectiveSerializer
    permission_classes = [IsOrganizer]
    http_method_names = ['get', 'post', 'patch', 'head', 'options']

    def get_queryset(self):
        # Meta.ordering is ignored in aggregate (GROUP BY) queries, so order explicitly.
        return (Objective.objects.current().annotate(entry_count=Count('entries'), last_entry_at=Max('entries__created_at'))
                .order_by('deadline', 'title'))

    def perform_create(self, serializer):
        objective = serializer.save()
        OrganizationLogEntry.objects.create(objective=objective, author=self.request.user,
                                            text='Objetivo creado.')

    def perform_update(self, serializer):
        was_done = serializer.instance.done
        objective = serializer.save()
        if objective.done != was_done:
            OrganizationLogEntry.objects.create(
                objective=objective, author=self.request.user,
                text='Objetivo marcado como completado.' if objective.done else 'Objetivo reabierto.',
            )


class LogEntryViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    """Organization diary: entries can be added and read, never edited or deleted."""

    serializer_class = LogEntrySerializer
    permission_classes = [IsOrganizer]

    def get_queryset(self):
        qs = OrganizationLogEntry.objects.current().select_related('author', 'objective')
        objective_id = self.request.query_params.get('objective')
        return qs.filter(objective_id=objective_id) if objective_id else qs

    def perform_create(self, serializer):
        objective = serializer.validated_data.get('objective')
        if objective and objective.edition != current_edition():
            raise serializers.ValidationError({'objective': 'El objetivo es de una edición anterior de ESIEM.'})
        serializer.save(author=self.request.user)


class EmailTemplateListView(viewsets.ViewSet):
    permission_classes = [IsAuthenticated, IsOrganizer]

    def list(self, request):
        return Response({'templates': emailing.list_templates(), 'defaults': emailing.DEFAULT_TEMPLATES})

    @action(detail=False, methods=['get'])
    def general(self, request):
        """?name=: the template for a message to several companies at once (the «Contactos» view):
        event placeholders filled, company ones replaced by a general wording."""
        name = request.query_params.get('name', '')
        try:
            template = emailing.read_template(name)
            credentials = emailing.uses_credentials(name)
        except FileNotFoundError:
            return Response({'detail': 'Plantilla no encontrada.'}, status=status.HTTP_404_NOT_FOUND)
        return Response({'name': name, 'credentials': credentials,
                         'subject': emailing.fill_general_placeholders(template['subject'], request),
                         'body': emailing.fill_general_placeholders(template['body'], request)})


class MailingViewSet(viewsets.ViewSet):
    """«Contactos» view (organizers): the contacts of every company of the current edition, with what
    each company has done so the panel can filter them, and one email to the selected contacts.

    It goes out as a single message with every recipient in Bcc, so the text is the same for all
    (no company placeholders). Each company still gets its own EmailHistory record and Bitácora note
    with its own recipients, as if it had been sent from its own composer."""

    permission_classes = [IsAuthenticated, IsOrganizer]

    def list(self, request):
        companies = (Company.objects.current().select_related('documentation').prefetch_related('contacts')
                     .annotate(attendee_count=Count('attendees', distinct=True)).order_by(Lower('name')))
        return Response(MailingCompanySerializer(companies, many=True).data)

    def _message(self, request):
        """(data, {company: [addresses]}, subject, body) for the selected contacts."""
        serializer = BulkEmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        leftover = emailing.company_placeholders_in(data['subject'] + data['body'])
        if leftover:
            raise serializers.ValidationError({'body': (
                f'El correo va a todas las empresas a la vez, en copia oculta: quita {", ".join(leftover)} '
                'o cámbialo por un texto general.')})
        ids = set(data['contacts'])
        contacts = list(CompanyContact.objects.filter(pk__in=ids, company__edition=current_edition())
                        .select_related('company').order_by(Lower('company__name'), '-is_primary', 'name'))
        if len(contacts) != len(ids):
            raise serializers.ValidationError({'contacts': 'Algún contacto ya no existe o es de una edición anterior. Recarga la página.'})
        by_company = {}
        for contact in contacts:
            addresses = by_company.setdefault(contact.company, [])
            if contact.email.lower() not in addresses:
                addresses.append(contact.email.lower())
        subject = emailing.fill_general_placeholders(data['subject'], request)
        body = emailing.fill_general_placeholders(data['body'], request)
        return data, by_company, subject, body

    @staticmethod
    def _all_addresses(by_company):
        return list(dict.fromkeys(address for addresses in by_company.values() for address in addresses))

    @action(detail=False, methods=['post'])
    def preview(self, request):
        _, by_company, subject, body = self._message(request)
        return Response({'subject': subject, 'body': body, 'recipients': self._all_addresses(by_company),
                         'companies': [{'id': c.id, 'name': c.name, 'recipients': addresses}
                                       for c, addresses in by_company.items()]})

    @action(detail=False, methods=['post'])
    def send(self, request):
        data, by_company, subject, body = self._message(request)
        if not data['manual']:
            if not settings.EMAIL_AUTOMATIC_SENDING:
                return Response({'detail': 'El envío automático está desactivado. Usa «Abrir en Outlook».'},
                                status=status.HTTP_400_BAD_REQUEST)
            try:
                emailing.send_bcc_email(self._all_addresses(by_company), subject, body)
            except (smtplib.SMTPException, OSError) as exc:
                return Response({'detail': f'No se ha enviado: {emailing.describe_smtp_error(exc)}.'},
                                status=status.HTTP_502_BAD_GATEWAY)
        others = len(by_company) - 1
        together = f' en copia oculta junto con otras {others} empresa(s)' if others else ' en copia oculta'
        for company, addresses in by_company.items():
            record = emailing.log_email(company, request.user, addresses, subject, body, data['template'], manual=data['manual'])
            header = (f'{EMAIL_KIND_LABELS[data["kind"]]} enviado{" desde Outlook" if data["manual"] else ""} '
                      f'a {", ".join(addresses)}{together} (desde «Contactos»).')
            CRMNote.objects.create(company=company, author=request.user, kind=CRMNote.Kind.EMAIL,
                                   text=f'{header}\n\nAsunto: {record.subject}\n\n{record.body}')
        return Response({'companies': len(by_company), 'recipients': len(self._all_addresses(by_company))},
                        status=status.HTTP_201_CREATED)
