from rest_framework import serializers
from rest_framework.validators import UniqueTogetherValidator

from endorsements.models import Endorsement
from user.serializers import DynamicAuthorSerializer

ENDORSEMENT_FIELDS = [
    "id",
    "endorser_user",
    "endorsed_user",
    "qualifier",
    "anecdote",
    "created_date",
    "updated_date"
]

INCLUDE_ENDORSER_AUTHOR_CTX_KEY = "include_endorser_author"


class EndorsementSerializer(serializers.ModelSerializer):
    """
    Serializer for the Endorsement model with support for including the endorser's author profile.
    """
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
        fields = [*ENDORSEMENT_FIELDS, "endorser_author"]

    def __init__(self, *args, **kwargs):
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
        fields = ENDORSEMENT_FIELDS
        validators = [
            UniqueTogetherValidator(
                queryset=Endorsement.objects.all(),
                fields=["endorser_user", "endorsed_user"],
                message="You have already endorsed this user.",
            )
        ]

    def validate(self, attrs):
        if attrs["endorser_user"] == attrs["endorsed_user"]:
            raise serializers.ValidationError(
                {"endorsed_user": "You cannot endorse yourself."}
            )

        return attrs

    def to_representation(self, instance):
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
        fields = ENDORSEMENT_FIELDS

    def to_representation(self, instance):
        # serialize all fields
        return EndorsementSerializer(instance, context=self.context).data
