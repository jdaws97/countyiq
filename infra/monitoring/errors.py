"""Safe user-facing errors shared by monitoring setup commands."""


class ConfigurationError(ValueError):
    """A fixed, credential-free message safe to show during account setup."""
