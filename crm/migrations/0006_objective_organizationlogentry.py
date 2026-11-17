import datetime

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

# Initial objectives, from objetivos.txt (title, deadline).
OBJECTIVES = [
    ('Reserva de aulas para charlas', '21/10/2026'),
    ('Solicitud de actividad para reconocimiento de créditos', '02/12/2026'),
    ('Solicitar Ofertas Contrato acuerdo marco', '04/02/2027'),
    ('Contrato acuerdo marco', '14/02/2027'),
    ('Carta del Director', '25/02/2027'),
    ('Carta de Bienvenida', '25/02/2027'),
    ('Solicitar Red Wifi', '25/02/2027'),
    ('Organización & Horario de Mesa Redonda', '26/02/2027'),
    ('Cafetería para coffee-break y catering', '23/02/2027'),
    ('Lista de asistentes para Catering (incluir intolerancias y veganos)', '27/02/2027'),
    ('Maquetado y acreditaciones', '01/03/2027'),
    ('Envío a BINUS - Pilar', '02/03/2027'),
    ('Preparar Documentos para Aulas y QRs & Encuestas', '03/03/2027'),
    ('Fecha Límite: Info de empresas para stands y Catalogo', '03/03/2027'),
    ('Difusión del evento en Redes - RRSS', '06/03/2027'),
    ('Actualización Pág Web (Carta Director, Catálogo, Mapa, Horarios)', '09/03/2027'),
    ('Puesto colaboradores ESIEM 2026', '09/03/2027'),
    ('Carteles con QRs', '09/03/2027'),
    ('Enviar correo Reconocimiento de créditos', '09/03/2027'),
    ('Solicitud de presentación a empresas (dejarla lista en el ordenador)', '09/03/2027'),
    ('Preparar Diapositivas para televisores - Pilar RRSS', '09/03/2027'),
    ('Pegar carteles - Equipo Estudiantes', '10/03/2027'),
    ('Preparar encuesta de satisfacción y de Egresados - Paz & Estudiantes', '10/03/2027'),
    ('Imprimir documentos wifi y comprobar funcionalidad', '09/03/2027'),
]


def seed_objectives(apps, schema_editor):
    Objective = apps.get_model('crm', 'Objective')
    Objective.objects.bulk_create(
        Objective(title=title, deadline=datetime.datetime.strptime(deadline, '%d/%m/%Y').date())
        for title, deadline in OBJECTIVES
    )


class Migration(migrations.Migration):

    dependencies = [
        ('crm', '0005_documentation_organizer_uploads'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Objective',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=255, verbose_name='objetivo')),
                ('deadline', models.DateField(verbose_name='fecha límite')),
                ('done', models.BooleanField(default=False, verbose_name='completado')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'verbose_name': 'objetivo',
                'ordering': ['deadline', 'title'],
            },
        ),
        migrations.CreateModel(
            name='OrganizationLogEntry',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('text', models.TextField(verbose_name='texto')),
                ('author', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
                ('objective', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='entries', to='crm.objective', verbose_name='objetivo')),
            ],
            options={
                'verbose_name': 'anotación de organización',
                'verbose_name_plural': 'registro de organización',
                'ordering': ['-created_at', '-id'],
            },
        ),
        migrations.RunPython(seed_objectives, migrations.RunPython.noop),
    ]
