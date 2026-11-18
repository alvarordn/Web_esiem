from django.test import TestCase
from django.urls import reverse

from core.models import EventSettings
from crm.models import Company, CRMNote

from .models import User

URL = reverse('accounts:register')


class RegistrationTests(TestCase):
    def setUp(self):
        event = EventSettings.load()
        event.invitation_key = 'ESIEM-EXPOSITOR-2027'
        event.save()

    def enter_key(self, key='ESIEM-EXPOSITOR-2027'):
        return self.client.post(URL, {'invitation_key': key})

    def payload(self, **overrides):
        data = {
            'company_name': '  Acme   Ingeniería ',
            'cif': 'B-12345678',
            'sector': 'energia',
            'address': 'Calle Mayor 1',
            'city': 'Sevilla',
            'postal_code': '41001',
            'company_phone': '954000000',
            'fax': '',
            'contact_name': 'Ana García',
            'contact_email': 'Ana@Acme.es',
            'contact_phone': '',
            'first_name': 'Ana',
            'last_name': 'García',
            'position': 'Directora General',
            'phone': '600000000',
            'email': 'ana@acme.es',
            'accept_privacy': 'on',
        }
        data.update(overrides)
        return data

    def test_form_requires_the_invitation_key(self):
        response = self.enter_key('NOPE')
        self.assertContains(response, 'La clave de invitación no es correcta')
        self.assertNotContains(response, 'Nombre de la empresa')
        # Skipping step 1 is not possible either.
        self.client.post(URL, self.payload())
        self.assertFalse(Company.objects.exists())

    def test_form_has_no_user_or_password_fields(self):
        response = self.client.get(self.enter_key().url)
        self.assertContains(response, 'Datos personales del firmante del contrato')
        self.assertContains(response, 'Nombre de la empresa')
        self.assertNotContains(response, 'Contraseña')
        self.assertNotContains(response, 'Forma de pago')
        self.assertContains(response, '1.500 € + IVA')  # the fee is still shown

    def test_registration_creates_interested_company_without_user(self):
        self.enter_key()
        response = self.client.post(URL, self.payload())
        self.assertRedirects(response, URL, fetch_redirect_response=False)
        company = Company.objects.get()
        self.assertEqual(company.name, 'Acme Ingeniería')
        self.assertEqual(company.status, Company.Status.INTERESTED)
        self.assertEqual((company.cif, company.sector, company.postal_code), ('B12345678', 'energia', '41001'))
        self.assertEqual((company.signer_name, company.signer_capacity), ('Ana García', 'Directora General'))
        self.assertFalse(User.objects.exists())
        # Same person as contact and signer: a single primary contact.
        self.assertEqual(company.contacts.get().email, 'ana@acme.es')
        self.assertTrue(company.contacts.get().is_primary)
        self.assertTrue(CRMNote.objects.filter(company=company, kind=CRMNote.Kind.SYSTEM, text__contains='Interesada').exists())
        # Thank-you page, shown once.
        self.assertContains(self.client.get(URL), '¡Solicitud recibida!')
        self.assertContains(self.client.get(URL), 'Clave de invitación')

    def test_designated_contact_is_primary_and_signer_is_kept(self):
        self.enter_key()
        self.client.post(URL, self.payload(contact_name='Luis Pérez', contact_email='rrhh@acme.es', contact_phone='611'))
        company = Company.objects.get()
        primary = company.contacts.get(is_primary=True)
        self.assertEqual((primary.email, primary.name, primary.phone), ('rrhh@acme.es', 'Luis Pérez', '611'))
        self.assertTrue(company.contacts.filter(email='ana@acme.es', position__contains='firmante').exists())
        self.assertEqual(company.contacts.count(), 2)

    def test_company_cannot_register_twice(self):
        Company.objects.create(name='Otra', cif='B12345678')
        self.enter_key()
        response = self.client.post(URL, self.payload())
        self.assertContains(response, 'ya ha enviado su formulario')
        response = self.client.post(URL, self.payload(company_name='OTRA', cif='B999'))
        self.assertContains(response, 'ya ha enviado su formulario')
        self.assertEqual(Company.objects.count(), 1)

    def test_invalid_postal_code_is_rejected(self):
        self.enter_key()
        response = self.client.post(URL, self.payload(postal_code='4100'))
        self.assertContains(response, 'código postal de 5 dígitos')
        self.assertFalse(Company.objects.exists())

    def test_changing_the_key_invalidates_pending_registration(self):
        self.enter_key()
        event = EventSettings.load()
        event.invitation_key = 'NUEVA-CLAVE'
        event.save()
        response = self.client.get(URL)
        self.assertContains(response, 'Clave de invitación')
        self.assertNotContains(response, 'Nombre de la empresa')
