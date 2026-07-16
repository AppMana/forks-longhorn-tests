variable "lh_aws_access_key" {
  description = "Optional AWS access key; the standard AWS credential chain is used when unset."
  type        = string
  default     = null
  sensitive   = true
}

variable "lh_aws_secret_key" {
  description = "Optional AWS secret key; the standard AWS credential chain is used when unset."
  type        = string
  default     = null
  sensitive   = true
}

variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "aws_availability_zone" {
  type    = string
  default = "us-east-1a"
}

variable "aws_ssh_public_key_file_path" {
  type    = string
  default = "~/.ssh/id_rsa.pub"
}

variable "aws_ssh_private_key_file_path" {
  type    = string
  default = "~/.ssh/id_rsa"
}

variable "admin_cidrs" {
  description = "CIDRs allowed to reach SSH, RDP, and the Kubernetes API."
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

variable "cluster_name" {
  type    = string
  default = "longhorn-windows"
}

variable "k8s_distro_name" {
  description = "Compatibility with the existing test pipeline. This workspace is RKE2-only."
  type        = string
  default     = "rke2"

  validation {
    condition     = var.k8s_distro_name == "rke2"
    error_message = "mixed-rke2 provisions RKE2 because k3s cannot add Windows agents."
  }
}

variable "k8s_distro_version" {
  type    = string
  default = "v1.34.2+rke2r1"
}

variable "linux_ami_id" {
  description = "Optional Ubuntu AMI override."
  type        = string
  default     = null
}

variable "windows_ami_id" {
  description = "Optional Windows Server 2022 Full Base AMI override."
  type        = string
  default     = null
}

variable "controlplane_instance_type" {
  type    = string
  default = "m6i.xlarge"
}

variable "linux_worker_instance_type" {
  type    = string
  default = "m6i.xlarge"
}

variable "windows_worker_instance_type" {
  type    = string
  default = "m6i.xlarge"
}

variable "linux_worker_count" {
  description = "Three workers preserve the existing Linux three-node E2E topology."
  type        = number
  default     = 3
}

variable "windows_ntfs_worker_count" {
  type    = number
  default = 2
}

variable "windows_refs_worker_count" {
  type    = number
  default = 1
}

variable "worker_data_volume_size" {
  type    = number
  default = 100
}

variable "csi_proxy_binary_url" {
  description = "Optional csi-proxy.exe artifact URL, including custom ReFS builds."
  type        = string
  default     = ""
}

variable "csi_proxy_sha256" {
  type    = string
  default = ""
}

variable "create_load_balancer" {
  description = "Compatibility input for the shared pipeline; no load balancer is needed."
  type        = bool
  default     = false

  validation {
    condition     = !var.create_load_balancer
    error_message = "mixed-rke2 does not create a Rancher load balancer."
  }
}
