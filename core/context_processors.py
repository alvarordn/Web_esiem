import os

from django.conf import settings as django_settings
from django.contrib.staticfiles import finders
from django.urls import reverse

from .content import CONTACT_EMAILS, GENERAL_EMAIL, SOCIAL_LINKS
from .models import EventSettings


def event(request):
    settings = EventSettings.load()
    nav = [
        ('core:home', 'Inicio'),
        ('core:letter', 'Carta del director'),
        ('core:etsi', 'ETSi'),
        ('core:event', settings.edition_name),
        ('core:exhibitors', 'Expositores'),
        ('accounts:register', 'Formulario de participación'),
        ('core:directory', 'Empresas'),
        ('core:chairs', 'Cátedras'),
        ('core:organizers', 'Organizadores'),
        ('core:follow', 'Síguenos'),
    ]
    static_export = getattr(django_settings, 'STATIC_EXPORT', False)  # set by manage.py export_static
    if static_export:
        nav = [entry for entry in nav if not entry[0].startswith('accounts:')]
    nav_items = [{'url': reverse(name), 'label': label} for name, label in nav]
    for item in nav_items:
        item['active'] = request.path == item['url']
    return {
        'event': settings, 'static_export': static_export, 'nav_items': nav_items, 'social_links': SOCIAL_LINKS, 'contact_emails': CONTACT_EMAILS, 'general_email': GENERAL_EMAIL,
        # Cache-busting for the stylesheet: browsers would otherwise keep an outdated esiem.css.
        'css_version': _static_version('css/esiem.css'),
    }


def _static_version(path):
    """Modification time of a static file, used as a ?v= query string."""
    found = finders.find(path)
    return int(os.path.getmtime(found)) if found else ''
