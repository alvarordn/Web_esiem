import datetime

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from core.models import EventSettings

from .models import Objective


def sync_objectives(event):
    """Place the current edition's objectives at `days_before_event` from the event date.

    If the edition has no objectives yet (the event date was moved to a new year), they are copied,
    not done, from the most recent edition that has them. Past editions are never touched."""
    year, day = event.year, event.event_day
    current = list(Objective.objects.filter(edition=year))
    if not current:
        source = (Objective.objects.exclude(edition=year).order_by('-edition')
                  .values_list('edition', flat=True).first())
        if source is None:
            return
        Objective.objects.bulk_create(
            Objective(edition=year, title=o.title, days_before_event=o.days_before_event,
                      deadline=day - datetime.timedelta(days=o.days_before_event))
            for o in Objective.objects.filter(edition=source)
        )
        return
    moved = []
    for objective in current:
        deadline = day - datetime.timedelta(days=objective.days_before_event)
        if objective.deadline != deadline:
            objective.deadline = deadline
            moved.append(objective)
    # bulk_update skips Objective.save(), so the offsets are kept as they are.
    Objective.objects.bulk_update(moved, ['deadline'])


@receiver(post_save, sender=EventSettings)
def event_settings_saved(sender, instance, raw=False, **kwargs):
    if not raw:
        with transaction.atomic():
            sync_objectives(instance)
