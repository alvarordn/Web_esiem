"""ZIP downloads of the corporate materials companies upload in «Dossier y Stand».

Two groups, matching the panel: «catálogo» (logo, dossier, advert) and «stand» (banner = platabanda).
Each ZIP has one folder per company plus a LEEME.txt listing what each company is still missing.
"""
import re
import shutil
import tempfile
import unicodedata
import zipfile
from pathlib import Path

from django.utils import timezone

# CompanyDocumentation file field -> file name inside the ZIP.
FILE_NAMES = {'logo': 'Logotipo', 'dossier': 'Dossier', 'advert': 'Anuncio', 'banner': 'Platabanda'}

GROUPS = {
    'catalogo': ('Material del catálogo', ['logo', 'dossier', 'advert']),
    'stand': ('Material del stand', ['banner']),
}
ALL_FIELDS = [name for _, fields in GROUPS.values() for name in fields]


def safe_name(text):
    """File-system friendly version of a company name (no accents or path separators)."""
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode()
    text = re.sub(r'[^\w\s.-]', '', text).strip()
    return re.sub(r'\s+', '_', text)[:80] or 'empresa'


def build_zip(companies, fields, title):
    """Write the requested materials of `companies` to a temporary ZIP and return it, rewound.

    The caller streams it (FileResponse closes it, which deletes it)."""
    tmp = tempfile.TemporaryFile()
    missing_lines = []
    used_folders = set()
    files_added = 0
    with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as archive:
        for company in companies:
            folder = safe_name(company.name)
            if folder in used_folders:  # two companies with the same name
                folder = f'{folder}_{company.pk}'
            used_folders.add(folder)
            doc = getattr(company, 'documentation', None)
            missing = []
            for field in fields:
                file = getattr(doc, field, None) if doc else None
                if not file:
                    missing.append(FILE_NAMES[field].lower())
                    continue
                arcname = f'{folder}/{FILE_NAMES[field]}{Path(file.name).suffix.lower()}'
                try:
                    with file.open('rb') as source, archive.open(arcname, 'w') as target:
                        shutil.copyfileobj(source, target, 1024 * 1024)
                    files_added += 1
                except FileNotFoundError:
                    missing.append(f'{FILE_NAMES[field].lower()} (archivo no encontrado en el servidor)')
            if missing:
                missing_lines.append(f'- {company.name}: falta {", ".join(missing)}')
        summary = [
            f'{title}',
            f'Generado el {timezone.localtime():%d/%m/%Y a las %H:%M}',
            f'{files_added} archivo(s) de {len(used_folders)} empresa(s).',
            '',
        ]
        summary += ['Material pendiente:', *missing_lines] if missing_lines else ['Todas las empresas han entregado este material.']
        archive.writestr('LEEME.txt', '\n'.join(summary) + '\n')
    tmp.seek(0)
    return tmp
