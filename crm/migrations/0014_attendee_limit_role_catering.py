from django.db import migrations, models


def mark_existing_allergies(apps, schema_editor):
    # Attendees registered before had a free «alergias / catering» text: whoever filled it eats there.
    EventAttendee = apps.get_model('crm', 'EventAttendee')
    EventAttendee.objects.exclude(allergies='').update(eats_at_event=True, has_allergies=True)


class Migration(migrations.Migration):

    dependencies = [
        ('crm', '0013_remove_payment'),
    ]

    operations = [
        migrations.AddField(
            model_name='company',
            name='max_attendees',
            field=models.PositiveSmallIntegerField(
                default=5, help_text='Personas que la empresa puede registrar en «Personas que asistirán al evento».',
                verbose_name='máximo de asistentes'),
        ),
        migrations.RenameField(model_name='eventattendee', old_name='dietary_needs', new_name='allergies'),
        migrations.AlterField(
            model_name='eventattendee',
            name='allergies',
            field=models.CharField(blank=True, max_length=255, verbose_name='alergias'),
        ),
        migrations.AddField(
            model_name='eventattendee',
            name='role',
            field=models.CharField(choices=[('stand', 'Stand'), ('speaker', 'Ponente'), ('both', 'Stand y ponente')],
                                   default='stand', max_length=10, verbose_name='participación'),
        ),
        migrations.AddField(
            model_name='eventattendee',
            name='eats_at_event',
            field=models.BooleanField(default=False, verbose_name='come en el evento'),
        ),
        migrations.AddField(
            model_name='eventattendee',
            name='has_allergies',
            field=models.BooleanField(default=False, verbose_name='tiene alergias'),
        ),
        migrations.RunPython(mark_existing_allergies, migrations.RunPython.noop),
    ]
