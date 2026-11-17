from django.http import Http404
from django.shortcuts import render

from crm.models import Company, Sector

from . import content


def _public_companies():
    companies = Company.objects.current().filter(status=Company.Status.CONFIRMED).select_related('documentation')
    result = []
    for company in companies:
        doc = getattr(company, 'documentation', None)
        result.append({
            'name': company.name,
            'sector': company.sector,
            'sectorLabel': company.get_sector_display(),
            'summary': company.summary,
            'website': company.website,
            'logo': doc.logo.url if doc and doc.logo else '',
        })
    return result


def home(request):
    return render(request, 'core/home.html', {
        'home_figures': content.HOME_FIGURES,
        'organizers': content.ORGANIZERS,
        'featured_companies': _public_companies()[:12],
    })


def letter(request):
    return render(request, 'core/letter.html')


def etsi(request):
    return render(request, 'core/etsi.html', {
        'figures': content.ETSI_FIGURES,
        'pars': content.ETSI_PARS,
        'pars_url': content.ETSI_PARS_URL,
        'studies_url': content.ETSI_STUDIES_URL,
        'degrees': content.ETSI_DEGREES,
        'masters': content.ETSI_MASTERS,
        'double_masters': content.ETSI_DOUBLE_MASTERS,
        'doctorates': content.ETSI_DOCTORATES,
    })


def exhibitors(request):
    """Exhibitor information, copied from the old esiem.es/infoexp.php."""
    return render(request, 'core/exhibitors.html', {
        'sections': [('stand', 'Stand'), ('presentacion', 'Presentación'), ('catering', 'Catering'),
                     ('coste', 'Coste'), ('contacto', 'Contacto')],
        'furniture': [('1', 'Repisa de melamina horizontal de 1 × 0,30 m'), ('1', 'Taburete'), ('2', 'Sillas'),
                      ('1', 'Mostrador vitrina de 1 m de ancho con puertas y cerradura')],
        'gallery': [('img/expositores/stand02.jpg', 'Stand para empresas'),
                    ('img/expositores/stand-medidas.svg', 'Medidas del stand'),
                    ('img/expositores/stand04.jpg', 'Vitrina mostrador'),
                    ('img/expositores/stand05.jpg', 'Repisa inclinada')],
    })


def event_info(request):
    return render(request, 'core/event.html')


def directory(request):
    companies = _public_companies()
    used_sectors = {c['sector'] for c in companies}
    return render(request, 'core/directory.html', {
        'companies': companies,
        'sectors': [(value, label) for value, label in Sector.choices if value in used_sectors],
    })


def chairs(request):
    return render(request, 'core/chairs.html', {'chairs': content.CHAIRS, 'chairs_url': content.CHAIRS_URL})


def organizers(request):
    return render(request, 'core/organizers.html', {'organizers': content.ORGANIZERS})


def follow(request):
    return render(request, 'core/follow.html')  # social_links comes from the context processor


LEGAL_PAGES = {
    'aviso-legal': ('Aviso legal', 'core/legal/aviso_legal.html'),
    'privacidad': ('Política de privacidad', 'core/legal/privacidad.html'),
    'cookies': ('Política de cookies', 'core/legal/cookies.html'),
}


def legal(request, page):
    if page not in LEGAL_PAGES:
        raise Http404
    title, template = LEGAL_PAGES[page]
    return render(request, template, {'title': title})
