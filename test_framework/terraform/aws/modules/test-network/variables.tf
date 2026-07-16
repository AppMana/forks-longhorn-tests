variable "name" {
  description = "Name prefix applied to the test network resources."
  type        = string
}

variable "availability_zone" {
  description = "Availability zone containing the single test subnet."
  type        = string
}

variable "vpc_cidr" {
  description = "CIDR used by the isolated test VPC."
  type        = string
  default     = "10.42.0.0/16"
}

variable "subnet_cidr" {
  description = "CIDR used by the VM subnet."
  type        = string
  default     = "10.42.1.0/24"
}

variable "admin_cidrs" {
  description = "CIDRs allowed to reach SSH, RDP, and the Kubernetes API."
  type        = list(string)
}

variable "ssh_public_key" {
  description = "OpenSSH public key installed on Linux and used to decrypt Windows administrator credentials."
  type        = string
}

variable "tags" {
  description = "Additional tags applied to every resource."
  type        = map(string)
  default     = {}
}
