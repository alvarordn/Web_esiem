from django.test import TestCase
from django.urls import reverse

from crm.models import Company


class PublicPagesTests(TestCase):
    def test_public_pages_render(self):
        for name in ('core:home', 'core:letter', 'core:etsi', 'core:event', 'core:exhibitors', 'core:directory', 'core:chairs',
                     'core:organizers', 'core:follow', 'accounts:register', 'accounts:login'):
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 200)
        self.assertEqual(self.client.get('/ediciones/').status_code, 404)

    def test_event_page_shows_programme(self):
        response = self.client.get(reverse('core:event'))
        self.assertContains(response, 'Mesa redonda A')
        self.assertContains(response, '17:30')
        for page in ('aviso-legal', 'privacidad', 'cookies'):
            self.assertEqual(self.client.get(reverse('core:legal', args=[page])).status_code, 200)
        self.assertEqual(self.client.get('/legal/otra/').status_code, 404)

    def test_directory_lists_only_confirmed_companies(self):
        Company.objects.create(name='Confirmada SA', status=Company.Status.CONFIRMED)
        Company.objects.create(name='Interesada SA', status=Company.Status.INTERESTED)
        response = self.client.get(reverse('core:directory'))
        self.assertContains(response, 'Confirmada SA')
        self.assertNotContains(response, 'Interesada SA')

    def test_panel_requires_login(self):
        response = self.client.get(reverse('crm:panel'))
        self.assertRedirects(response, f"{reverse('accounts:login')}?next={reverse('crm:panel')}")
