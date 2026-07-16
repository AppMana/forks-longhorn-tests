variable "cluster_name" {
  description = "Stable name used for the RKE2 cluster and EC2 tags."
  type        = string
}

variable "rke2_version" {
  description = "Pinned RKE2 release installed on every node."
  type        = string
}

variable "cluster_token" {
  description = "Shared RKE2 registration token."
  type        = string
  sensitive   = true
}

variable "cni" {
  description = "RKE2 CNI. Mixed Windows clusters support calico or flannel."
  type        = string
  default     = "calico"

  validation {
    condition     = contains(["calico", "flannel"], var.cni)
    error_message = "Windows RKE2 clusters require cni to be calico or flannel."
  }
}

variable "availability_zone" {
  type = string
}

variable "subnet_id" {
  type = string
}

variable "subnet_cidr" {
  type = string
}

variable "security_group_ids" {
  type = list(string)
}

variable "key_name" {
  type = string
}

variable "node_pools" {
  description = <<-EOT
    Declarative VM pools. Pools are flattened into one aws_instance resource so
    Linux and Windows nodes cannot drift into separate provisioning designs.
  EOT
  type = map(object({
    os               = string
    role             = string
    count            = number
    address_start    = number
    ami_id           = string
    instance_type    = string
    root_volume_size = optional(number, 64)
    data_volume_size = optional(number, 100)
    data_volume_type = optional(string, "gp3")
    filesystem       = optional(string, "")
    labels           = optional(map(string), {})
    taints           = optional(list(string), [])
  }))

  validation {
    condition = alltrue([
      for pool in values(var.node_pools) :
      contains(["linux", "windows"], lower(pool.os))
    ])
    error_message = "node pool os must be linux or windows."
  }

  validation {
    condition = alltrue([
      for pool in values(var.node_pools) :
      contains(["server", "agent"], lower(pool.role))
    ])
    error_message = "node pool role must be server or agent."
  }

  validation {
    condition = alltrue([
      for pool in values(var.node_pools) :
      lower(pool.os) != "windows" || lower(pool.role) == "agent"
    ])
    error_message = "RKE2 supports Windows agents, not Windows servers."
  }

  validation {
    condition = sum([
      for pool in values(var.node_pools) :
      lower(pool.role) == "server" ? pool.count : 0
    ]) == 1
    error_message = "exactly one RKE2 server is required by this test module."
  }

  validation {
    condition = alltrue([
      for pool in values(var.node_pools) :
      pool.data_volume_size == 0 || contains(
        lower(pool.os) == "windows" ? ["ntfs", "refs"] : ["ext4", "xfs"],
        lower(pool.filesystem)
      )
    ])
    error_message = "data disks require ext4/xfs on Linux or ntfs/refs on Windows."
  }
}

variable "csi_proxy_binary_url" {
  description = "Optional URL for the csi-proxy.exe build under test."
  type        = string
  default     = ""
}

variable "csi_proxy_sha256" {
  description = "Optional SHA-256 for csi-proxy_binary_url."
  type        = string
  default     = ""
}

variable "tags" {
  type    = map(string)
  default = {}
}
