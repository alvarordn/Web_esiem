import datetime
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import models
from django.utils import timezone

# Day schedule of ESIEM 2026 (esiem.es), used as the starting point for the new edition.
DEFAULT_PROGRAMME = """09:30 | Recepción de las empresas expositoras
10:15 | Apertura de la zona de stands
10:45 | Mesa redonda A
12:00 | Mesa redonda B
13:00 | Comida (tres turnos, hasta las 16:00)
15:00 | Continúan las visitas a stands y las presentaciones de empresa · Mesa redonda C
16:15 | Mesa redonda D
17:30 | Clausura de la jornada"""


def default_event_date():
    return datetime.datetime(2027, 3, 11, 10, 0, tzinfo=ZoneInfo(settings.TIME_ZONE))


def current_edition():
    """Year of the current ESIEM edition: the year of EventSettings.event_date. Default for the
    `edition` field of every CRM record; changing the event date to another year starts a new
    edition (earlier records stay in the database but the site and the CRM stop showing them).
    Read-only on purpose: it also runs as a field default inside old migrations."""
    event_date = EventSettings.objects.filter(pk=1).values_list('event_date', flat=True).first()
    return timezone.localtime(event_date or default_event_date()).year


class EventSettings(models.Model):
    """Singleton with the current edition's configuration, editable from the Django admin."""

    event_date = models.DateTimeField(
        'fecha y hora del evento',
        default=default_event_date,
        help_text='Su año es la edición de ESIEM: al cambiarla a otro año empieza una edición nueva '
                  '(las empresas y registros de años anteriores se conservan, pero dejan de mostrarse) '
                  'y los objetivos se copian del año anterior con los mismos días de antelación.',
    )
    venue = models.CharField('lugar', max_length=200, default='ETSi, Universidad de Sevilla')
    invitation_key = models.CharField(
        'clave común de invitación',
        max_length=60,
        default='ESIEM-EXPOSITOR-2027',
        help_text='Clave que las empresas deben introducir para registrarse.',
    )
    director_letter = models.TextField('carta del director', blank=True)
    director_signature = models.CharField('firma de la carta', max_length=200, blank=True)
    programme = models.TextField(
        'programa de la jornada',
        default=DEFAULT_PROGRAMME,
        blank=True,
        help_text='Una actividad por línea con el formato «HH:MM | Actividad».',
    )
    participation_fee = models.CharField('coste de participación', max_length=120, default='1.500 € + IVA')
    payment_instructions = models.TextField(
        'instrucciones de pago',
        blank=True,
        help_text='Datos para la transferencia o el talón (titular, IBAN, concepto…). Se muestran en el formulario de participación.',
    )

    class Meta:
        verbose_name = 'configuración del evento'
        verbose_name_plural = 'configuración del evento'

    def __str__(self):
        return self.edition_name

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @property
    def event_day(self):
        """Local date of the event."""
        return timezone.localtime(self.event_date).date()

    @property
    def year(self):
        """The ESIEM edition, taken from the event date."""
        return self.event_day.year

    @property
    def edition_name(self):
        return f'ESIEM {self.year}'

    @property
    def programme_items(self):
        """[(time, activity)] parsed from the programme text."""
        items = []
        for line in self.programme.splitlines():
            if not line.strip():
                continue
            time, sep, activity = line.partition('|')
            items.append((time.strip(), activity.strip()) if sep else ('', line.strip()))
        return items
