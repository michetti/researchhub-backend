from django.urls import reverse
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
        """Anyone can list endorsements without logging in."""
        endorsement = Endorsement.objects.create(
            endorser_user=self.endorser,
            endorsed_user=self.endorsed,
            qualifier=Endorsement.Qualifier.COLLABORATED_ON_RESEARCH,
            anecdote="Worked on a study together.",
        )

        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        result_ids = [item["id"] for item in _results(response)]
        self.assertIn(endorsement.id, result_ids)

    def test_list_endorsements_filters_by_endorser_user(self):
        """Filtering by endorser user returns only endorsements from that user."""
        fixture = self._create_filter_fixture_endorsements()

        response = self.client.get(
            self.list_url, {"endorser_user": self.endorser.id}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        result_ids = {item["id"] for item in _results(response)}
        self.assertSetEqual(
            result_ids,
            {fixture["endorsement_1"].id, fixture["endorsement_2"].id},
        )

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

    def test_list_endorsements_filters_work_for_unauthenticated_requests(self):
        """Anonymous users can still use list filters on endorsements."""
        fixture = self._create_filter_fixture_endorsements()

        response = self.client.get(
            self.list_url, {"endorser_user": self.other_user.id}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        result_ids = [item["id"] for item in _results(response)]
        self.assertEqual(result_ids, [fixture["endorsement_3"].id])

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
