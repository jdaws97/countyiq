variable "cloudflare_account_id" {
  description = "Cloudflare account containing CountyIQ."
  type        = string
}

variable "cloudflare_zone_id" {
  description = "Cloudflare zone ID for countyiq.net."
  type        = string
}

variable "domain" {
  description = "Public marketing hostname; the protected product uses app.<domain>."
  type        = string
  default     = "countyiq.net"

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9.-]*[a-z0-9]$", var.domain))
    error_message = "domain must be a lowercase DNS hostname."
  }
}

variable "access_auth_domain" {
  description = "Unique Cloudflare Access login domain."
  type        = string
  default     = "countyiq.cloudflareaccess.com"
}

variable "access_allowed_emails" {
  description = "Exact email addresses invited to the private alpha."
  type        = set(string)

  validation {
    condition = (
      length(var.access_allowed_emails) > 0 &&
      alltrue([for address in var.access_allowed_emails : can(regex("^[^@[:space:]]+@[^@[:space:]]+\\.[^@[:space:]]+$", address))])
    )
    error_message = "At least one valid invited email address is required."
  }
}

variable "raw_bucket_name" {
  type    = string
  default = "countyiq-raw"
}

variable "operator_email" {
  description = "Single owner allowed to access Dagster; independent of tester access."
  type        = string

  validation {
    condition     = can(regex("^[^@[:space:]]+@[^@[:space:]]+\\.[^@[:space:]]+$", var.operator_email))
    error_message = "operator_email must be one exact email address."
  }
}

variable "backup_bucket_name" {
  type    = string
  default = "countyiq-backups"
}

variable "raw_retention_days" {
  description = "Maximum R2 age for raw source objects."
  type        = number
  default     = 90

  validation {
    condition     = var.raw_retention_days >= 7 && var.raw_retention_days <= 180
    error_message = "Raw retention must remain between 7 and 180 days."
  }
}

variable "database_backup_retention_days" {
  description = "Maximum R2 age for database dumps and manifests."
  type        = number
  default     = 7

  validation {
    condition     = var.database_backup_retention_days >= 4 && var.database_backup_retention_days <= 30
    error_message = "Database backup retention must remain between 4 and 30 days."
  }
}

variable "backup_lock_days" {
  description = "Minimum immutable period for objects in the backup bucket."
  type        = number
  default     = 3

  validation {
    condition = (
      var.backup_lock_days >= 1 &&
      var.backup_lock_days < var.database_backup_retention_days
    )
    error_message = "Backup lock must be at least one day and shorter than backup retention."
  }
}

variable "publish_marketing_site" {
  description = "Remove the temporary apex Access gate only after verifying the split origin and app Access. See account-workspaces.md."
  type        = bool
  default     = false
}
