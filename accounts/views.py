from django.contrib.auth.views import LoginView
from django.shortcuts import redirect, render

from .forms import CompanyRegistrationForm, InvitationKeyForm, LoginForm, invitation_key_is_valid

# Session entry holding the key entered in step 1 (re-checked on every request,
# so changing the key in the admin invalidates half-finished registrations).
INVITATION_SESSION_KEY = 'registration_invitation_key'
# Name of the company that just sent the form, for the thank-you page.
SUBMITTED_SESSION_KEY = 'registration_submitted_company'


class EsiemLoginView(LoginView):
    template_name = 'accounts/login.html'
    authentication_form = LoginForm
    redirect_authenticated_user = True


def register(request):
    if request.user.is_authenticated:
        return redirect('crm:panel')

    submitted = request.session.pop(SUBMITTED_SESSION_KEY, None)
    if submitted:
        return render(request, 'accounts/register.html', {'step': 'done', 'company_name': submitted})

    if not invitation_key_is_valid(request.session.get(INVITATION_SESSION_KEY)):
        form = InvitationKeyForm(request.POST or None)
        if request.method == 'POST' and form.is_valid():
            request.session[INVITATION_SESSION_KEY] = form.cleaned_data['invitation_key']
            return redirect('accounts:register')
        return render(request, 'accounts/register.html', {'form': form, 'step': 'key'})

    form = CompanyRegistrationForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        company = form.save()
        request.session.pop(INVITATION_SESSION_KEY, None)
        request.session[SUBMITTED_SESSION_KEY] = company.name
        return redirect('accounts:register')  # POST/redirect/GET: a reload doesn't resubmit
    return render(request, 'accounts/register.html', {'form': form, 'step': 'details'})
