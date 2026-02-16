from rest_framework.throttling import UserRateThrottle


class EndorsementCreateBurstThrottle(UserRateThrottle):
    """
    Limit how quickly a user can create endorsements in a short window.
    """

    scope = "endorsement.create.burst"
    rate = "3/min"


class EndorsementCreateSustainedThrottle(UserRateThrottle):
    """
    Limit daily endorsement volume per user to reduce scripted spam.
    """

    scope = "endorsement.create.sustained"
    rate = "30/day"

