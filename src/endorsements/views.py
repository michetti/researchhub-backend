from django.db.models import Exists, OuterRef
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import SAFE_METHODS, BasePermission, IsAuthenticatedOrReadOnly

from endorsements.models import Endorsement
from endorsements.serializers import EndorsementSerializer, EndorsementUpdateSerializer, \
    EndorsementCreateSerializer, INCLUDE_ENDORSER_AUTHOR_CTX_KEY


class IsEndorsementOwner(BasePermission):
    """
    Custom permission to restrict non-safe methods to the current user's endorsements.
    """
    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True

        return obj.endorser_user == request.user


class EndorsementsViewSet(viewsets.ModelViewSet):
    """
    Endorsements must be filtered by endorser or endorsed user (or both):
    Ex: GET /api/endorsements/?endorser_user=1 (endorsements given by user 1)
    Ex: GET /api/endorsements/?endorsed_user=2 (endorsements received by user 2)
    Ex: GET /api/endorsements/?endorser_user=1&endorsed_user=2 (can be used to check if user 1 endorsed user 2)

    It supports including a minimally hydrated endorser's author profile in the response:
    Ex: GET /api/endorsements/1/?include_endorser_author=true
    Ex: GET /api/endorsements/?endorsed_user=1&include_endorser_author=true

    Results are paginated and ordered by creation date in descending order.
    """
    queryset = Endorsement.objects.all().order_by("-created_date")
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['endorser_user', 'endorsed_user']
    permission_classes = [IsAuthenticatedOrReadOnly, IsEndorsementOwner]
    REQUIRED_LIST_FILTERS = ("endorsed_user", "endorser_user")

    def _ensure_required_list_filter_present(self):
        has_required_filter = any(
            self.request.query_params.get(param)
            for param in self.REQUIRED_LIST_FILTERS
        )
        if not has_required_filter:
            raise ValidationError(
                {
                    "non_field_errors": [
                        "At least one of 'endorsed_user' or 'endorser_user' query parameters is required."
                    ]
                }
            )

    def _is_include_endorser_author(self) -> bool:
        # ensure we only include the author profile if the parameter is exactly the string "true" or "True"
        param = self.request.query_params.get("include_endorser_author", "false")
        return param.lower() == "true"

    def get_queryset(self):
        # queryset for checking reciprocal endorsements
        reciprocal_endorsement_qs = Endorsement.objects.filter(
            endorser_user_id=OuterRef("endorsed_user_id"),
            endorsed_user_id=OuterRef("endorser_user_id"),
        )

        # base queryset with is_reciprocal annotation
        qs = Endorsement.objects.annotate(
            is_reciprocal=Exists(reciprocal_endorsement_qs)
        ).order_by("-created_date")

        if self._is_include_endorser_author():
            # avoid N+1 queries by eager loading author profile
            qs = qs.select_related(
                "endorser_user__author_profile",
            )

        return qs

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx[INCLUDE_ENDORSER_AUTHOR_CTX_KEY] = self._is_include_endorser_author()
        return ctx

    def list(self, request, *args, **kwargs):
        self._ensure_required_list_filter_present()
        return super().list(request, *args, **kwargs)

    def get_serializer_class(self):
        if self.action == "create":
            return EndorsementCreateSerializer

        if self.action in ["partial_update", "update"]:
            return EndorsementUpdateSerializer

        return EndorsementSerializer

    def perform_create(self, serializer):
        serializer.save(endorser_user=self.request.user)
