terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }
}

locals {
  nodes = merge([
    for pool_name, pool in var.node_pools : {
      for index in range(pool.count) : format("%s-%02d", pool_name, index) => merge(pool, {
        name       = format("%s-%02d", pool_name, index)
        pool       = pool_name
        pool_index = index
        os         = lower(pool.os)
        role       = lower(pool.role)
        filesystem = lower(pool.filesystem)
        private_ip = cidrhost(var.subnet_cidr, pool.address_start + index)
      })
    }
  ]...)

  server_private_ip = one([
    for node in values(local.nodes) : node.private_ip if node.role == "server"
  ])

  common_tags = merge(var.tags, {
    Owner                      = "longhorn-infra"
    "longhorn.io/test-cluster" = var.cluster_name
  })

  node_labels = {
    for name, node in local.nodes : name => merge(
      node.labels,
      {
        "longhorn.io/test-node-pool" = node.pool
        "longhorn.io/test-node-os"   = node.os
      },
      node.data_volume_size > 0 ? {
        "longhorn.io/test-filesystem" = node.filesystem
      } : {}
    )
  }
}

resource "aws_instance" "node" {
  for_each = local.nodes

  ami                         = each.value.ami_id
  instance_type               = each.value.instance_type
  availability_zone           = var.availability_zone
  subnet_id                   = var.subnet_id
  private_ip                  = each.value.private_ip
  associate_public_ip_address = true
  source_dest_check           = false
  vpc_security_group_ids      = var.security_group_ids
  key_name                    = var.key_name

  user_data = templatefile(
    each.value.os == "windows" ? "${path.module}/templates/windows-agent.ps1.tftpl" : "${path.module}/templates/linux-node.sh.tftpl",
    {
      node_name            = each.value.name
      role                 = each.value.role
      server_url           = "https://${local.server_private_ip}:9345"
      server_private_ip    = local.server_private_ip
      cluster_token        = var.cluster_token
      rke2_version         = var.rke2_version
      cni                  = var.cni
      filesystem           = each.value.filesystem
      has_data_disk        = each.value.data_volume_size > 0
      labels               = [for key, value in local.node_labels[each.key] : "${key}=${value}"]
      taints               = each.value.taints
      csi_proxy_binary_url = var.csi_proxy_binary_url
      csi_proxy_sha256     = lower(var.csi_proxy_sha256)
    }
  )
  user_data_replace_on_change = true

  root_block_device {
    delete_on_termination = true
    encrypted             = true
    volume_size           = each.value.root_volume_size
    volume_type           = "gp3"
  }

  dynamic "ebs_block_device" {
    for_each = each.value.data_volume_size > 0 ? [each.value] : []
    content {
      device_name           = "/dev/sdf"
      delete_on_termination = true
      encrypted             = true
      volume_size           = ebs_block_device.value.data_volume_size
      volume_type           = ebs_block_device.value.data_volume_type
    }
  }

  tags = merge(local.common_tags, {
    Name                         = each.value.name
    "longhorn.io/test-node-os"   = each.value.os
    "longhorn.io/test-node-pool" = each.value.pool
  })

  lifecycle {
    precondition {
      condition     = each.value.address_start + each.value.pool_index > 1
      error_message = "node addresses must not use the subnet network or gateway addresses."
    }
  }
}
