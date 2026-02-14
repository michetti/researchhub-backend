# Endorsements

## Technical decisions
- Initially created Endorsement code inside the user app, but moved into its own app to avoid bloating the user app.
- Considered using UUIDs for endorsements but decided to follow the pattern of the other entities in the codebase.
- Considered setting db_table to 'endorsement' but decided to follow the pattern of the other entities in the codebase.
- Fixed ordering to `-created_date` given it is what the only use case we have currently requires and to avoid 
  creating too many indexes in the database.
- Considered creating an `EndorsementQualifier` model but decided to keep it simple using a `CharField` with 
  `TextChoices`. We can easily migrate this to a separated model later if needed without losing data.
- Considered always including `endorser_author` in the response to simplify the code, but decided to make it an 
  optional parameter instead to make the API more flexible.
