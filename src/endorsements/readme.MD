# Endorsements

## Technical decisions
- Initially created endorsement code inside the `user` app, but moved it into its own app to avoid bloating `user`.
- Considered using UUIDs for endorsements, but decided to follow the pattern of the other entities in the codebase.
- Considered setting `db_table` to `endorsement`, but decided to follow the pattern of the other entities in the codebase.
- Fixed ordering to `-created_date` because it matches the current use case and avoids creating too many indexes.
- Enforced `endorser_user` or `endorsed_user` as required list query parameters because this matches our use cases, aligns with the indexes, prevents querying the entire table, and simplifies caching.
- Considered creating an `EndorsementQualifier` model, but decided to keep it simple using a `CharField` with `TextChoices`. We can migrate to a separate model later without losing data.
- Considered always including `endorser_author` in responses to simplify code, but decided to keep it optional for flexibility.
- Implemented caching for the endorsements list endpoint with a 5-minute TTL and first-page-only caching. The cache key is based on a prefix and normalized query parameters.
- Considered model signals (`post_save`/`post_delete`) for cache invalidation, but kept invalidation in the API write path for the first version to keep behavior simple and explicit. Signals would also not fully guarantee invalidation for all write paths (for example, bulk operations or raw SQL).
- Added type hints and `@override` annotations, following patterns in newer code.
- Added create-only per-user throttling with burst and daily limits to reduce spam while keeping reads unrestricted.
- Added serializer-level `AlreadyEndorsedConflict` (`409`) and reused it in `perform_create` so duplicate endorsement errors are consistent across pre-save validation and DB race-condition (`IntegrityError`) paths.
- Considered deleting `ENDORSEMENT_RECEIVED` notifications when an endorsement is removed, and it likely makes sense 
  for data hygiene; deferred for now because I could not find existing production patterns in the codebase for deleting notifications tied to deleted items.
