import datetime
import io
import smtplib
import tempfile
import zipfile
from unittest import mock
from zoneinfo import ZoneInfo

from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.models import User
from core.models import EventSettings

from .credentials import suggest_username
from .emailing import render_template
from .models import (
    Company,
    CompanyContact,
    CompanyDocumentation,
    CRMNote,
    EmailHistory,
    EventAttendee,
    Objective,
    OrganizationLogEntry,
)


def set_event_date(year, month, day):
    event = EventSettings.load()
    event.event_date = datetime.datetime(year, month, day, 10, 0, tzinfo=ZoneInfo('Europe/Madrid'))
    event.save()
    return event


class EditionTests(TestCase):
    def test_new_records_take_the_year_of_the_event_date(self):
        company = Company.objects.create(name='Acme')
        self.assertEqual(company.edition, 2027)
        event = set_event_date(2028, 3, 9)
        self.assertEqual((event.year, event.edition_name), (2028, 'ESIEM 2028'))
        note = CRMNote.objects.create(company=company, text='Hola')
        self.assertEqual(note.edition, 2028)
        self.assertEqual(Company.objects.get(pk=company.pk).edition, 2027)

    def test_new_edition_hides_previous_companies_but_keeps_them(self):
        acme = Company.objects.create(name='Acme', status=Company.Status.CONFIRMED)
        user = User.objects.create_user('acme', password='x', is_company=True, company=acme)
        organizer = User.objects.create_user('org', password='x', is_staff_admin=True)
        set_event_date(2028, 3, 9)

        client = APIClient()
        client.force_authenticate(organizer)
        self.assertEqual(client.get('/api/companies/').json(), [])
        self.assertEqual(client.get(f'/api/companies/{acme.id}/').status_code, 404)
        self.assertNotContains(self.client.get(reverse('core:directory')), 'Acme')
        client.force_authenticate(user)
        self.assertEqual(client.get('/api/companies/').status_code, 403)
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse('crm:panel')).status_code, 403)

        # The same company can take part again: a new record for 2028; the 2027 one stays.
        again = Company.objects.create(name='ACME')
        self.assertEqual(again.edition, 2028)
        self.assertEqual(Company.objects.filter(name__iexact='acme').count(), 2)

    def test_past_edition_company_user_cannot_log_in(self):
        acme = Company.objects.create(name='Acme', status=Company.Status.CONFIRMED)
        User.objects.create_user('acme', password='x', is_company=True, company=acme)
        set_event_date(2028, 3, 9)
        response = self.client.post(reverse('accounts:login'), {'username': 'acme', 'password': 'x'})
        self.assertContains(response, 'edición anterior')
        self.assertNotIn('_auth_user_id', self.client.session)


class ObjectiveEditionTests(TestCase):
    def test_seeded_objectives_store_days_before_event(self):
        wifi = Objective.objects.get(title='Solicitar Red Wifi')  # 25/02/2027, event 11/03/2027
        self.assertEqual(wifi.days_before_event, 14)

    def test_moving_the_event_moves_the_current_deadlines(self):
        set_event_date(2027, 3, 18)
        wifi = Objective.objects.get(title='Solicitar Red Wifi')
        self.assertEqual((wifi.deadline, wifi.days_before_event), (datetime.date(2027, 3, 4), 14))

    def test_new_edition_copies_objectives_with_the_same_offsets(self):
        Objective.objects.filter(title='Solicitar Red Wifi').update(done=True)
        set_event_date(2028, 3, 9)
        self.assertEqual(Objective.objects.filter(edition=2028).count(), 24)
        new = Objective.objects.get(title='Solicitar Red Wifi', edition=2028)
        self.assertEqual((new.deadline, new.days_before_event, new.done), (datetime.date(2028, 2, 24), 14, False))
        old = Objective.objects.get(title='Solicitar Red Wifi', edition=2027)
        self.assertEqual((old.deadline, old.done), (datetime.date(2027, 2, 25), True))

        client = APIClient()
        client.force_authenticate(User.objects.create_user('org', password='x', is_staff_admin=True))
        rows = client.get('/api/objectives/').json()
        self.assertEqual({row['id'] for row in rows}, set(Objective.objects.filter(edition=2028).values_list('id', flat=True)))
        created = client.post('/api/objectives/', {'title': 'Nuevo', 'deadline': '2028-03-01'}, format='json').json()
        self.assertEqual(created['days_before_event'], 8)


