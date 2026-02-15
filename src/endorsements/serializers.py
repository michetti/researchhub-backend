from rest_framework import serializers
from rest_framework.validators import UniqueTogetherValidator

from endorsements.models import Endorsement
from user.serializers import DynamicAuthorSerializer

INCLUDE_ENDORSER_AUTHOR_CTX_KEY = "include_endorser_author"


class EndorsementSerializer(serializers.ModelSerializer):
    """
    Serializer for the Endorsement model with support for including the endorser's author profile.
    """
    is_reciprocal = serializers.SerializerMethodField()
    authority_score = serializers.SerializerMethodField()
    endorser_author = DynamicAuthorSerializer(
        source="endorser_user.author_profile",
        read_only=True,
        _include_fields=[
            "id",
            "first_name",
            "last_name",
            "profile_image",
        ],
    )

    class Meta:
        model = Endorsement
        fields = [
            "id",
            "endorser_user",
            "endorsed_user",
            "is_reciprocal",
            "qualifier",
            "anecdote",
            "authority_score",
            "created_date",
            "updated_date",
            "endorser_author",
        ]

    @staticmethod
    def get_is_reciprocal(obj) -> bool:
        # prefer queryset annotation to avoid per-row lookups on list / retrieve endpoints.
        if hasattr(obj, "is_reciprocal"):
            return bool(obj.is_reciprocal)

        # fallback to manual check if queryset annotation is not available.
        return Endorsement.objects.filter(
            endorser_user_id=obj.endorsed_user_id,
            endorsed_user_id=obj.endorser_user_id,
        ).exists()

    @staticmethod
    def get_authority_score(obj) -> int:
        # prefer queryset annotation to avoid per-row lookups on list / retrieve endpoints.
        if hasattr(obj, "authority_score"):
            return int(obj.authority_score)

        # fallback to manual count if queryset annotation is not available.
        return Endorsement.objects.filter(
            endorser_user_id=obj.endorser_user_id,
        ).count()

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        if not self.context.get(INCLUDE_ENDORSER_AUTHOR_CTX_KEY):
            self.fields.pop("endorser_author", None)


class EndorsementCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating endorsements, ensuring uniqueness and self-endorsement checks.
    """
    endorser_user = serializers.HiddenField(default=serializers.CurrentUserDefault())

    class Meta:
        model = Endorsement
        fields = [
            "id",
            "endorser_user",
            "endorsed_user",
            "qualifier",
            "anecdote",
            "created_date",
            "updated_date",
        ]
        validators = [
            UniqueTogetherValidator(
                queryset=Endorsement.objects.all(),
                fields=["endorser_user", "endorsed_user"],
                message="You have already endorsed this user.",
            )
        ]

    def validate(self, attrs) -> dict:
        if attrs["endorser_user"] == attrs["endorsed_user"]:
            raise serializers.ValidationError(
                {"endorsed_user": "You cannot endorse yourself."}
            )

        return attrs

    def to_representation(self, instance) -> dict:
        # serialize all fields
        return EndorsementSerializer(instance, context=self.context).data


class EndorsementUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for updating endorsements, ensuring the owner can only modify editable fields.
    """
    endorser_user = serializers.PrimaryKeyRelatedField(read_only=True)
    endorsed_user = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = Endorsement
        fields = [
            "id",
            "endorser_user",
            "endorsed_user",
            "qualifier",
            "anecdote",
            "created_date",
            "updated_date",
        ]

    def to_representation(self, instance) -> dict:
        # serialize all fields
        return EndorsementSerializer(instance, context=self.context).data
