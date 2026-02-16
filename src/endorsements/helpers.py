from django.db import IntegrityError


def is_integrity_error_due_to_constraint(exc: IntegrityError, constraint_name: str) -> bool:
    """
    Return True when an IntegrityError maps to the given DB constraint name.
    """
    # check constraint name using psycopg / PostgreSQL diagnostics
    cause = getattr(exc, "__cause__", None)
    diag = getattr(cause, "diag", None)
    if getattr(diag, "constraint_name", None) == constraint_name:
        return True

    # check if the constraint name is in the error message as a last resort
    return constraint_name in str(exc)
