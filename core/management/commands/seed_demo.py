"""Load demo content: exhibitor companies (current edition) with logos from estilo/Empresas,
and one organizer + one company user for trying the panels.
"""

from django.conf import settings
from django.core.files import File
from django.core.management.base import BaseCommand

from accounts.models import User
from core.models import EventSettings
from crm.models import Company, CompanyContact, CompanyDocumentation, Sector

LOGOS_DIR = settings.BASE_DIR / 'estilo' / 'Empresas'

# (logo file, company name, sector)
COMPANIES = [
    ('Accenture.jpg', 'Accenture', Sector.CONSULTORIA),
    ('ACCIONA.png', 'Acciona', Sector.CONSTRUCCION),
    ('AERTEC.jpg', 'AERTEC', Sector.AEROESPACIAL),
    ('AIRBUS.jpg', 'Airbus', Sector.AEROESPACIAL),
    ('ALTEN logo.jpg', 'ALTEN', Sector.CONSULTORIA),
    ('APPlus.jpg', 'Applus+', Sector.CONSULTORIA),
    ('ATEXIS.jpg', 'ATEXIS', Sector.AEROESPACIAL),
    ('ayesa.jpg', 'Ayesa', Sector.CONSULTORIA),
    ('azvi.jpg', 'Azvi', Sector.CONSTRUCCION),
    ('capgemini.jpg', 'Capgemini', Sector.CONSULTORIA),
    ('carrier.jpg', 'Carrier', Sector.INDUSTRIA),
    ('catec.jpg', 'CATEC', Sector.AEROESPACIAL),
    ('cepsa.jpg', 'Cepsa (Moeve)', Sector.ENERGIA),
    ('cosentino.jpg', 'Cosentino', Sector.INDUSTRIA),
    ('elecnor.jpg', 'Elecnor', Sector.ENERGIA),
    ('EMASESA.jpg', 'EMASESA', Sector.INSTITUCION),
    ('galgus.jpg', 'Galgus', Sector.IT),
    ('HILTI.jpg', 'Hilti', Sector.CONSTRUCCION),
    ('hitachi.jpg', 'Hitachi', Sector.INDUSTRIA),
    ('Huawei.jpg', 'Huawei', Sector.IT),
    ('indra.jpg', 'Indra', Sector.IT),
    ('ineco.jpg', 'Ineco', Sector.CONSULTORIA),
    ('inerco.jpg', 'Inerco', Sector.CONSULTORIA),
    ('minsait.jpg', 'Minsait', Sector.IT),
    ('ntt.jpg', 'NTT DATA', Sector.IT),
    ('Schneider.jpg', 'Schneider Electric', Sector.ENERGIA),
    ('SII.jpg', 'SII', Sector.CONSULTORIA),
    ('skylife.jpg', 'Skylife Engineering', Sector.AEROESPACIAL),
    ('tragsa.jpg', 'Tragsa', Sector.CONSTRUCCION),
    ('valeo.jpg', 'Valeo', Sector.INDUSTRIA),
    ('Wood.jpg', 'Wood', Sector.ENERGIA),
    ('COIAE.png', 'COIAE', Sector.INSTITUCION),
    ('defensa.jpg', 'Ministerio de Defensa', Sector.INSTITUCION),
]

DEMO_PASSWORD = 'esiem-demo-2027'


class Command(BaseCommand):
    help = 'Carga datos de demostración (empresas y usuarios de prueba).'

    def handle(self, *args, **options):
        # Demo companies are created in the current edition (the year of the event date).
        event = EventSettings.load()

        created = 0
        for logo_name, name, sector in COMPANIES:
            company, is_new = Company.objects.get_or_create(
                name=name, edition=event.year, defaults={'sector': sector, 'status': Company.Status.CONFIRMED},
            )
            created += is_new
            doc, _ = CompanyDocumentation.objects.get_or_create(company=company)
            logo_path = LOGOS_DIR / logo_name
            if not doc.logo and logo_path.exists():
                with logo_path.open('rb') as fh:
                    doc.logo.save(logo_path.name, File(fh), save=True)

        organizer, is_new = User.objects.get_or_create(
            username='organizador@esiem.es',
            defaults={'email': 'organizador@esiem.es', 'first_name': 'Equipo', 'last_name': 'Organizador', 'is_staff_admin': True},
        )
        if is_new:
            organizer.set_password(DEMO_PASSWORD)
            organizer.save()

        demo_company = Company.objects.get(name='Airbus', edition=event.year)
        company_user, is_new = User.objects.get_or_create(
            username='empresa@demo.es',
            defaults={'email': 'empresa@demo.es', 'first_name': 'Usuario', 'last_name': 'Demo', 'is_company': True, 'company': demo_company},
        )
        if is_new:
            company_user.set_password(DEMO_PASSWORD)
            company_user.save()
        CompanyContact.objects.get_or_create(
            company=demo_company, email='empresa@demo.es',
            defaults={'name': 'Usuario Demo', 'position': 'RRHH', 'is_primary': True},
        )

        self.stdout.write(self.style.SUCCESS(f'Datos de demostración cargados ({created} empresas nuevas).'))
        self.stdout.write(f'  Organizador: organizador@esiem.es / {DEMO_PASSWORD}')
        self.stdout.write(f'  Empresa:     empresa@demo.es / {DEMO_PASSWORD}')
        self.stdout.write(f'  Clave de invitación: {event.invitation_key}')
