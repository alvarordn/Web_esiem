"""Institutional content for the public pages (taken from esiem.es). Logos are paths under static/."""

ORGANIZERS = [
    {
        'name': 'ETSi · Universidad de Sevilla',
        'description': 'Escuela Técnica Superior de Ingeniería de Sevilla, sede y organizadora del encuentro.',
        'logo': 'img/etsi.jpg',
        'url': 'https://www.etsi.us.es',
    },
    {
        'name': 'ESTIEM Local Group Seville',
        'description': 'Grupo local de ESTIEM, la asociación europea de estudiantes de Ingeniería Industrial y Organización.',
        'logo': 'img/organizadores/estiem-sevilla.png',
        'url': 'https://www.estiem.org',
    },
    {
        'name': 'EUROAVIA Sevilla',
        'description': 'Sección sevillana de EUROAVIA, la asociación europea de estudiantes de ingeniería aeroespacial.',
        'logo': 'img/organizadores/euroavia-sevilla.png',  # rendered from estilo/Asociaciones/EUROAVIA/Logo Sevilla Extended.ai
        'url': 'https://sevilla.euroavia.eu',
    },
    {
        'name': 'Vantus',
        'description': '',
        'logo': 'img/organizadores/vantus.svg',
        'url': 'https://vantusteam.com/',
    },
]

# From https://etsi.us.es/empresas-practicas/catedras-de-empresas (logos downloaded from that page).
CHAIRS_URL = 'https://etsi.us.es/empresas-practicas/catedras-de-empresas'
_CHAIR = 'https://etsi.us.es/empresas-practicas/catedras'
CHAIRS = [
    {'name': 'Cátedra INERCO', 'logo': 'img/catedras/inerco.png', 'url': f'{_CHAIR}/catedra-inerco'},
    {'name': 'Cátedra ENDESA RED', 'logo': 'img/catedras/endesa-red.png', 'url': f'{_CHAIR}/catedra-endesa-red'},
    {'name': 'Cátedra MP', 'logo': 'img/catedras/mp.png', 'url': f'{_CHAIR}/catedra-mp'},
    {'name': 'Cátedra Aeroespacial AIRBUS GROUP', 'logo': 'img/catedras/airbus.png',
     'url': f'{_CHAIR}/catedra-aeroespacial-airbus-group'},
    {'name': 'Cátedra de Prevención de Riesgos Laborales PRL', 'logo': 'img/catedras/prl.png',
     'url': f'{_CHAIR}/catedra-de-prevencion-de-riesgos-laborales-prl'},
    {'name': 'Cátedra Moeve Energía', 'logo': 'img/catedras/moeve.jpg', 'url': f'{_CHAIR}/catedra-cepsa-energia'},
    {'name': 'Cátedra Alter Technology', 'logo': 'img/catedras/alter-technology.png',
     'url': f'{_CHAIR}/catedra-alter-technology'},
    {'name': 'Cátedra del Agua de EMASESA', 'logo': 'img/catedras/emasesa.png',
     'url': f'{_CHAIR}/catedra-del-agua-de-emasesa'},
    {'name': 'Cátedra Economía Circular', 'logo': 'img/catedras/economia-circular.svg',
     'url': f'{_CHAIR}/catedra-economia-circular'},
    {'name': 'Cátedra de IoT (Internet de las Cosas)', 'logo': 'img/catedras/iot.jpg',
     'url': f'{_CHAIR}/catedra-de-lot-internet-de-las-cosas_'},
    {'name': 'Cátedra de Ingeniería y Modelos de Negocio', 'logo': 'img/catedras/ingenieria-modelos-negocio.jpg',
     'url': f'{_CHAIR}/catedra-de-ingenieria-y-modelos-de-negocio'},
    {'name': 'Cátedra INDRA de Vigilancia Espacial', 'logo': 'img/catedras/indra.png',
     'url': f'{_CHAIR}/catedra-INDRA-Vigilancia-Espacial'},
    {'name': 'Cátedra Hitachi Energy', 'logo': 'img/catedras/hitachi-energy.png',
     'url': f'{_CHAIR}/catedra-hitachi-energy'},
    {'name': 'Cátedra Hitachi Energy PCS', 'logo': 'img/catedras/hitachi-energy-pcs.png',
     'url': f'{_CHAIR}/catedra-hitachi-energy-PCS'},
    {'name': 'Cátedra de Ciberseguridad y Ciberinteligencia BeOneSec', 'logo': 'img/catedras/beonesec.png',
     'url': f'{_CHAIR}/catedra-de-ciberseguridad-y-ciberinteligencia-beonesec'},
    {'name': 'Cátedra Schneider Electric: Digitalización e inteligencia artificial industrial',
     'logo': 'img/catedras/schneider.png', 'url': f'{_CHAIR}/catedra_schneider_electric'},
    {'name': 'Cátedra GHENOVA de proyectos integrados de la Universidad de Sevilla', 'logo': 'img/catedras/ghenova.png',
     'url': f'{_CHAIR}/catedra-ghenova-de-proyectos-integrados-de-la-universidad-de-sevilla'},
    {'name': 'Cátedra Wingenia-Energía', 'logo': 'img/catedras/wingenia.png', 'url': f'{_CHAIR}/catedra-Wingenia-Energia'},
    {'name': 'Cátedra Azvi', 'logo': 'img/catedras/azvi.png', 'url': f'{_CHAIR}/catedra-Azvi'},
    {'name': 'Cátedra Lantania: Ingeniería y Tecnología del Agua', 'logo': 'img/catedras/lantania.jpg',
     'url': f'{_CHAIR}/catedra-lantania'},
]

