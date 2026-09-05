cloudflare_account_id = "a37fbb717276b94bcec2a5eb2be0a8d2"
cloudflare_zone_id    = "62bd19e18a62734396b24497c095d9e6"
domain                = "countyiq.net"
access_auth_domain    = "countyiq.cloudflareaccess.com"

access_allowed_emails = [
  "jarod.daws@protonmail.com",
]

# These bounds are deliberately conservative. The VPS guard hard-stops all
# writers at 8 GB total R2 storage, leaving headroom below the 10 GB allowance.
raw_retention_days             = 90
database_backup_retention_days = 7
backup_lock_days               = 3
