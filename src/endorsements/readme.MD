# Endorsements

## Technical decisions
- Initially created Endorsement as a related model inside the user app, but moved it to its own app to avoid bloating the user app.
- Considered using UUIDs for endorsements but decided to follow the pattern of the other entities.
- I'm not a fan of how Django names the tables, but decided to follow the pattern of the other entities.
- Considered creating an EndorsementQualifier entity but decided to keep it simple for the work trial. We can easily migrate to a qualifier entity if we need it. 