# Institutional contact, shown in the footer and on the exhibitors page.
# Provisional generic address: confirm the mailbox exists before launch.
GENERAL_EMAIL = 'contacto@esiem.es'

CONTACT_EMAILS = [
    {'label': 'Dirección', 'email': 'direccion-esiem-etsi@us.es'},
    {'label': 'Dudas e información', 'email': GENERAL_EMAIL},
]

# Icons: simple-icons (CC0) in static/img/redes/; `brand` is the CSS background of the icon tile.
SOCIAL_LINKS = [
    {'name': 'Instagram', 'handle': '@esiem_etsi', 'url': 'https://www.instagram.com/esiem_etsi/',
     'icon': 'img/redes/instagram.svg',
     'brand': 'linear-gradient(45deg, #F58529, #DD2A7B 50%, #8134AF 75%, #515BD4)'},
    {'name': 'LinkedIn', 'handle': 'ESIEM', 'url': 'https://www.linkedin.com/company/esiem/',
     'icon': 'img/redes/linkedin.svg', 'brand': '#0A66C2'},
    {'name': 'X (Twitter)', 'handle': '@esiem_etsi', 'url': 'https://x.com/esiem_etsi',
     'icon': 'img/redes/x.svg', 'brand': '#000000'},
]

# Source: Memoria de actividades ETSi 2023-2024 (etsi.us.es); the School was created in December 1963.
ETSI_FIGURES = [
    ('+60', 'años de historia'),
    ('+5.500', 'estudiantes'),
    ('+500', 'profesores'),
    ('761', 'titulados en el curso 2023-24'),
]

# Figures strip on the home page (full labels, 4 items to fill the grid).
HOME_FIGURES = [
    ('+4.000', 'estudiantes potenciales asistentes a la feria'),
    ('+60', 'años de historia de la ETSi'),
    ('+5.500', 'estudiantes en la ETSi'),
    ('+500', 'profesores'),
]

# Academic offer, from https://etsi.us.es/estudios-y-titulaciones (programmes marked "no se oferta" left out).
_STUDIES = 'https://etsi.us.es/estudios-y-titulaciones'
ETSI_STUDIES_URL = _STUDIES
ETSI_PARS_URL = f'{_STUDIES}/programas-academicos-con-recorrido-sucesivo-pars'

# PARS (Programas Académicos con Recorrido Sucesivo): a grado followed by its qualifying máster.
ETSI_PARS = [
    {
        'area': 'Ingeniería Industrial',
        'degree': ('Grado en Ingeniería de Tecnologías Industriales',
                   f'{_STUDIES}/grados/grado-en-ingenieria-de-tecnologias-industriales-plan-2024'),
        'master': ('Máster Universitario en Ingeniería Industrial',
                   f'{_STUDIES}/masteres/master-universitario-en-ingenieria-industrial-plan-2024'),
    },
    {
        'area': 'Ingeniería de Telecomunicación',
        'degree': ('Grado en Ingeniería de las Tecnologías de Telecomunicación',
                   f'{_STUDIES}/grados/grado-en-ingenieria-de-las-tecnologias-de-telecomunicacion'),
        'master': ('Máster Universitario en Ingeniería de Telecomunicación',
                   f'{_STUDIES}/masteres/master-universitario-en-ingenieria-de-telecomunicacion'),
    },
    {
        'area': 'Ingeniería Aeronáutica',
        'degree': ('Grado en Ingeniería Aeroespacial',
                   f'{_STUDIES}/grados/grado-en-ingenieria-aeroespacial'),
        'master': ('Máster Universitario en Ingeniería Aeronáutica',
                   f'{_STUDIES}/masteres/master-universitario-en-ingenieria-aeronautica'),
    },
    {
        'area': 'Ingeniería de Caminos, Canales y Puertos',
        'degree': ('Grado en Ingeniería Civil',
                   f'{_STUDIES}/grados/grado-en-ingenieria-civil'),
        'master': ('Máster Universitario en Ingeniería de Caminos, Canales y Puertos',
                   f'{_STUDIES}/masteres/master-universitario-en-ingenieria-de-caminos-canales-y-puertos'),
    },
    {
        'area': 'Ingeniería Química',
        'degree': ('Grado en Ingeniería Química',
                   f'{_STUDIES}/grados/grado-en-ingenieria-quimica'),
        'master': ('Máster Universitario en Ingeniería Química',
                   f'{_STUDIES}/masteres/master-universitario-en-ingenieria-quimica'),
    },
]

