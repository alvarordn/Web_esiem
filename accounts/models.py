from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    is_company = models.BooleanField('es empresa', default=False)
    is_staff_admin = models.BooleanField('es organizador', default=False)
    company = models.ForeignKey(
        'crm.Company',
        verbose_name='empresa',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='users',
    )

    @property
    def is_organizer(self):
        """Organizers (and superusers) get the full CRM."""
        return self.is_staff_admin or self.is_superuser

    @property
    def has_portal_access(self):
        """Company users only reach the panel while their company is in the current ESIEM edition."""
        from core.models import current_edition

        return bool(self.is_company and self.company_id and self.company.edition == current_edition())

    def __str__(self):
        return self.get_full_name() or self.username
