from typing import Any

from django.core.cache import cache
from django.db import connection
from django.urls import reverse
from django.test.utils import CaptureQueriesContext
from rest_framework import status
from rest_framework.test import APITestCase

from endorsements.cache import LIST_CACHE_VERSION_KEY
from endorsements.models import Endorsement
from user.tests.helpers import create_random_default_user


def _results(response: Any) -> Any:
    """Return paginated results or raw list from a list endpoint response."""
    if isinstance(response.data, dict) and "results" in response.data:
        return response.data["results"]
    return response.data


class EndorsementsViewSetTests(APITestCase):
    def setUp(self) -> None:
        """Create users and endpoint URLs used by endorsement view tests."""
        self.endorser = create_random_default_user("endorser")
        self.endorsed = create_random_default_user("endorsed")
        self.other_user = create_random_default_user("other-user")

        self.list_url = reverse("endorsements-list")

    def _create_filter_fixture_endorsements(self) -> dict[str, Endorsement]:
        """Create endorsements that let us test endorser and endorsed filters."""
        endorsement_1 = Endorsement.objects.create(
            endorser_user=self.endorser,
            endorsed_user=self.endorsed,
            qualifier=Endorsement.Qualifier.COLLABORATED_ON_RESEARCH,
        )
        endorsement_2 = Endorsement.objects.create(
            endorser_user=self.endorser,
            endorsed_user=self.other_user,
            qualifier=Endorsement.Qualifier.ACTIVE_IN_SAME_COMMUNITY,
        )
        endorsement_3 = Endorsement.objects.create(
            endorser_user=self.other_user,
            endorsed_user=self.endorsed,
            qualifier=Endorsement.Qualifier.MET_AT_CONFERENCE_OR_EVENT,
        )
        return {
            "endorsement_1": endorsement_1,
            "endorsement_2": endorsement_2,
            "endorsement_3": endorsement_3,
        }

    def test_list_endorsements_allows_unauthenticated_read(self) -> None:
        """Anyone can list endorsements when endorsed_user is provided."""
        endorsement = Endorsement.objects.create(
            endorser_user=self.endorser,
            endorsed_user=self.endorsed,
            qualifier=Endorsement.Qualifier.COLLABORATED_ON_RESEARCH,
            anecdote="Worked on a study together.",
        )

        response = self.client.get(
            self.list_url, {"endorsed_user": self.endorsed.id}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        result_ids = [item["id"] for item in _results(response)]
        self.assertIn(endorsement.id, result_ids)

    def test_qualifiers_endpoint_returns_ordered_code_and_label_list(self) -> None:
        """Qualifier endpoint should expose code/label pairs in declaration order."""
        url = reverse("endorsements-qualifiers")

        response = self.client.get(url, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        expected = [
            {"code": code, "label": label}
            for code, label in Endorsement.Qualifier.choices
        ]
        self.assertEqual(response.data, expected)

    def test_qualifiers_endpoint_allows_unauthenticated_read(self) -> None:
        """Qualifier endpoint is read-only and available to anonymous users."""
        url = reverse("endorsements-qualifiers")

        response = self.client.get(url, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_list_endorsements_rejects_without_endorsed_or_endorser_filter(self) -> None:
        """List requests are rejected when neither endorsed_user nor endorser_user is provided."""
        fixture = self._create_filter_fixture_endorsements()

        response = self.client.get(self.list_url, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data["non_field_errors"][0],
            "At least one of 'endorsed_user' or 'endorser_user' query parameters is required.",
        )
        self.assertIsNotNone(fixture["endorsement_1"].id)

    def test_list_endorsements_filters_by_endorsed_user(self) -> None:
        """Filtering by an endorsed user returns only endorsements for that user."""
        fixture = self._create_filter_fixture_endorsements()

        response = self.client.get(
            self.list_url, {"endorsed_user": self.endorsed.id}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        result_ids = {item["id"] for item in _results(response)}
        self.assertSetEqual(
            result_ids,
            {fixture["endorsement_1"].id, fixture["endorsement_3"].id},
        )

    def test_list_endorsements_filters_by_endorser_and_endorsed_intersection(self) -> None:
        """Applying both filters returns only the matching endorsement pair."""
        fixture = self._create_filter_fixture_endorsements()

        response = self.client.get(
            self.list_url,
            {
                "endorser_user": self.endorser.id,
                "endorsed_user": self.endorsed.id,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        result_ids = [item["id"] for item in _results(response)]
        self.assertEqual(result_ids, [fixture["endorsement_1"].id])

    def test_list_endorsements_filters_by_endorser_user(self) -> None:
        """Filtering by endorser user returns only endorsements from that user."""
        fixture = self._create_filter_fixture_endorsements()

        response = self.client.get(
            self.list_url, {"endorser_user": self.other_user.id}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        result_ids = [item["id"] for item in _results(response)]
        self.assertEqual(result_ids, [fixture["endorsement_3"].id])

    def test_list_endorsements_does_not_include_endorser_author_by_default(self) -> None:
        """Endorser author payload is omitted unless explicitly requested."""
        Endorsement.objects.create(
            endorser_user=self.endorser,
            endorsed_user=self.endorsed,
            qualifier=Endorsement.Qualifier.COLLABORATED_ON_RESEARCH,
        )

        response = self.client.get(
            self.list_url, {"endorsed_user": self.endorsed.id}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        first_result = _results(response)[0]
        self.assertNotIn("endorser_author", first_result)

    def test_list_endorsements_includes_is_reciprocal_false_without_reverse_endorsement(self) -> None:
        """Reciprocal flag is present and false when reverse endorsement does not exist."""
        Endorsement.objects.create(
            endorser_user=self.endorser,
            endorsed_user=self.endorsed,
            qualifier=Endorsement.Qualifier.COLLABORATED_ON_RESEARCH,
        )

        response = self.client.get(
            self.list_url, {"endorsed_user": self.endorsed.id}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        first_result = _results(response)[0]
        self.assertIn("is_reciprocal", first_result)
        self.assertFalse(first_result["is_reciprocal"])

    def test_list_endorsements_includes_is_reciprocal_true_with_reverse_endorsement(self) -> None:
        """Reciprocal flag is true when both users endorse each other."""
        Endorsement.objects.create(
            endorser_user=self.endorser,
            endorsed_user=self.endorsed,
            qualifier=Endorsement.Qualifier.COLLABORATED_ON_RESEARCH,
        )
        Endorsement.objects.create(
            endorser_user=self.endorsed,
            endorsed_user=self.endorser,
            qualifier=Endorsement.Qualifier.ACTIVE_IN_SAME_COMMUNITY,
        )

        response = self.client.get(
            self.list_url,
            {"endorser_user": self.endorser.id, "endorsed_user": self.endorsed.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        first_result = _results(response)[0]
        self.assertIn("is_reciprocal", first_result)
        self.assertTrue(first_result["is_reciprocal"])

    def test_list_endorsements_includes_authority_score(self) -> None:
        """Authority score reflects how many endorsements the endorser user has given."""
        fixture = self._create_filter_fixture_endorsements()

        response = self.client.get(
            self.list_url, {"endorsed_user": self.endorsed.id}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        score_by_id = {
            item["id"]: item["authority_score"] for item in _results(response)
        }
        self.assertEqual(score_by_id[fixture["endorsement_1"].id], 2)
        self.assertEqual(score_by_id[fixture["endorsement_3"].id], 1)

    def test_list_endorsements_includes_endorser_author_when_requested(self) -> None:
        """Endorser author payload is included when include_endorser_author=true."""
        Endorsement.objects.create(
            endorser_user=self.endorser,
            endorsed_user=self.endorsed,
            qualifier=Endorsement.Qualifier.COLLABORATED_ON_RESEARCH,
        )

        response = self.client.get(
            self.list_url,
            {
                "include_endorser_author": "true",
                "endorsed_user": self.endorsed.id,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        first_result = _results(response)[0]
        self.assertIn("endorser_author", first_result)
        self.assertEqual(
            set(first_result["endorser_author"].keys()),
            {"id", "first_name", "last_name", "profile_image"},
        )
        self.assertEqual(
            first_result["endorser_author"]["id"],
            self.endorser.author_profile.id,
        )

    def test_list_endorsements_filters_work_with_include_endorser_author(self) -> None:
        """Filtering still works when include_endorser_author=true is provided."""
        fixture = self._create_filter_fixture_endorsements()

        response = self.client.get(
            self.list_url,
            {
                "include_endorser_author": "true",
                "endorsed_user": self.endorsed.id,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = _results(response)
        result_ids = {item["id"] for item in results}
        self.assertSetEqual(
            result_ids,
            {fixture["endorsement_1"].id, fixture["endorsement_3"].id},
        )
        self.assertTrue(all("endorser_author" in item for item in results))

    def test_include_endorser_author_query_count_is_constant_as_results_grow(self) -> None:
        """Including endorser author should not introduce per-row query growth."""
        small_endorsed_user = create_random_default_user("small-endorsed")
        large_endorsed_user = create_random_default_user("large-endorsed")

        for idx in range(3):
            Endorsement.objects.create(
                endorser_user=create_random_default_user(f"small-endorser-{idx}"),
                endorsed_user=small_endorsed_user,
                qualifier=Endorsement.Qualifier.ACTIVE_IN_SAME_COMMUNITY,
            )

        for idx in range(15):
            Endorsement.objects.create(
                endorser_user=create_random_default_user(f"large-endorser-{idx}"),
                endorsed_user=large_endorsed_user,
                qualifier=Endorsement.Qualifier.ACTIVE_IN_SAME_COMMUNITY,
            )

        params_small = {
            "include_endorser_author": "true",
            "endorsed_user": small_endorsed_user.id,
        }
        params_large = {
            "include_endorser_author": "true",
            "endorsed_user": large_endorsed_user.id,
        }

        with CaptureQueriesContext(connection) as small_ctx:
            small_response = self.client.get(self.list_url, params_small, format="json")
        with CaptureQueriesContext(connection) as large_ctx:
            large_response = self.client.get(self.list_url, params_large, format="json")

        self.assertEqual(small_response.status_code, status.HTTP_200_OK)
        self.assertEqual(large_response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(small_ctx), len(large_ctx))

    def test_create_endorsement_requires_authentication(self) -> None:
        """Creating an endorsement is blocked for anonymous users."""
        payload = {
            "endorsed_user": self.endorsed.id,
            "qualifier": Endorsement.Qualifier.ACTIVE_IN_SAME_COMMUNITY,
            "anecdote": "Known through community work.",
        }

        response = self.client.post(self.list_url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(Endorsement.objects.count(), 0)

    def test_create_endorsement_is_throttled_after_burst_limit(self) -> None:
        """Creating too many endorsements in a short window should be throttled."""
        cache.clear()
        self.client.force_authenticate(user=self.endorser)

        for idx in range(3):
            target_user = create_random_default_user(f"throttle-target-{idx}")
            response = self.client.post(
                self.list_url,
                {
                    "endorsed_user": target_user.id,
                    "qualifier": Endorsement.Qualifier.ACTIVE_IN_SAME_COMMUNITY,
                    "anecdote": f"Burst throttle seed {idx}",
                },
                format="json",
            )
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        throttled_target = create_random_default_user("throttle-target-throttled")
        throttled_response = self.client.post(
            self.list_url,
            {
                "endorsed_user": throttled_target.id,
                "qualifier": Endorsement.Qualifier.ACTIVE_IN_SAME_COMMUNITY,
                "anecdote": "This request should be throttled.",
            },
            format="json",
        )

        self.assertEqual(
            throttled_response.status_code,
            status.HTTP_429_TOO_MANY_REQUESTS,
        )

    def test_create_endorsement_throttle_is_scoped_per_endorser(self) -> None:
        """One user's throttle state should not block another user's create."""
        cache.clear()

        self.client.force_authenticate(user=self.endorser)
        for idx in range(3):
            target_user = create_random_default_user(f"per-user-throttle-{idx}")
            response = self.client.post(
                self.list_url,
                {
                    "endorsed_user": target_user.id,
                    "qualifier": Endorsement.Qualifier.ACTIVE_IN_SAME_COMMUNITY,
                    "anecdote": f"Seed endorsement {idx}",
                },
                format="json",
            )
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        throttled_target = create_random_default_user("per-user-throttle-throttled")
        throttled_response = self.client.post(
            self.list_url,
            {
                "endorsed_user": throttled_target.id,
                "qualifier": Endorsement.Qualifier.ACTIVE_IN_SAME_COMMUNITY,
                "anecdote": "Should be throttled for first user.",
            },
            format="json",
        )
        self.assertEqual(
            throttled_response.status_code,
            status.HTTP_429_TOO_MANY_REQUESTS,
        )

        self.client.force_authenticate(user=self.other_user)
        other_user_target = create_random_default_user("per-user-throttle-other")
        other_user_response = self.client.post(
            self.list_url,
            {
                "endorsed_user": other_user_target.id,
                "qualifier": Endorsement.Qualifier.ACTIVE_IN_SAME_COMMUNITY,
                "anecdote": "Second user should not be throttled.",
            },
            format="json",
        )
        self.assertEqual(other_user_response.status_code, status.HTTP_201_CREATED)

    def test_create_endorsement_uses_authenticated_user_as_endorser(self) -> None:
        """The API uses the logged-in user as the endorser."""
        payload = {
            "endorsed_user": self.endorsed.id,
            "qualifier": Endorsement.Qualifier.MET_AT_CONFERENCE_OR_EVENT,
            "anecdote": "Met at a conference.",
        }
        self.client.force_authenticate(user=self.endorser)

        response = self.client.post(self.list_url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        endorsement = Endorsement.objects.get(id=response.data["id"])
        self.assertEqual(endorsement.endorser_user, self.endorser)
        self.assertEqual(endorsement.endorsed_user, self.endorsed)

    def test_create_endorsement_response_includes_is_reciprocal(self) -> None:
        """Create responses include reciprocal state for the created endorsement."""
        Endorsement.objects.create(
            endorser_user=self.endorsed,
            endorsed_user=self.endorser,
            qualifier=Endorsement.Qualifier.COLLABORATED_ON_RESEARCH,
        )
        payload = {
            "endorsed_user": self.endorsed.id,
            "qualifier": Endorsement.Qualifier.MET_AT_CONFERENCE_OR_EVENT,
            "anecdote": "Met at a conference.",
        }
        self.client.force_authenticate(user=self.endorser)

        response = self.client.post(self.list_url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("is_reciprocal", response.data)
        self.assertTrue(response.data["is_reciprocal"])

    def test_create_endorsement_response_includes_authority_score(self) -> None:
        """Create responses include authority score for the authenticated endorser user."""
        Endorsement.objects.create(
            endorser_user=self.endorser,
            endorsed_user=self.other_user,
            qualifier=Endorsement.Qualifier.COLLABORATED_ON_RESEARCH,
        )
        payload = {
            "endorsed_user": self.endorsed.id,
            "qualifier": Endorsement.Qualifier.MET_AT_CONFERENCE_OR_EVENT,
            "anecdote": "Met at a conference.",
        }
        self.client.force_authenticate(user=self.endorser)

        response = self.client.post(self.list_url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("authority_score", response.data)
        self.assertEqual(response.data["authority_score"], 2)

    def test_create_endorsement_rejects_duplicate_for_same_user_pair(self) -> None:
        """A user cannot endorse the same person more than once."""
        Endorsement.objects.create(
            endorser_user=self.endorser,
            endorsed_user=self.endorsed,
            qualifier=Endorsement.Qualifier.COLLABORATED_ON_RESEARCH,
        )
        payload = {
            "endorsed_user": self.endorsed.id,
            "qualifier": Endorsement.Qualifier.MET_AT_CONFERENCE_OR_EVENT,
            "anecdote": "Second endorsement attempt.",
        }
        self.client.force_authenticate(user=self.endorser)

        response = self.client.post(self.list_url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("You have already endorsed this user.", str(response.data))
        self.assertEqual(
            Endorsement.objects.filter(
                endorser_user=self.endorser, endorsed_user=self.endorsed
            ).count(),
            1,
        )

    def test_create_endorsement_rejects_self_endorsement(self) -> None:
        """A user cannot create an endorsement for themselves."""
        payload = {
            "endorsed_user": self.endorser.id,
            "qualifier": Endorsement.Qualifier.ACTIVE_IN_SAME_COMMUNITY,
            "anecdote": "Trying to self endorse.",
        }
        self.client.force_authenticate(user=self.endorser)

        response = self.client.post(self.list_url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("You cannot endorse yourself.", str(response.data))
        self.assertFalse(
            Endorsement.objects.filter(
                endorser_user=self.endorser, endorsed_user=self.endorser
            ).exists()
        )

    def test_update_endorsement_allows_owner_and_keeps_user_fields_immutable(self) -> None:
        """The owner can update editable fields but not the user fields."""
        endorsement = Endorsement.objects.create(
            endorser_user=self.endorser,
            endorsed_user=self.endorsed,
            qualifier=Endorsement.Qualifier.COLLABORATED_ON_RESEARCH,
            anecdote="Initial anecdote.",
        )
        detail_url = reverse("endorsements-detail", kwargs={"pk": endorsement.id})
        payload = {
            "qualifier": Endorsement.Qualifier.KNOW_PERSONALLY_OUTSIDE_WORK,
            "anecdote": "Updated anecdote.",
            "endorser_user": self.other_user.id,
            "endorsed_user": self.other_user.id,
        }
        self.client.force_authenticate(user=self.endorser)

        response = self.client.patch(detail_url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        endorsement.refresh_from_db()
        self.assertEqual(
            endorsement.qualifier, Endorsement.Qualifier.KNOW_PERSONALLY_OUTSIDE_WORK
        )
        self.assertEqual(endorsement.anecdote, "Updated anecdote.")
        self.assertEqual(endorsement.endorser_user, self.endorser)
        self.assertEqual(endorsement.endorsed_user, self.endorsed)

    def test_update_endorsement_forbidden_for_non_owner(self) -> None:
        """Non-owners cannot update someone else's endorsement."""
        endorsement = Endorsement.objects.create(
            endorser_user=self.endorser,
            endorsed_user=self.endorsed,
            qualifier=Endorsement.Qualifier.COLLABORATED_ON_RESEARCH,
            anecdote="Initial anecdote.",
        )
        detail_url = reverse("endorsements-detail", kwargs={"pk": endorsement.id})
        self.client.force_authenticate(user=self.other_user)

        response = self.client.patch(
            detail_url,
            {"anecdote": "Unauthorized update"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        endorsement.refresh_from_db()
        self.assertEqual(endorsement.anecdote, "Initial anecdote.")

    def test_delete_endorsement_forbidden_for_non_owner(self) -> None:
        """Non-owners cannot delete someone else's endorsement."""
        endorsement = Endorsement.objects.create(
            endorser_user=self.endorser,
            endorsed_user=self.endorsed,
            qualifier=Endorsement.Qualifier.COLLABORATED_ON_RESEARCH,
        )
        detail_url = reverse("endorsements-detail", kwargs={"pk": endorsement.id})
        self.client.force_authenticate(user=self.other_user)

        response = self.client.delete(detail_url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(Endorsement.objects.filter(id=endorsement.id).exists())

    def test_delete_endorsement_allows_owner(self) -> None:
        """Owners can delete their own endorsements."""
        endorsement = Endorsement.objects.create(
            endorser_user=self.endorser,
            endorsed_user=self.endorsed,
            qualifier=Endorsement.Qualifier.COLLABORATED_ON_RESEARCH,
        )
        detail_url = reverse("endorsements-detail", kwargs={"pk": endorsement.id})
        self.client.force_authenticate(user=self.endorser)

        response = self.client.delete(detail_url)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Endorsement.objects.filter(id=endorsement.id).exists())


class EndorsementsCacheTests(APITestCase):
    """Behavioral tests for endorsements list caching and invalidation."""

    def setUp(self) -> None:
        cache.clear()
        self.endorser = create_random_default_user("cache-endorser")
        self.endorsed = create_random_default_user("cache-endorsed")
        self.other_user = create_random_default_user("cache-other")
        self.list_url = reverse("endorsements-list")

        self.endorsement = Endorsement.objects.create(
            endorser_user=self.endorser,
            endorsed_user=self.endorsed,
            qualifier=Endorsement.Qualifier.COLLABORATED_ON_RESEARCH,
            anecdote="Initial cached endorsement.",
        )
        self.detail_url = reverse(
            "endorsements-detail",
            kwargs={"pk": self.endorsement.id},
        )

    def tearDown(self) -> None:
        cache.clear()

    def _list_for_endorsed_user(
        self,
        endorsed_user_id: int,
        **params: Any,
    ) -> Any:
        query_params = {"endorsed_user": endorsed_user_id, **params}
        return self.client.get(self.list_url, query_params, format="json")

    def test_list_page_1_cache_hit_after_initial_miss(self) -> None:
        """Page 1 list responses should be cached after the first request."""
        response_1 = self._list_for_endorsed_user(self.endorsed.id)
        response_2 = self._list_for_endorsed_user(self.endorsed.id)

        self.assertEqual(response_1.status_code, status.HTTP_200_OK)
        self.assertEqual(response_2.status_code, status.HTTP_200_OK)
        self.assertEqual(response_1["RH-Cache"], "miss")
        self.assertEqual(response_2["RH-Cache"], "hit")

    def test_list_page_2_is_not_cached(self) -> None:
        """Only the first page is cache-eligible for endorsements list."""
        # Default pagination size is 10. Create enough rows so page 2 is valid.
        for idx in range(10):
            Endorsement.objects.create(
                endorser_user=create_random_default_user(f"page-two-endorser-{idx}"),
                endorsed_user=self.endorsed,
                qualifier=Endorsement.Qualifier.ACTIVE_IN_SAME_COMMUNITY,
            )

        response_1 = self._list_for_endorsed_user(self.endorsed.id, page=2)
        response_2 = self._list_for_endorsed_user(self.endorsed.id, page=2)

        self.assertEqual(response_1.status_code, status.HTTP_200_OK)
        self.assertEqual(response_2.status_code, status.HTTP_200_OK)
        self.assertEqual(response_1["RH-Cache"], "miss")
        self.assertEqual(response_2["RH-Cache"], "miss")
        self.assertIsNone(cache.get(LIST_CACHE_VERSION_KEY))

    def test_create_bumps_list_cache_generation(self) -> None:
        """Creating an endorsement invalidates existing cached list responses."""
        self._list_for_endorsed_user(self.endorsed.id)
        self.assertEqual(
            self._list_for_endorsed_user(self.endorsed.id)["RH-Cache"],
            "hit",
        )
        current_version = cache.get(LIST_CACHE_VERSION_KEY)

        self.client.force_authenticate(user=self.other_user)
        create_response = self.client.post(
            self.list_url,
            {
                "endorsed_user": self.endorsed.id,
                "qualifier": Endorsement.Qualifier.ACTIVE_IN_SAME_COMMUNITY,
                "anecdote": "Cache invalidation via create.",
            },
            format="json",
        )

        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(cache.get(LIST_CACHE_VERSION_KEY), current_version + 1)
        self.assertEqual(
            self._list_for_endorsed_user(self.endorsed.id)["RH-Cache"],
            "miss",
        )
        self.assertEqual(
            self._list_for_endorsed_user(self.endorsed.id)["RH-Cache"],
            "hit",
        )

    def test_update_bumps_list_cache_generation(self) -> None:
        """Updating an endorsement invalidates existing cached list responses."""
        self._list_for_endorsed_user(self.endorsed.id)
        self.assertEqual(
            self._list_for_endorsed_user(self.endorsed.id)["RH-Cache"],
            "hit",
        )
        current_version = cache.get(LIST_CACHE_VERSION_KEY)

        self.client.force_authenticate(user=self.endorser)
        update_response = self.client.patch(
            self.detail_url,
            {"anecdote": "Cache invalidation via update."},
            format="json",
        )

        self.assertEqual(update_response.status_code, status.HTTP_200_OK)
        self.assertEqual(cache.get(LIST_CACHE_VERSION_KEY), current_version + 1)
        self.assertEqual(
            self._list_for_endorsed_user(self.endorsed.id)["RH-Cache"],
            "miss",
        )
        self.assertEqual(
            self._list_for_endorsed_user(self.endorsed.id)["RH-Cache"],
            "hit",
        )

    def test_delete_bumps_list_cache_generation(self) -> None:
        """Deleting an endorsement invalidates existing cached list responses."""
        self._list_for_endorsed_user(self.endorsed.id)
        self.assertEqual(
            self._list_for_endorsed_user(self.endorsed.id)["RH-Cache"],
            "hit",
        )
        current_version = cache.get(LIST_CACHE_VERSION_KEY)

        self.client.force_authenticate(user=self.endorser)
        delete_response = self.client.delete(self.detail_url)

        self.assertEqual(delete_response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(cache.get(LIST_CACHE_VERSION_KEY), current_version + 1)
        self.assertEqual(
            self._list_for_endorsed_user(self.endorsed.id)["RH-Cache"],
            "miss",
        )
        self.assertEqual(
            self._list_for_endorsed_user(self.endorsed.id)["RH-Cache"],
            "hit",
        )
