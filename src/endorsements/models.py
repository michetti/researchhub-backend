from django.db import models
from django.db.models import Q, F


class Endorsement(models.Model):
    class Qualifier(models.TextChoices):
        COLLABORATED_ON_RESEARCH = "collaborated_on_research", "Collaborated on research together"
        COLLEAGUE_AT_SAME_INSTITUTION = "colleague_at_same_institution", "Colleague at same institution"
        KNOW_PERSONALLY_OUTSIDE_WORK = "know_personally_outside_work", "Know personally (outside work)"
        MET_AT_CONFERENCE_OR_EVENT = "met_at_conference_or_event", "Met at conference/event"
        ACTIVE_IN_SAME_COMMUNITY = "active_in_same_community", "Active in same community"

    endorser_user = models.ForeignKey(
        to='user.User',
        on_delete=models.CASCADE,
        related_name='endorsements_given',
        help_text="The user that gave the endorsement",
        editable=False,
    )
    endorsed_user = models.ForeignKey(
        to='user.User',
        on_delete=models.CASCADE,
        related_name='endorsements_received',
        help_text="The user that was endorsed",
    )
    qualifier = models.CharField(
        max_length=64,
        choices=Qualifier.choices,
        blank=True,
        help_text="Context for how the endorser knows the endorsed user.",
    )
    anecdote = models.TextField(
        max_length=500,
        blank=True,
        help_text="A personal anecdote about the relationship.",
    )
    created_date = models.DateTimeField(auto_now_add=True)
    updated_date = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            # only one endorsement per user pair
            models.UniqueConstraint(
                fields=["endorser_user", "endorsed_user"],
                name="endorsement_pair_uq",
            ),
            # prevent self endorsements
            models.CheckConstraint(
                condition=~Q(endorser_user=F("endorsed_user")),
                name="endorsement_no_self_ck",
            ),
        ]
        indexes = [
            # for returning endorsements received by a given user
            models.Index(fields=["endorsed_user", "-created_date"], name="endorse_recv_created_ix"),
            # for returning endorsements given by a given user
            models.Index(fields=["endorser_user", "-created_date"], name="endorse_give_created_ix"),
        ]
