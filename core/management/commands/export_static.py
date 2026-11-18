"""Export the public site as static HTML (e.g. for a GitHub Pages preview).

Pages are rendered anonymously through the test client with `settings.STATIC_EXPORT = True`, which
hides everything that needs the server (private area, participation form), and written as
<path>/index.html. Root-relative URLs are rewritten to relative ones so the site works under any
base path (https://<user>.github.io/<repo>/). The company directory is left empty unless
--con-empresas is given.
"""

import re
import shutil
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.test import Client
from django.urls import reverse

from core import views

# Root-relative URL in an attribute or a JSON string: href="/x", src="/x", "logo": "/media/x".
ROOT_URL = re.compile(r'''(?P<quote>["'])/(?!/)''')
SERVER_ONLY = re.compile(r'''["']/(?:cuenta|panel|api|admin)/''')


class Command(BaseCommand):
    help = 'Exporta la web pública como HTML estático (vista previa para GitHub Pages).'

    def add_arguments(self, parser):
        parser.add_argument('output', nargs='?', default=str(settings.BASE_DIR / '_site'))
        parser.add_argument('--con-empresas', action='store_true',
                            help='Incluye las empresas aceptadas de la BD en el directorio (por defecto, vacío).')

    def handle(self, output, con_empresas, **options):
        out = Path(output)
        if out.exists():
            shutil.rmtree(out)
        out.mkdir(parents=True)

        settings.STATIC_EXPORT = True
        if not con_empresas:
            views._public_companies = lambda: []

        paths = [reverse(f'core:{name}') for name in
                 ('home', 'letter', 'etsi', 'event', 'exhibitors', 'directory', 'chairs', 'organizers', 'follow')]
        paths += [reverse('core:legal', args=[slug]) for slug in views.LEGAL_PAGES]

        client = Client(SERVER_NAME='localhost')
        media = set()
        for path in paths:
            response = client.get(path)
            if response.status_code != 200:
                raise CommandError(f'{path} devolvió {response.status_code}')
            html = response.content.decode()
            if SERVER_ONLY.search(html):
                raise CommandError(f'{path} enlaza a una parte privada de la web')
            media.update(re.findall(r'/media/([^"\'?\s]+)', html))
            prefix = '../' * path.strip('/').count('/') + ('../' if path != '/' else './')
            target = out / path.strip('/') / 'index.html'
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(ROOT_URL.sub(lambda m: m['quote'] + prefix, html), encoding='utf-8')

        shutil.copytree(settings.BASE_DIR / 'static', out / 'static', ignore=shutil.ignore_patterns('panel.js'))
        for name in media:
            source = Path(settings.MEDIA_ROOT) / name
            if source.is_file():
                (out / 'media' / name).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, out / 'media' / name)
        (out / '.nojekyll').touch()  # serve folders as-is
        self.stdout.write(self.style.SUCCESS(f'{len(paths)} páginas y {len(media)} ficheros de media en {out}'))