class ApiTestCase(TestCase):
    def setUp(self):
        self.acme = Company.objects.create(name='Acme')
        self.beta = Company.objects.create(name='Beta')
        self.contact = CompanyContact.objects.create(company=self.acme, email='rrhh@acme.es', name='Ana', is_primary=True)
        self.organizer = User.objects.create_user('org', password='x', is_staff_admin=True)
        self.company_user = User.objects.create_user('acme', password='x', is_company=True, company=self.acme)
        self.client = APIClient()


class CompanyScopingTests(ApiTestCase):
    def test_company_user_sees_only_own_company(self):
        self.client.force_authenticate(self.company_user)
        response = self.client.get('/api/companies/')
        self.assertEqual([c['id'] for c in response.json()], [self.acme.id])
        self.assertEqual(self.client.get(f'/api/companies/{self.beta.id}/').status_code, 404)

    def test_list_reports_attendees_and_materials_progress(self):
        EventAttendee.objects.create(company=self.acme, first_name='Ana', last_name='López', dni='1')
        EventAttendee.objects.create(company=self.acme, first_name='Luis', last_name='Gil', dni='2')
        CompanyDocumentation.objects.create(company=self.acme, dossier='companies/x/d.pdf', logo='companies/x/l.png',
                                            logo_by_organizer=True, advert='companies/x/a.pdf')
        self.client.force_authenticate(self.organizer)
        rows = {c['name']: c for c in self.client.get('/api/companies/?search=a').json()}
        acme, beta = rows['Acme'], rows['Beta']
        self.assertEqual(acme['attendee_count'], 2)
        self.assertEqual((acme['dossier_state'], acme['logo_state'], acme['advert_state'], acme['banner_state']),
                         ('done', 'pending', 'done', 'missing'))
        self.assertEqual((beta['attendee_count'], beta['dossier_state']), (0, 'missing'))

    def test_company_user_can_edit_contract_data_and_it_is_logged(self):
        self.client.force_authenticate(self.company_user)
        response = self.client.patch(f'/api/companies/{self.acme.id}/', {
            'address': 'Calle Nueva 2', 'payment_method': 'cheque', 'name': 'Otro nombre', 'cif': 'X1',
        }, format='json')
        self.assertEqual(response.status_code, 200)
        self.acme.refresh_from_db()
        self.assertEqual((self.acme.address, self.acme.payment_method), ('Calle Nueva 2', 'cheque'))
        self.assertEqual((self.acme.name, self.acme.cif), ('Acme', ''))
        note = CRMNote.objects.get(company=self.acme)
        self.assertIn('domicilio', note.text)
        self.assertIn('forma de pago', note.text)

    def test_company_user_cannot_change_status_stand_or_summary(self):
        self.client.force_authenticate(self.company_user)
        self.client.patch(f'/api/companies/{self.acme.id}/', {
            'status': 'confirmed', 'stand_number': 'A1', 'summary': 'Hola', 'website': 'https://acme.example',
        }, format='json')
        self.acme.refresh_from_db()
        self.assertEqual(self.acme.status, Company.Status.INTERESTED)
        self.assertEqual(self.acme.stand_number, '')
        self.assertEqual(self.acme.summary, '')
        self.assertEqual(self.acme.website, 'https://acme.example')

    def test_company_attendees_are_forced_to_own_company(self):
        self.client.force_authenticate(self.company_user)
        response = self.client.post('/api/attendees/', {
            'company': self.beta.id, 'first_name': 'Eva', 'last_name': 'Ruiz', 'dni': '1X',
        }, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(EventAttendee.objects.get().company, self.acme)

    def test_attendee_edits_by_company_are_visible_to_organizer(self):
        self.client.force_authenticate(self.company_user)
        self.client.post('/api/attendees/', {'first_name': 'Eva', 'last_name': 'Ruiz', 'dni': '1X', 'dietary_needs': 'celíaca'}, format='json')
        self.client.force_authenticate(self.organizer)
        rows = self.client.get(f'/api/attendees/?company={self.acme.id}').json()
        self.assertEqual(rows[0]['dietary_needs'], 'celíaca')

    def test_company_user_cannot_use_crm_only_endpoints(self):
        self.client.force_authenticate(self.company_user)
        self.assertEqual(self.client.get(f'/api/notes/?company={self.acme.id}').status_code, 403)
        self.assertEqual(self.client.get('/api/contacts/').status_code, 403)
        self.assertEqual(self.client.get(f'/api/companies/{self.acme.id}/emails/').status_code, 403)
        self.assertEqual(self.client.post(f'/api/companies/{self.acme.id}/send-email/', {}, format='json').status_code, 403)

    def test_only_organizer_can_delete_company(self):
        self.client.force_authenticate(self.company_user)
        self.assertEqual(self.client.delete(f'/api/companies/{self.acme.id}/').status_code, 403)
        self.client.force_authenticate(self.organizer)
        self.assertEqual(self.client.delete(f'/api/companies/{self.acme.id}/').status_code, 204)
        self.assertFalse(Company.objects.filter(pk=self.acme.id).exists())
        self.assertFalse(CompanyContact.objects.filter(pk=self.contact.id).exists())
        self.assertFalse(User.objects.filter(pk=self.company_user.id).exists())
        self.assertTrue(User.objects.filter(pk=self.organizer.id).exists())

    def test_companies_cannot_be_created_from_the_panel(self):
        self.client.force_authenticate(self.organizer)
        response = self.client.post('/api/companies/', {'name': 'Nueva'}, format='json')
        self.assertEqual(response.status_code, 405)
        self.assertFalse(Company.objects.filter(name='Nueva').exists())

    def test_anonymous_has_no_api_access(self):
        self.assertEqual(self.client.get('/api/companies/').status_code, 403)


class NotesTests(ApiTestCase):
    def test_note_records_author_and_cannot_be_edited(self):
        self.client.force_authenticate(self.organizer)
        response = self.client.post('/api/notes/', {'company': self.acme.id, 'text': 'Llamada: aceptan participar', 'kind': 'call'}, format='json')
        self.assertEqual(response.status_code, 201)
        note = CRMNote.objects.get()
        self.assertEqual(note.author, self.organizer)
        self.assertGreaterEqual(self.client.patch(f'/api/notes/{note.id}/', {'text': 'x'}, format='json').status_code, 400)
        self.assertGreaterEqual(self.client.delete(f'/api/notes/{note.id}/').status_code, 400)
        note.refresh_from_db()
        self.assertEqual(note.text, 'Llamada: aceptan participar')


class OrganizationLogTests(ApiTestCase):
    def test_objectives_from_objetivos_txt_are_seeded(self):
        objective = Objective.objects.get(title='Solicitar Red Wifi')
        self.assertEqual(objective.deadline.isoformat(), '2027-02-25')
        self.assertEqual(Objective.objects.count(), 24)

    def test_entry_is_linked_to_objective_and_immutable(self):
        objective = Objective.objects.get(title='Carteles con QRs')
        self.client.force_authenticate(self.organizer)
        response = self.client.post('/api/log-entries/', {'objective': objective.id, 'text': 'Pedidos a reprografía'}, format='json')
        self.assertEqual(response.status_code, 201)
        entry = OrganizationLogEntry.objects.get()
        self.assertEqual((entry.objective, entry.author), (objective, self.organizer))
        self.assertGreaterEqual(self.client.patch(f'/api/log-entries/{entry.id}/', {'text': 'x'}, format='json').status_code, 400)
        self.assertGreaterEqual(self.client.delete(f'/api/log-entries/{entry.id}/').status_code, 400)
        rows = {o['id']: o for o in self.client.get('/api/objectives/').json()}
        self.assertEqual(rows[objective.id]['entry_count'], 1)
        self.assertEqual(len(self.client.get(f'/api/log-entries/?objective={objective.id}').json()), 1)

    def test_general_entry_without_objective(self):
        self.client.force_authenticate(self.organizer)
        response = self.client.post('/api/log-entries/', {'objective': None, 'text': 'Reunión del equipo'}, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertIsNone(OrganizationLogEntry.objects.get().objective)

    def test_completing_objective_is_logged(self):
        objective = Objective.objects.get(title='Carta del Director')
        self.client.force_authenticate(self.organizer)
        self.assertEqual(self.client.patch(f'/api/objectives/{objective.id}/', {'done': True}, format='json').status_code, 200)
        objective.refresh_from_db()
        self.assertTrue(objective.done)
        self.assertEqual(objective.entries.get().text, 'Objetivo marcado como completado.')
        self.assertEqual(self.client.delete(f'/api/objectives/{objective.id}/').status_code, 405)

    def test_company_user_has_no_access(self):
        self.client.force_authenticate(self.company_user)
        self.assertEqual(self.client.get('/api/objectives/').status_code, 403)
        self.assertEqual(self.client.get('/api/log-entries/').status_code, 403)
        self.assertEqual(self.client.post('/api/log-entries/', {'text': 'x'}, format='json').status_code, 403)


@override_settings(EMAIL_AUTOMATIC_SENDING=True)  # independent of the local .env
class EmailTests(ApiTestCase):
    def send(self, **data):
        self.client.force_authenticate(self.organizer)
        payload = {'recipients': ['rrhh@acme.es'], 'subject': 'Asunto', 'body': 'Texto editado', **data}
        return self.client.post(f'/api/companies/{self.acme.id}/send-email/', payload, format='json')

    def test_template_placeholders_are_replaced(self):
        rendered = render_template('seguimiento.txt', self.acme)
        self.assertIn('Acme', rendered['body'])
        self.assertIn('Ana', rendered['body'])
        self.assertNotIn('{nombre_empresa}', rendered['body'])
        self.assertTrue(rendered['subject'])

    def test_template_name_cannot_escape_directory(self):
        self.client.force_authenticate(self.organizer)
        response = self.client.get(f'/api/companies/{self.acme.id}/email-template/?name=../manage.py')
        self.assertEqual(response.status_code, 404)

    def test_acceptance_template_includes_generated_credentials(self):
        self.client.force_authenticate(self.organizer)
        data = self.client.get(f'/api/companies/{self.acme.id}/email-template/?kind=acceptance').json()
        credentials = data['credentials']
        self.assertEqual(credentials['username'], 'acme')
        self.assertEqual(len(credentials['password']), 10)
        self.assertIn(f"Usuario:     {credentials['username']}", data['body'])
        self.assertIn(credentials['password'], data['body'])
        # Other templates carry no credentials.
        data = self.client.get(f'/api/companies/{self.acme.id}/email-template/?kind=rejection').json()
        self.assertIsNone(data['credentials'])

    def test_username_comes_from_company_name_and_is_unique(self):
        company = Company.objects.create(name='Acme Ingeniería, S.L.')
        self.assertEqual(suggest_username(company), 'acme-ingenieria')
        User.objects.create_user('acme-ingenieria')
        self.assertEqual(suggest_username(company), 'acme-ingenieria-2')
        # An already accepted company keeps its username.
        self.assertEqual(suggest_username(self.acme), 'acme')

    def test_acceptance_creates_portal_user_and_accepts_company(self):
        response = self.send(kind='acceptance', username='acme-sa', password='Clave2027x')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(mail.outbox), 1)
        self.acme.refresh_from_db()
        self.assertEqual(self.acme.status, Company.Status.CONFIRMED)
        # The existing portal user of Acme gets the username and password of the email (no second account).
        user = User.objects.get(company=self.acme)
        self.assertEqual(user.username, 'acme-sa')
        self.assertTrue(user.check_password('Clave2027x'))
        note = CRMNote.objects.get(company=self.acme)
        self.assertEqual(note.kind, CRMNote.Kind.EMAIL)
        self.assertIn('Correo de aceptación enviado a rrhh@acme.es. La empresa pasa a «Aceptada»', note.text)
        self.assertIn('Texto editado', note.text)

    def test_acceptance_of_new_company_creates_user_from_contact(self):
        company = Company.objects.create(name='Gamma')
        CompanyContact.objects.create(company=company, email='rrhh@gamma.es', name='Eva Ruiz', is_primary=True)
        self.client.force_authenticate(self.organizer)
        response = self.client.post(f'/api/companies/{company.id}/send-email/', {
            'recipients': ['rrhh@gamma.es'], 'subject': 'x', 'body': 'x',
            'kind': 'acceptance', 'username': 'gamma', 'password': 'Clave2027x',
        }, format='json')
        self.assertEqual(response.status_code, 201)
        user = User.objects.get(username='gamma')
        self.assertEqual((user.company, user.is_company, user.email, user.first_name), (company, True, 'rrhh@gamma.es', 'Eva'))
        self.assertTrue(self.client.login(username='gamma', password='Clave2027x'))

    def test_organizer_sees_credentials_and_resend_reuses_them(self):
        self.send(kind='acceptance', username='acme-sa', password='Clave2027x')
        access = self.client.get(f'/api/companies/{self.acme.id}/').json()['portal_access']
        self.assertEqual((access['username'], access['password'], access['active']), ('acme-sa', 'Clave2027x', True))
        # Loading the acceptance template again (to resend it) keeps the same credentials.
        data = self.client.get(f'/api/companies/{self.acme.id}/email-template/?kind=acceptance').json()
        self.assertEqual(data['credentials'], {'username': 'acme-sa', 'password': 'Clave2027x'})
        # Once accepted they are fixed: a resend can't change them.
        self.assertEqual(self.send(kind='acceptance', username='otro', password='Clave2027x').status_code, 400)
        self.assertEqual(self.send(kind='acceptance', username='acme-sa', password='OtraClave99').status_code, 400)
        self.assertEqual(self.send(kind='acceptance', username='acme-sa', password='Clave2027x').status_code, 201)
        # Company users never get them through the API.
        self.client.force_authenticate(self.company_user)
        self.assertNotIn('portal_access', self.client.get(f'/api/companies/{self.acme.id}/').json())

    def test_portal_credentials_box_is_locked_once_accepted(self):
        self.client.force_authenticate(self.organizer)
        url = f'/api/companies/{self.acme.id}/portal-credentials/'
        data = self.client.get(url).json()
        self.assertEqual((data['username'], data['locked'], data['password_known']), ('acme', False, False))
        self.send(kind='acceptance', username='acme-sa', password='Clave2027x')
        data = self.client.get(url).json()
        self.assertEqual((data['username'], data['password'], data['locked'], data['password_known']),
                         ('acme-sa', 'Clave2027x', True, True))
        # Company users don't get it.
        self.client.force_authenticate(self.company_user)
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_acceptance_needs_free_username_and_password(self):
        self.assertEqual(self.send(kind='acceptance', username='org', password='Clave2027x').status_code, 400)
        self.assertEqual(self.send(kind='acceptance', username='acme-sa', password='').status_code, 400)
        self.assertEqual(len(mail.outbox), 0)
        self.acme.refresh_from_db()
        self.assertEqual(self.acme.status, Company.Status.INTERESTED)

    def test_rejection_rejects_company_and_disables_portal_access(self):
        response = self.send(kind='rejection')
        self.assertEqual(response.status_code, 201)
        self.acme.refresh_from_db()
        self.assertEqual(self.acme.status, Company.Status.DECLINED)
        self.company_user.refresh_from_db()
        self.assertFalse(self.company_user.is_active)
        self.assertIn('La empresa pasa a «Rechazada»', CRMNote.objects.get().text)

    def test_follow_up_does_not_change_status(self):
        self.assertEqual(self.send(kind='summary').status_code, 201)
        self.acme.refresh_from_db()
        self.assertEqual(self.acme.status, Company.Status.INTERESTED)
        self.assertIn('Correo de seguimiento enviado', CRMNote.objects.get().text)

    def test_failed_send_is_not_logged_in_crm(self):
        with mock.patch('crm.emailing.EmailMessage.send', side_effect=smtplib.SMTPException('caído')):
            self.send(kind='rejection')
        self.assertFalse(CRMNote.objects.exists())
        self.acme.refresh_from_db()
        self.assertEqual(self.acme.status, Company.Status.INTERESTED)

    def test_cannot_send_to_addresses_outside_company_contacts(self):
        response = self.send(recipients=['otro@ejemplo.com'])
        self.assertEqual(response.status_code, 400)
        self.assertEqual(len(mail.outbox), 0)

    def test_manual_acceptance_is_logged_without_sending(self):
        with self.settings(EMAIL_AUTOMATIC_SENDING=False):
            automatic = self.send()
            manual = self.send(kind='acceptance', username='acme-sa', password='Clave2027x', manual=True)
        self.assertEqual(automatic.status_code, 400)
        self.assertEqual(manual.status_code, 201)
        self.assertEqual(len(mail.outbox), 0)
        self.assertTrue(EmailHistory.objects.get().manual)
        self.acme.refresh_from_db()
        self.assertEqual(self.acme.status, Company.Status.CONFIRMED)
        self.assertIn('desde Outlook', CRMNote.objects.get().text)

    def test_smtp_failure_returns_readable_error_without_logging(self):
        refused = smtplib.SMTPRecipientsRefused({'rrhh@acme.es': (554, b'Access denied')})
        with mock.patch('crm.emailing.EmailMessage.send', side_effect=refused):
            response = self.send(kind='acceptance', username='acme-sa', password='Clave2027x')
        self.assertEqual(response.status_code, 502)
        self.assertIn('rechazado el destinatario', response.data['detail'])
        self.assertFalse(EmailHistory.objects.exists())
        self.acme.refresh_from_db()
        self.assertEqual(self.acme.status, Company.Status.INTERESTED)
        self.company_user.refresh_from_db()
        self.assertTrue(self.company_user.check_password('x'))


class DocumentationTests(ApiTestCase):
    def test_dossier_must_be_pdf(self):
        self.client.force_authenticate(self.company_user)
        bad = SimpleUploadedFile('dossier.exe', b'x')
        response = self.client.patch(f'/api/companies/{self.acme.id}/documentation/', {'dossier': bad}, format='multipart')
        self.assertEqual(response.status_code, 400)

    @override_settings(MEDIA_ROOT=tempfile.mkdtemp())
    def test_company_uploads_word_dossier_and_advert(self):
        self.client.force_authenticate(self.company_user)
        response = self.client.patch(f'/api/companies/{self.acme.id}/documentation/', {
            'dossier': SimpleUploadedFile('dossier.docx', b'x'),
            'advert': SimpleUploadedFile('anuncio.pdf', b'%PDF'),
        }, format='multipart')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['advert'])
        self.assertFalse(response.json()['advert_by_organizer'])

    def test_company_can_update_stand_needs(self):
        self.client.force_authenticate(self.company_user)
        response = self.client.patch(f'/api/companies/{self.acme.id}/documentation/', {'chairs': 3, 'needs_wifi': True}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.acme.documentation.chairs, 3)


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class MaterialsZipTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.client.force_authenticate(self.company_user)
        self.client.patch(f'/api/companies/{self.acme.id}/documentation/', {
            'logo': SimpleUploadedFile('logo.png', b'png'),
            'dossier': SimpleUploadedFile('d.pdf', b'%PDF'),
            'banner': SimpleUploadedFile('plata.pdf', b'%PDF-b'),
        }, format='multipart')

    def names(self, response):
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/zip')
        archive = zipfile.ZipFile(io.BytesIO(b''.join(response.streaming_content)))
        return set(archive.namelist()), archive

    def test_company_zip_has_all_its_files(self):
        self.client.force_authenticate(self.organizer)
        names, archive = self.names(self.client.get(f'/api/companies/{self.acme.id}/materials-zip/'))
        self.assertEqual(names, {'Acme/Logotipo.png', 'Acme/Dossier.pdf', 'Acme/Platabanda.pdf', 'LEEME.txt'})
        self.assertEqual(archive.read('Acme/Platabanda.pdf'), b'%PDF-b')
        self.assertIn('Acme: falta anuncio', archive.read('LEEME.txt').decode())

    def test_bulk_zip_by_group(self):
        self.client.force_authenticate(self.organizer)
        names, archive = self.names(self.client.get('/api/companies/materials-zip/?group=stand'))
        self.assertEqual(names, {'Acme/Platabanda.pdf', 'LEEME.txt'})
        self.assertIn('Beta: falta platabanda', archive.read('LEEME.txt').decode())
        names, _ = self.names(self.client.get('/api/companies/materials-zip/?group=catalogo'))
        self.assertEqual(names, {'Acme/Logotipo.png', 'Acme/Dossier.pdf', 'LEEME.txt'})
        self.assertEqual(self.client.get('/api/companies/materials-zip/?group=otro').status_code, 400)

    def test_company_users_cannot_download_zips(self):
        self.assertEqual(self.client.get(f'/api/companies/{self.acme.id}/materials-zip/').status_code, 403)
        self.assertEqual(self.client.get('/api/companies/materials-zip/?group=stand').status_code, 403)


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class OrganizerUploadConfirmationTests(ApiTestCase):
    def url(self):
        return f'/api/companies/{self.acme.id}/documentation/'

    def upload(self, user, name='dossier.pdf'):
        self.client.force_authenticate(user)
        return self.client.patch(self.url(), {'dossier': SimpleUploadedFile(name, b'%PDF')}, format='multipart')

    def confirm(self, value=True):
        self.client.force_authenticate(self.company_user)
        return self.client.patch(self.url(), {'dossier_confirmed': value}, format='json')

    def test_company_confirms_organizer_upload_and_it_is_logged(self):
        self.assertTrue(self.upload(self.organizer).json()['dossier_by_organizer'])
        response = self.confirm()
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.json()['dossier_confirmed_at'])
        self.assertIn('confirmado el dossier', CRMNote.objects.get().text)
        self.assertIsNone(self.confirm(False).json()['dossier_confirmed_at'])

    def test_company_replacing_organizer_upload_clears_flags_and_is_logged(self):
        self.upload(self.organizer)
        self.confirm()
        data = self.upload(self.company_user, 'propio.pdf').json()
        self.assertFalse(data['dossier_by_organizer'])
        self.assertIsNone(data['dossier_confirmed_at'])
        self.assertIn('sustituido el dossier', CRMNote.objects.order_by('-id').first().text)

    def test_cannot_confirm_company_own_upload(self):
        self.upload(self.company_user)
        self.assertEqual(self.confirm().status_code, 400)

    def test_cannot_confirm_without_file(self):
        self.assertEqual(self.confirm().status_code, 400)

    def test_organizer_cannot_confirm_on_behalf_of_company(self):
        self.upload(self.organizer)
        response = self.client.patch(self.url(), {'dossier_confirmed': True}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_new_organizer_upload_resets_confirmation(self):
        self.upload(self.organizer)
        self.confirm()
        self.assertIsNone(self.upload(self.organizer, 'v2.pdf').json()['dossier_confirmed_at'])
