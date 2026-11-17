from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count, Max, Q
from django.http import FileResponse
from django.utils import timezone
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
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
    CompanyListSerializer,
    CompanyPortalSerializer,
    CompanySerializer,
    ContactSerializer,
    DocumentationSerializer,
    EmailHistorySerializer,
    LogEntrySerializer,
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
        before = {name: getattr(company, name) for name in serializer.validated_data}
        serializer.save()
        if self.request.user.is_organizer:
            return
        # Let the organizers know in the Bitácora when a company edits its own data.
        changed = [
            str(Company._meta.get_field(name).verbose_name)
            for name, old in before.items() if getattr(company, name) != old
        ]
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
