from django.db import migrations, models


def lowercase_i(apps, schema_editor):
    EventSettings = apps.get_model('core', 'EventSettings')
    for settings in EventSettings.objects.filter(venue__contains='ETSI'):
        settings.venue = settings.venue.replace('ETSI', 'ETSi')
        settings.save(update_fields=['venue'])


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0003_delete_edition_eventsettings_participation_fee_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='eventsettings',
            name='venue',
            field=models.CharField(default='ETSi, Universidad de Sevilla', max_length=200, verbose_name='lugar'),
        ),
        migrations.RunPython(lowercase_i, migrations.RunPython.noop),
    ]
