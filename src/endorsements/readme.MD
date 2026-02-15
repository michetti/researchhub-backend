# Endorsements

## Technical decisions
- Initially created Endorsement code inside the user app, but moved into its own app to avoid bloating the user app.
- Considered using UUIDs for endorsements but decided to follow the pattern of the other entities in the codebase.
- Considered setting db_table to 'endorsement' but decided to follow the pattern of the other entities in the codebase.
- Fixed ordering to `-created_date` given it is what the only use case we have currently requires and to avoid 
  creating too many indexes in the database.
- Decided to enforce `endorser_user` or `endorsed_user` as required list query parameter since it matches our uses 
  cases, matches the indexes in the database, prevents querying the entire table and simplifies caching. 
- Considered creating an `EndorsementQualifier` model but decided to keep it simple using a `CharField` with 
  `TextChoices`. We can easily migrate this to a separated model later if needed without losing data.
- Considered always including `endorser_author` in the response to simplify the code, but decided to make it an 
  optional parameter instead to make the API more flexible.
- Returning `authority_score` field in the response as a way to indicate how meaningful the endorsement is. For now, 
  it is based on the number of endorsements for the endorser user. Later it should be changed to a more sophisticated 
  calculation based on PageRank, for example.
- Implemented caching for endorsements list endpoint. Decided to go with a TTL of 5 minutes and cache only the first 
  page of results. The cache key is based on a prefix and the normalized query parameters.
- Added type hints and override annotations as the newer code seems to be using them.
- Added create-only per-user throttling with burst and daily limits to prevent spam while keeping reads unrestricted.
