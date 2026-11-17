"""Portal credentials sent in the acceptance email.

The username is derived from the company name ("Acme Ingeniería, S.L." -> "acme-ingenieria"),
the password is random. Both are generated when the organizer loads the acceptance template and
are only stored (as a user) when the acceptance is actually sent/registered.
"""
import re

from django.contrib.auth import get_user_model
from django.utils.crypto import get_random_string
from django.utils.text import slugify

# Legal-form suffixes dropped from the username.
_LEGAL_FORMS = re.compile(r'[\s,]+(s\.?\s?a\.?\s?u?\.?|s\.?\s?l\.?\s?u?\.?|s\.?\s?c\.?\s?a\.?|s\.?\s?coop\.?)$', re.IGNORECASE)
# No look-alike characters (0/O, 1/l/I), so it can be typed from the email without mistakes.
_PASSWORD_CHARS = 'abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789'
USERNAME_MAX = 30


def company_portal_user(company):
    return get_user_model().objects.filter(company=company, is_company=True).order_by('pk').first()


def suggest_username(company):
    """Existing portal user of the company, or a free username based on its name."""
    existing = company_portal_user(company)
    if existing:
        return existing.username
    base = slugify(_LEGAL_FORMS.sub('', company.name.strip()))[:USERNAME_MAX].strip('-') or 'empresa'
    users = get_user_model().objects
    candidate, n = base, 2
    while users.filter(username__iexact=candidate).exists():
        suffix = f'-{n}'
        candidate = f'{base[:USERNAME_MAX - len(suffix)]}{suffix}'
        n += 1
    return candidate


def generate_password():
    return get_random_string(10, _PASSWORD_CHARS)


def username_problem(company, username):
    """Error message if `username` can't be used for this company's portal account, else ''."""
    if not re.fullmatch(r'[\w.@+-]{3,150}', username or ''):
        return 'El usuario debe tener al menos 3 caracteres (letras, números y . @ + - _).'
    clash = get_user_model().objects.filter(username__iexact=username).first()
    if clash and not (clash.is_company and clash.company_id == company.pk):
        return f'El usuario «{username}» ya existe. Escribe otro en el recuadro de acceso al portal.'
    return ''


def grant_access(company, username, password):
    """Create (or reactivate and reset) the company's portal user. Returns the user."""
    User = get_user_model()
    user = company_portal_user(company)
    if user is None:
        user = User(username=username, is_company=True, company=company)
        contact = company.primary_contact
        if contact:
            user.email = contact.email
            first, _, last = (contact.name or '').partition(' ')
            user.first_name, user.last_name = first[:150], last[:150]
    user.username = username  # the one written in the email (the organizer may have edited it)
    user.is_active = True
    user.set_password(password)
    user.save()
    company.portal_password = password
    company.save(update_fields=['portal_password', 'updated_at'])
    return user


def current_credentials(company):
    """Username/password already given to the company (to resend them), or None."""
    user = company_portal_user(company)
    if user and company.portal_password and user.check_password(company.portal_password):
        return {'username': user.username, 'password': company.portal_password}
    return None


def revoke_access(company):
    """Rejected companies can no longer log in (users are kept, not deleted)."""
    return get_user_model().objects.filter(company=company, is_company=True, is_active=True).update(is_active=False)
