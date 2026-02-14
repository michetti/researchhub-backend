from django.db import connection
from django.urls import reverse
from django.test.utils import CaptureQueriesContext
from rest_framework import status
from rest_framework.test import APITestCase

from endorsements.models import Endorsement
from user.tests.helpers import create_random_default_user


def _results(response):
    """Return paginated results or raw list from a list endpoint response."""
    if isinstance(response.data, dict) and "results" in response.data:
        return response.data["results"]
    return response.data


class EndorsementsViewSetTests(APITestCase):
    def setUp(self):
        """Create users and endpoint URLs used by endorsement view tests."""
        self.endorser = create_random_default_user("endorser")
        self.endorsed = create_random_default_user("endorsed")
        self.other_user = create_random_default_user("other-user")

        self.list_url = reverse("endorsements-list")

    def _create_filter_fixture_endorsements(self):
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

    def test_list_endorsements_allows_unauthenticated_read(self):
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

    def test_list_endorsements_rejects_without_endorsed_or_endorser_filter(self):
        """List requests are rejected when neither endorsed_user nor endorser_user is provided."""
        fixture = self._create_filter_fixture_endorsements()

        response = self.client.get(self.list_url, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data["non_field_errors"][0],
            "At least one of 'endorsed_user' or 'endorser_user' query parameters is required.",
        )
        self.assertIsNotNone(fixture["endorsement_1"].id)

    def test_list_endorsements_filters_by_endorsed_user(self):
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

    def test_list_endorsements_filters_by_endorser_and_endorsed_intersection(self):
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

    def test_list_endorsements_filters_by_endorser_user(self):
        """Filtering by endorser user returns only endorsements from that user."""
        fixture = self._create_filter_fixture_endorsements()

        response = self.client.get(
            self.list_url, {"endorser_user": self.other_user.id}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        result_ids = [item["id"] for item in _results(response)]
        self.assertEqual(result_ids, [fixture["endorsement_3"].id])

    def test_list_endorsements_does_not_include_endorser_author_by_default(self):
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

    def test_list_endorsements_includes_endorser_author_when_requested(self):
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

    def test_list_endorsements_filters_work_with_include_endorser_author(self):
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

    def test_include_endorser_author_query_count_is_constant_as_results_grow(self):
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

    def test_create_endorsement_requires_authentication(self):
        """Creating an endorsement is blocked for anonymous users."""
        payload = {
            "endorsed_user": self.endorsed.id,
            "qualifier": Endorsement.Qualifier.ACTIVE_IN_SAME_COMMUNITY,
            "anecdote": "Known through community work.",
        }

        response = self.client.post(self.list_url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(Endorsement.objects.count(), 0)

    def test_create_endorsement_uses_authenticated_user_as_endorser(self):
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

    def test_create_endorsement_rejects_duplicate_for_same_user_pair(self):
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

    def test_create_endorsement_rejects_self_endorsement(self):
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

    def test_update_endorsement_allows_owner_and_keeps_user_fields_immutable(self):
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

    def test_update_endorsement_forbidden_for_non_owner(self):
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

    def test_delete_endorsement_forbidden_for_non_owner(self):
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

    def test_delete_endorsement_allows_owner(self):
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
