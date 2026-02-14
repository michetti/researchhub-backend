from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets
from rest_framework.permissions import SAFE_METHODS, BasePermission, IsAuthenticatedOrReadOnly

from endorsements.models import Endorsement
from endorsements.serializers import EndorsementSerializer, EndorsementUpdateSerializer, \
    EndorsementCreateSerializer


class IsEndorsementOwner(BasePermission):
    """
    Custom permission to restrict non-safe methods to the endorser user.
    """
    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True

        return obj.endorser_user == request.user


class EndorsementsViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing endorsements, including listing, creating, updating, patching, and deleting.
    """
    queryset = Endorsement.objects.all().order_by("-created_date")
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['endorser_user', 'endorsed_user']
    permission_classes = [IsAuthenticatedOrReadOnly, IsEndorsementOwner]

    def get_serializer_class(self):
        if self.action == "create":
            return EndorsementCreateSerializer

        if self.action in ["partial_update", "update"]:
            return EndorsementUpdateSerializer

        return EndorsementSerializer

    def perform_create(self, serializer):
        serializer.save(endorser_user=self.request.user)
