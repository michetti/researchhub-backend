from typing import Any, override

from django.db.models import Count, Exists, OuterRef, Subquery, QuerySet
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status, viewsets, serializers
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import SAFE_METHODS, BasePermission, IsAuthenticatedOrReadOnly
from rest_framework.response import Response

from endorsements.cache import (
    bump_list_cache_version,
    get_cached_list_response,
    get_list_cache_key,
    set_cached_list_response,
)
from endorsements.models import Endorsement
from endorsements.serializers import EndorsementSerializer, EndorsementUpdateSerializer, \
    EndorsementCreateSerializer, INCLUDE_ENDORSER_AUTHOR_CTX_KEY
from endorsements.throttles import (
    EndorsementCreateBurstThrottle,
    EndorsementCreateSustainedThrottle,
)


class IsEndorsementOwner(BasePermission):
    """
    Custom permission to restrict non-safe methods to the current user's endorsements.
    """
    def has_object_permission(self, request, view, obj) -> bool:
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

    Cache is enabled for GET /api/endorsements/ only and has the following properties:
    - cache key based on normalized query parameters;
    - only the first page of results per cache key is cached;
    - cache TTL is kept short at 5 minutes;
    - any operation that modifies endorsements invalidates the cache.
    """
    queryset = Endorsement.objects.all().order_by("-created_date")
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['endorser_user', 'endorsed_user']
    permission_classes = [IsAuthenticatedOrReadOnly, IsEndorsementOwner]
    REQUIRED_LIST_FILTERS = ("endorsed_user", "endorser_user")
    CREATE_THROTTLE_CLASSES = [
        EndorsementCreateBurstThrottle,
        EndorsementCreateSustainedThrottle,
    ]

    def _ensure_required_list_filter_present(self) -> None:
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

    @override
    def get_queryset(self) -> QuerySet:
        # queryset for checking reciprocal endorsements
        reciprocal_endorsement_qs = Endorsement.objects.filter(
            endorser_user_id=OuterRef("endorsed_user_id"),
            endorsed_user_id=OuterRef("endorser_user_id"),
        )

        # queryset for calculating endorser authority score based on number of endorsements
        endorser_authority_score_qs = (
            Endorsement.objects.filter(endorser_user_id=OuterRef("endorser_user_id"))
            .order_by()  # safeguard to ensure no ordering in case it's set elsewhere (Meta.ordering, for example)
            .values("endorser_user_id")
            .annotate(score=Count("id"))
            .values("score")[:1]
        )

        # base queryset with relationship annotations
        qs = Endorsement.objects.annotate(
            is_reciprocal=Exists(reciprocal_endorsement_qs),
            authority_score=Subquery(endorser_authority_score_qs),
        ).order_by("-created_date")

        if self._is_include_endorser_author():
            # avoid N+1 queries by eager loading author profile
            qs = qs.select_related(
                "endorser_user__author_profile",
            )

        return qs

    @override
    def get_serializer_class(self) -> type[serializers.Serializer]:
        if self.action == "create":
            return EndorsementCreateSerializer

        if self.action in ["partial_update", "update"]:
            return EndorsementUpdateSerializer

        return EndorsementSerializer

    @override
    def get_throttles(self):
        # Rate-limit endorsement creation to reduce automated spam.
        if self.action == "create":
            return [throttle() for throttle in self.CREATE_THROTTLE_CLASSES]

        return super().get_throttles()

    @override
    def get_serializer_context(self) -> dict[str, Any]:
        ctx = super().get_serializer_context()
        ctx[INCLUDE_ENDORSER_AUTHOR_CTX_KEY] = self._is_include_endorser_author()
        return ctx

    @action(detail=False, methods=["get"], url_path="qualifiers", url_name="qualifiers")
    def qualifiers(self, request, *args, **kwargs) -> Response:
        data = [
            {"code": code, "label": label}
            for code, label in Endorsement.Qualifier.choices
        ]
        return Response(data)

    @override
    def list(self, request, *args, **kwargs) -> Response:
        self._ensure_required_list_filter_present()

        # return cached response if present
        cache_key = get_list_cache_key(request)
        cached_response = get_cached_list_response(cache_key)
        if cached_response is not None:
            response = Response(cached_response)
            response["RH-Cache"] = "hit"
            return response

        response = super().list(request, *args, **kwargs)

        # cache response if successful
        if cache_key is not None and response.status_code == status.HTTP_200_OK:
            set_cached_list_response(cache_key, response.data)

        response["RH-Cache"] = "miss"
        return response

    @override
    def perform_create(self, serializer) -> None:
        super().perform_create(serializer)
        bump_list_cache_version()

    @override
    def perform_update(self, serializer) -> None:
        super().perform_update(serializer)
        bump_list_cache_version()

    @override
    def perform_destroy(self, instance) -> None:
        super().perform_destroy(instance)
        bump_list_cache_version()
