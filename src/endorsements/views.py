from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets
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
    Endorsements can be filtered by endorser and endorsed user:
    Ex: GET /api/endorsements/?endorser_user=1&endorsed_user=2

    It supports including a minimally hydrated endorser's author profile in the response:
    Ex: GET /api/endorsements/1/?include_endorser_author=true
    Ex: GET /api/endorsements/?endorsed_user=1&include_endorser_author=true

    Results are paginated and ordered by creation date in descending order.
    """
    queryset = Endorsement.objects.all().order_by("-created_date")
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['endorser_user', 'endorsed_user']
    permission_classes = [IsAuthenticatedOrReadOnly, IsEndorsementOwner]

    def _is_include_endorser_author(self) -> bool:
        # ensure we only include the author profile if the parameter is exactly the string "true" or "True"
        param = self.request.query_params.get("include_endorser_author", "false")
        return param.lower() == "true"

    def get_queryset(self):
        qs = Endorsement.objects.all().order_by("-created_date")

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

    def get_serializer_class(self):
        if self.action == "create":
            return EndorsementCreateSerializer

        if self.action in ["partial_update", "update"]:
            return EndorsementUpdateSerializer

        return EndorsementSerializer

    def perform_create(self, serializer):
        serializer.save(endorser_user=self.request.user)
