import os

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.staticfiles import finders
from django.core.exceptions import PermissionDenied
from django.shortcuts import render
from django.urls import reverse

from .models import Company, CRMNote, Sector


def _static_version(path):
    """Modification time of a static file, used as a ?v= query string."""
    found = finders.find(path)
    return int(os.path.getmtime(found)) if found else ''


@login_required
def panel(request):
    """Private area. Organizers get the full CRM; companies get the same tabs for their own company."""
    user = request.user
    if not user.is_organizer and not (user.is_company and user.company_id):
        raise PermissionDenied('Tu cuenta no está asociada a ninguna empresa.')
    if not user.is_organizer and not user.has_portal_access:
        raise PermissionDenied('Tu acceso corresponde a una edición anterior de ESIEM.')
    initial_company = request.GET.get('empresa') if user.is_organizer else user.company_id
    return render(request, 'crm/panel.html', {
        # Cache-busting: browsers would otherwise keep running an outdated panel.js after a change.
        'panel_js_version': _static_version('js/panel.js'),
        'panel_config': {
            'apiRoot': reverse('crm:api-root'),
            'isOrganizer': user.is_organizer,
            'automaticEmail': settings.EMAIL_AUTOMATIC_SENDING,
            'companyId': int(initial_company) if str(initial_company or '').isdigit() else None,
            'sectors': Sector.choices,
            'statuses': Company.Status.choices,
            'noteKinds': [c for c in CRMNote.Kind.choices if c[0] != CRMNote.Kind.SYSTEM],
        },
    })