# Grados outside the PARS (Campus de Excelencia Internacional Andalucía Tech).
ETSI_DEGREES = [
    ('Grado en Ingeniería de Organización Industrial', f'{_STUDIES}/grados/grado-en-ingenieria-de-organizacion-industrial'),
    ('Grado en Ingeniería de la Energía', f'{_STUDIES}/grados/grado-en-ingenieria-de-la-energia'),
    ('Grado en Ingeniería Electrónica, Robótica y Mecatrónica',
     f'{_STUDIES}/grados/grado-en-ingenieria-electronica-robotica-y-mecatronica'),
]

ETSI_MASTERS = [
    ('Máster Universitario en Ingeniería Industrial',
     f'{_STUDIES}/masteres/master-universitario-en-ingenieria-industrial-plan-2024'),
    ('Máster Universitario en Ingeniería de Telecomunicación',
     f'{_STUDIES}/masteres/master-universitario-en-ingenieria-de-telecomunicacion'),
    ('Máster Universitario en Ingeniería Aeronáutica', f'{_STUDIES}/masteres/master-universitario-en-ingenieria-aeronautica'),
    ('Máster Universitario en Ingeniería de Caminos, Canales y Puertos',
     f'{_STUDIES}/masteres/master-universitario-en-ingenieria-de-caminos-canales-y-puertos'),
    ('Máster Universitario en Ingeniería Química', f'{_STUDIES}/masteres/master-universitario-en-ingenieria-quimica'),
    ('Máster Universitario en Diseño Avanzado en Ingeniería Mecánica',
     f'{_STUDIES}/masteres/master-universitario-en-diseno-avanzado-en-ingenieria-mecanica'),
    ('Máster Universitario en Ingeniería en Electrónica, Robótica y Automática',
     f'{_STUDIES}/masteres/master-universitario-en-ingenieria-en-electronica-robotica-y-automatica'),
    ('Máster Universitario en Organización Industrial y Gestión de Empresas',
     f'{_STUDIES}/masteres/master-universitario-en-organizacion-industrial-y-gestion-de-empresas'),
    ('Máster Universitario en Sistemas de Energía Eléctrica',
     f'{_STUDIES}/masteres/master-universitario-en-sistemas-de-energia-electrica'),
    ('Máster Universitario en Sistemas de Energía Térmica',
     f'{_STUDIES}/masteres/master-universitario-en-sistemas-de-energia-termica'),
    ('Máster Universitario en Ingeniería Ambiental', f'{_STUDIES}/masteres/master-universitario-en-ingenieria-ambiental'),
    ("Master's Degree in Operation of Space Systems", f'{_STUDIES}/masteres/masters-degree-operation-space-systems'),
]

ETSI_DOUBLE_MASTERS = [
    ('Doble Máster Universitario en Ingeniería Química e Ingeniería Ambiental',
     f'{_STUDIES}/masteres/doble-master-universitario-en-ingenieria-quimica-e-ingenieria-ambiental'),
    ("Joint Master's Degree in Aeronautic Engineering and Operation of Space Systems",
     f'{_STUDIES}/masteres/joint-masters-degree-aeronautic-engineering-and-operation-space-systems'),
]

ETSI_DOCTORATES = [
    ('Doctorado en Ingeniería Automática, Electrónica y Telecomunicación',
     f'{_STUDIES}/doctorados/doctorado-en-ingenieria-automatica-electronica-y-telecomunicacion'),
    ('Doctorado en Ingeniería Mecánica y de Organización Industrial',
     f'{_STUDIES}/doctorados/doctorado-en-ingenieria-mecanica-y-de-organizacion-industrial'),
    ('Doctorado en Ingeniería Energética, Química y Ambiental',
     f'{_STUDIES}/doctorados/doctorado-en-ingenieria-energetica-quimica-y-ambiental'),
    ('Doctorado en Sistemas de Energía Eléctrica', f'{_STUDIES}/doctorados/doctorado-en-sistemas-de-energia-electrica'),
]
