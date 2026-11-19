from django.conf import settings
from django.db import models
from django.db.models.functions import Lower

from core.models import EventSettings, current_edition


class Sector(models.TextChoices):
    IT = 'it', 'IT y Software'
    CONSULTORIA = 'consultoria', 'Consultoría'
    ENERGIA = 'energia', 'Energía'
    AEROESPACIAL = 'aeroespacial', 'Aeroespacial'
    INDUSTRIA = 'industria', 'Industria y Fabricación'
    CONSTRUCCION = 'construccion', 'Construcción e Infraestructuras'
    INSTITUCION = 'institucion', 'Instituciones y Colegios Profesionales'
    OTROS = 'otros', 'Otros'


class EditionQuerySet(models.QuerySet):
    def current(self):
        """Records of the current ESIEM edition (the year of the event date)."""
        return self.filter(edition=current_edition())


class EditionModel(models.Model):
    """Every CRM record carries the ESIEM edition (year) it belongs to, taken from the event date
    when created. Records of past editions are kept, but the site and the CRM only use `.current()`."""

    edition = models.PositiveSmallIntegerField('año de ESIEM', default=current_edition, db_index=True)

    objects = EditionQuerySet.as_manager()

    class Meta:
        abstract = True


class Company(EditionModel):
    # Companies sign up through the participation form as «Interesada»; the organizers then accept
    # them (portal user created, credentials emailed) or reject them, see crm.api.send_email.
    class Status(models.TextChoices):
        INTERESTED = 'interested', 'Interesada'
        CONFIRMED = 'confirmed', 'Aceptada'
        DECLINED = 'declined', 'Rechazada'

    # Unique per edition: a company takes part in a new edition by sending the form again.
    name = models.CharField('nombre', max_length=200)
    cif = models.CharField('CIF', max_length=20, blank=True)
    sector = models.CharField(max_length=20, choices=Sector.choices, default=Sector.OTROS)
    website = models.URLField('sitio web', blank=True)
    summary = models.TextField('resumen público', blank=True)
    status = models.CharField('estado', max_length=10, choices=Status.choices, default=Status.INTERESTED)
    stand_number = models.CharField('stand asignado', max_length=20, blank=True)
    # Raised per company from the Django admin / the DB when an exception is agreed.
    max_attendees = models.PositiveSmallIntegerField(
        'máximo de asistentes', default=5,
        help_text='Personas que la empresa puede registrar en «Personas que asistirán al evento».',
    )
    # Set when the company confirms a section as final: from then on it can't change it (the
    # organizers still can, and can reopen it by clearing the date).
    attendees_confirmed_at = models.DateTimeField(
        'asistentes confirmados el', null=True, blank=True,
        help_text='Vacío = la empresa aún puede modificar sus personas asistentes.')
    materials_confirmed_at = models.DateTimeField(
        'material confirmado el', null=True, blank=True,
        help_text='Vacío = la empresa aún puede subir o cambiar el dossier y el material del stand.')

    # Participation form (contract / billing data), filled in on registration.
    address = models.CharField('domicilio', max_length=255, blank=True)
    city = models.CharField('población', max_length=120, blank=True)
    postal_code = models.CharField('código postal', max_length=10, blank=True)
    phone = models.CharField('teléfono', max_length=40, blank=True)
    fax = models.CharField(max_length=40, blank=True)
    signer_name = models.CharField('firmante del contrato', max_length=200, blank=True)
    signer_capacity = models.CharField('calidad en la que firma', max_length=150, blank=True)
    # Portal password sent in the acceptance email, kept so organizers can resend it (on request).
    portal_password = models.CharField('contraseña del portal', max_length=128, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'empresa'
        ordering = [Lower('name')]  # case-insensitive regardless of the DB collation
        constraints = [
            models.UniqueConstraint(Lower('name'), 'edition', name='unique_company_name_per_edition'),
        ]

    def __str__(self):
        return self.name

    @property
    def primary_contact(self):
        return self.contacts.filter(is_primary=True).first() or self.contacts.first()


class CompanyContact(EditionModel):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='contacts')
    name = models.CharField('nombre', max_length=200, blank=True)
    email = models.EmailField()
    phone = models.CharField('teléfono', max_length=40, blank=True)
    position = models.CharField('cargo', max_length=120, blank=True)
    is_primary = models.BooleanField('es principal', default=False)

    class Meta:
        verbose_name = 'contacto'
        ordering = ['-is_primary', 'name']
        constraints = [
            models.UniqueConstraint(fields=['company', 'email'], name='unique_contact_email_per_company'),
        ]

    def __str__(self):
        return f'{self.name} <{self.email}>' if self.name else self.email


class CRMNote(EditionModel):
    class Kind(models.TextChoices):
        NOTE = 'note', 'Nota'
        CALL = 'call', 'Llamada'
        EMAIL = 'email', 'Correo'
        MEETING = 'meeting', 'Reunión'
        SYSTEM = 'system', 'Sistema'

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='notes')
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    text = models.TextField('texto')
    kind = models.CharField('tipo de interacción', max_length=10, choices=Kind.choices, default=Kind.NOTE)

    class Meta:
        verbose_name = 'anotación CRM'
        verbose_name_plural = 'anotaciones CRM'
        ordering = ['-created_at']


