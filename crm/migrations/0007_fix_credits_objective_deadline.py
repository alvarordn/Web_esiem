import datetime

from django.db import migrations

TITLE = 'Solicitud de actividad para reconocimiento de créditos'


def fix_deadline(apps, schema_editor):
    # objetivos.txt had 02/12/2024 by mistake; databases seeded by 0006 before the fix keep that date.
    Objective = apps.get_model('crm', 'Objective')
    Objective.objects.filter(title=TITLE, deadline=datetime.date(2024, 12, 2)).update(deadline=datetime.date(2026, 12, 2))


class Migration(migrations.Migration):

    dependencies = [
        ('crm', '0006_objective_organizationlogentry'),
    ]

    operations = [
        migrations.RunPython(fix_deadline, migrations.RunPython.noop),
    ]
