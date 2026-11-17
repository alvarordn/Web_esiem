"""Server-side .txt email templates and sending through the configured SMTP mailer.

A template is a UTF-8 .txt file in settings.EMAIL_TEMPLATES_DIR. If its first
line starts with "Asunto:" that line is the subject; the rest is the body.
Placeholders such as {nombre_empresa} are replaced when the template is loaded,
and the admin can then edit the text freely before sending.
"""

import re
import smtplib
from pathlib import Path

from django.conf import settings
from django.core.mail import EmailMessage
from django.urls import reverse

from core.models import EventSettings

from .models import EmailHistory

# Default draft per email kind (the composer's «Tipo de correo»). Invitations are sent outside
# the app; «acceptance» and «rejection» also decide the company's status (see crm.api.send_email).
DEFAULT_TEMPLATES = {
    'acceptance': 'aceptacion.txt',
    'rejection': 'rechazo.txt',
    'summary': 'seguimiento.txt',
    'attendees': 'solicitud_asistentes.txt',
    'dossier': 'solicitud_materiales.txt',
}
DECISION_KINDS = ('acceptance', 'rejection')

_SAFE_NAME = re.compile(r'^[\w\- ]+\.txt$')


def templates_dir():
    return Path(settings.EMAIL_TEMPLATES_DIR)


def list_templates():
    return sorted(p.name for p in templates_dir().glob('*.txt'))


def template_path(name):
    if not _SAFE_NAME.match(name or ''):
        raise FileNotFoundError(name)
    path = templates_dir() / name
    if not path.is_file():
        raise FileNotFoundError(name)
    return path


def template_context(company, request=None):
    event = EventSettings.load()
    registration_path = reverse('accounts:register')
    login_path = reverse('accounts:login')
    contact = company.primary_contact
    return {
        'nombre_empresa': company.name,
        'enlace_registro': request.build_absolute_uri(registration_path) if request else registration_path,
        'enlace_acceso': request.build_absolute_uri(login_path) if request else login_path,
        'clave_registro': event.invitation_key,
        'nombre_evento': event.edition_name,
        'fecha_evento': event.event_date.strftime('%d/%m/%Y') if event.event_date else 'por confirmar',
        'lugar_evento': event.venue,
        'stand': company.stand_number or 'por asignar',
        'nombre_contacto': contact.name if contact and contact.name else 'equipo',
    }


CREDENTIAL_PLACEHOLDERS = ('{usuario}', '{contraseña}')


def uses_credentials(name):
    """True if the template includes the portal username/password (the acceptance email)."""
    text = template_path(name).read_text(encoding='utf-8')
    return any(p in text for p in CREDENTIAL_PLACEHOLDERS)


def render_template(name, company, request=None, extra=None):
    """`extra` adds placeholders, e.g. the {usuario} / {contraseña} of the acceptance email."""
    text = template_path(name).read_text(encoding='utf-8')
    context = {**template_context(company, request), **(extra or {})}
    # Unknown {placeholders} are left as-is rather than raising.
    text = re.sub(r'\{(\w+)\}', lambda m: str(context.get(m.group(1), m.group(0))), text)
    subject, body = '', text
    first_line, _, rest = text.partition('\n')
    if first_line.lower().startswith('asunto:'):
        subject, body = first_line.split(':', 1)[1].strip(), rest.lstrip('\n')
    return {'name': name, 'subject': subject, 'body': body}


def describe_smtp_error(exc):
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return 'el servidor de correo ha rechazado el usuario o la contraseña'
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        return 'el servidor de correo ha rechazado el destinatario (¿falta la contraseña SMTP en .env?)'
    if isinstance(exc, smtplib.SMTPException):
        return f'error del servidor de correo: {exc}'
    return f'no se pudo conectar con el servidor de correo: {exc}'


def send_company_email(company, sender, recipients, subject, body, template=''):
    """Send one message per recipient (so addresses aren't exposed to each other).

    Returns (history record or None, {address: error}). Only delivered addresses are logged.
    """
    sent, failed = [], {}
    for address in recipients:
        try:
            EmailMessage(subject=subject, body=body, to=[address]).send()
        except (smtplib.SMTPException, OSError) as exc:
            failed[address] = describe_smtp_error(exc)
        else:
            sent.append(address)
    record = log_email(company, sender, sent, subject, body, template) if sent else None
    return record, failed


def log_email(company, sender, recipients, subject, body, template='', manual=False):
    return EmailHistory.objects.create(
        company=company,
        sender=sender,
        subject=subject,
        body=body,
        recipients=list(recipients),
        template=template,
        manual=manual,
    )
