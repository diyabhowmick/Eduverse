variable "env" {
  description = "staging or production"
  type        = string
  validation {
    condition     = contains(["staging", "production"], var.env)
    error_message = "env must be staging or production."
  }
}
variable "region" {
  type    = string
  default = "ap-south-1" # Mumbai
}
variable "domain" {
  description = "Full host name, for example eduverse.zprox.ai or staging.eduverse.zprox.ai"
  type        = string
}
variable "route53_zone_id" {
  description = "Hosted zone for the domain. Leave empty to create the DNS record yourself."
  type        = string
  default     = ""
}
variable "acme_email" {
  description = "Email Let's Encrypt writes to about the HTTPS certificate"
  type        = string
}
variable "instance_type" {
  type    = string
  default = "t3.large" # 2 vCPU, 8 GB: API + worker + M1 on one box
}
variable "root_volume_gb" {
  type    = number
  default = 60
}
variable "db_instance_class" {
  type    = string
  default = "db.t4g.small"
}
variable "db_storage_gb" {
  type    = number
  default = 20
}
variable "db_backup_days" {
  type    = number
  default = 7
}
variable "superadmin_email" {
  type = string
}
variable "alarm_email" {
  description = "Gets an email when the server or database is in trouble. Empty = no alarms by email."
  type        = string
  default     = ""
}
