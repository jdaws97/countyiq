"""CountyIQ API package bootstrap."""

from dotenv import load_dotenv

# Package initialization happens before api.main imports settings-dependent
# modules, so local .env values are available when module-level configuration
# is resolved. Production Compose still supplies an explicit environment.
load_dotenv()