class Objective(EditionModel):
    """An event-organization goal with a deadline («Registro» tab), independent of the companies.

    `days_before_event` (event date − deadline) is what carries over between editions: moving the
    event date shifts the deadlines of the current edition, and a new edition starts with a copy of
    the previous one's objectives (see crm.signals). `deadline` keeps each edition's actual date."""

    title = models.CharField('objetivo', max_length=255)
    deadline = models.DateField('fecha límite')
    days_before_event = models.IntegerField(
        'días antes del evento', default=0,
        help_text='Días entre la fecha límite y la fecha del evento (negativo si es posterior al evento).',
    )
    done = models.BooleanField('completado', default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'objetivo'
        ordering = ['deadline', 'title']

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        # The offset can only be measured against the current edition's event date.
        event = EventSettings.load()
        if self.edition == event.year:
            self.days_before_event = (event.event_day - self.deadline).days
            if kwargs.get('update_fields') is not None:
                kwargs['update_fields'] = {*kwargs['update_fields'], 'days_before_event'}
        super().save(*args, **kwargs)


class OrganizationLogEntry(EditionModel):
    """Diary of organization actions. Like CRMNote, entries are never edited or deleted."""

    objective = models.ForeignKey(Objective, on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name='entries', verbose_name='objetivo')
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    text = models.TextField('texto')

    class Meta:
        verbose_name = 'anotación de organización'
        verbose_name_plural = 'registro de organización'
        ordering = ['-created_at', '-id']


class EventAttendee(EditionModel):
    """A person a company registers for the event, at most `Company.max_attendees` per company."""

    class Role(models.TextChoices):
        STAND = 'stand', 'Stand'
        SPEAKER = 'speaker', 'Ponente'
        BOTH = 'both', 'Stand y ponente'

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='attendees')
    first_name = models.CharField('nombre', max_length=100)
    last_name = models.CharField('apellidos', max_length=150)
    dni = models.CharField('DNI', max_length=20)
    position = models.CharField('cargo', max_length=120, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField('teléfono', max_length=40, blank=True)
    role = models.CharField('participación', max_length=10, choices=Role.choices, default=Role.STAND)
    # Catering: allergies only apply to people who eat at the event, the text only if they have any.
    eats_at_event = models.BooleanField('come en el evento', default=False)
    has_allergies = models.BooleanField('tiene alergias', default=False)
    allergies = models.CharField('alergias', max_length=255, blank=True)

    class Meta:
        verbose_name = 'asistente'
        ordering = ['last_name', 'first_name']

    def __str__(self):
        return f'{self.first_name} {self.last_name}'


def company_upload_path(instance, filename):
    return f'companies/{instance.company_id}/{filename}'


class CompanyDocumentation(EditionModel):
    company = models.OneToOneField(Company, on_delete=models.CASCADE, related_name='documentation')
    # Two groups in the panel: catálogo (logo, dossier, advert) and stand (banner = the stand's platabanda).
    dossier = models.FileField('dossier (PDF/DOC)', upload_to=company_upload_path, blank=True)
    logo = models.FileField('logotipo', upload_to=company_upload_path, blank=True)
    advert = models.FileField('anuncio', upload_to=company_upload_path, blank=True)
    banner = models.FileField('platabanda', upload_to=company_upload_path, blank=True)
    # Files uploaded by an organizer on behalf of the company: the company can replace them or
    # confirm them. Uploading a new file resets both flags (a company upload is never "by organizer").
    dossier_by_organizer = models.BooleanField('dossier subido por la organización', default=False)
    dossier_confirmed_at = models.DateTimeField('dossier confirmado por la empresa', null=True, blank=True)
    logo_by_organizer = models.BooleanField('logotipo subido por la organización', default=False)
    logo_confirmed_at = models.DateTimeField('logotipo confirmado por la empresa', null=True, blank=True)
    advert_by_organizer = models.BooleanField('anuncio subido por la organización', default=False)
    advert_confirmed_at = models.DateTimeField('anuncio confirmado por la empresa', null=True, blank=True)
    banner_by_organizer = models.BooleanField('platabanda subida por la organización', default=False)
    banner_confirmed_at = models.DateTimeField('platabanda confirmada por la empresa', null=True, blank=True)
    power_outlets = models.PositiveSmallIntegerField('enchufes', default=0)
    chairs = models.PositiveSmallIntegerField('sillas', default=0)
    needs_wifi = models.BooleanField('conexión Wi-Fi', default=False)
    stand_notes = models.TextField('otras necesidades del stand', blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'dossier y stand'
        verbose_name_plural = 'dossiers y stands'


class EmailHistory(EditionModel):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='emails')
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    subject = models.CharField('asunto', max_length=255)
    body = models.TextField('cuerpo')
    recipients = models.JSONField('destinatarios', default=list)
    template = models.CharField('plantilla utilizada', max_length=120, blank=True)
    # True when the organizer sent it from their own mail client (Outlook) and only registered it here.
    manual = models.BooleanField('enviado desde el correo del organizador', default=False)
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'correo enviado'
        verbose_name_plural = 'historial de correos'
        ordering = ['-sent_at']
