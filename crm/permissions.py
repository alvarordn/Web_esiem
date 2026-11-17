from rest_framework.permissions import BasePermission


class IsOrganizer(BasePermission):
    message = 'Solo la organización puede realizar esta acción.'

    def has_permission(self, request, view):
        return bool(request.user.is_authenticated and request.user.is_organizer)


class IsOrganizerOrCompanyUser(BasePermission):
    """Organizers see everything; company users only data of their own company (scoped in get_queryset)."""

    def has_permission(self, request, view):
        user = request.user
        return bool(user.is_authenticated and (user.is_organizer or user.has_portal_access))
