from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.db import transaction
from django.utils.crypto import constant_time_compare

from core.models import EventSettings
from crm.models import Company, CompanyContact, CRMNote, Sector


def invitation_key_is_valid(key):
    expected = EventSettings.load().invitation_key
    return bool(expected) and constant_time_compare((key or '').strip(), expected)


def normalize_cif(cif):
    return ''.join(ch for ch in (cif or '').upper() if ch.isalnum())


class LoginForm(AuthenticationForm):
    username = forms.CharField(
        label='Usuario', widget=forms.TextInput(attrs={'autofocus': True, 'autocomplete': 'username'}),
        help_text='El usuario que recibiste en el correo de aceptación.',
    )

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if user.is_company and not user.is_organizer and not user.has_portal_access:
            raise forms.ValidationError(
                f'Este acceso era para una edición anterior de ESIEM. Para participar en '
                f'{EventSettings.load().edition_name}, envía de nuevo el formulario de participación.',
                code='past_edition',
            )


class InvitationKeyForm(forms.Form):
    """Step 1: the participation form is only shown after a valid key (sent with the invitation email)."""

    invitation_key = forms.CharField(
        label='Clave de invitación',
        help_text='La encontrarás en el correo de invitación de la organización.',
    )

    def clean_invitation_key(self):
        key = self.cleaned_data['invitation_key'].strip()
        if not invitation_key_is_valid(key):
            raise forms.ValidationError('La clave de invitación no es correcta.')
        return key


class CompanyRegistrationForm(forms.Form):
    """Step 2, the participation form. It creates the company in the CRM as «Interesada»; no portal
    account yet: the organizers accept or reject it, and the acceptance email carries the credentials."""

    company_name = forms.CharField(label='Nombre de la empresa', max_length=200)
    cif = forms.CharField(label='CIF de la empresa', max_length=20)
    sector = forms.ChoiceField(label='Sector', choices=Sector.choices)
    address = forms.CharField(label='Domicilio', max_length=255)
    city = forms.CharField(label='Población', max_length=120)
    postal_code = forms.RegexField(
        label='Código postal', regex=r'^\d{5}$', max_length=5,
        error_messages={'invalid': 'Introduce un código postal de 5 dígitos.'},
    )
    company_phone = forms.CharField(label='Teléfono de la empresa', max_length=40)
    fax = forms.CharField(label='Fax', max_length=40, required=False)

    contact_name = forms.CharField(
        label='Persona designada para contacto o representación', max_length=200,
        help_text='Recibirá los correos de la organización. Puede ser el propio firmante.',
    )
    contact_email = forms.EmailField(label='Email de contacto')
    contact_phone = forms.CharField(label='Teléfono de contacto', max_length=40, required=False)

    first_name = forms.CharField(label='Nombre', max_length=150)
    last_name = forms.CharField(label='Apellidos', max_length=150)
    position = forms.CharField(label='Calidad en la que firma', max_length=150, help_text='Por ejemplo: Director General, Apoderado, Responsable de RRHH.')
    phone = forms.CharField(label='Teléfono', max_length=40, required=False)
    email = forms.EmailField(label='Email')

    accept_privacy = forms.BooleanField(label='He leído y acepto la política de privacidad')

    ALREADY_REGISTERED = ('Esta empresa ya ha enviado su formulario de participación. '
                          'Si necesitas cambiar algún dato, ponte en contacto con la organización.')

    def clean_company_name(self):
        # Duplicates are checked within the current edition: past participants register again.
        name = ' '.join(self.cleaned_data['company_name'].split())
        if Company.objects.current().filter(name__iexact=name).exists():
            raise forms.ValidationError(self.ALREADY_REGISTERED)
        return name

    def clean_cif(self):
        cif = normalize_cif(self.cleaned_data['cif'])
        if not cif:
            raise forms.ValidationError('Introduce el CIF de la empresa.')
        current_cifs = Company.objects.current().exclude(cif='').values_list('cif', flat=True)
        if any(normalize_cif(other) == cif for other in current_cifs):
            raise forms.ValidationError(self.ALREADY_REGISTERED)
        return cif

    def clean_email(self):
        return self.cleaned_data['email'].lower()

    def clean_contact_email(self):
        return self.cleaned_data['contact_email'].lower()

    @transaction.atomic
    def save(self):
        data = self.cleaned_data
        company = Company.objects.create(
            name=data['company_name'],
            cif=data['cif'],
            sector=data['sector'],
            status=Company.Status.INTERESTED,
            address=data['address'],
            city=data['city'],
            postal_code=data['postal_code'],
            phone=data['company_phone'],
            fax=data['fax'],
            signer_name=f"{data['first_name']} {data['last_name']}",
            signer_capacity=data['position'],
        )
        # The designated contact is the primary contact (the acceptance email goes there);
        # the signer is kept as a second contact when it is a different person.
        same_person = data['contact_email'] == data['email']
        CompanyContact.objects.create(
            company=company, email=data['contact_email'], name=data['contact_name'],
            phone=data['contact_phone'] or (data['phone'] if same_person else ''),
            position=data['position'] if same_person else '', is_primary=True,
        )
        if not same_person:
            CompanyContact.objects.create(
                company=company, email=data['email'], name=company.signer_name,
                phone=data['phone'], position=f"{data['position']} (firmante)",
            )
        CRMNote.objects.create(
            company=company,
            kind=CRMNote.Kind.SYSTEM,
            text=(
                'Formulario de participación recibido: la empresa queda como «Interesada». '
                f'Firmante: {company.signer_name} ({data["email"]}). '
                f'Contacto: {data["contact_name"]} ({data["contact_email"]}).'
            ),
        )
        return company

