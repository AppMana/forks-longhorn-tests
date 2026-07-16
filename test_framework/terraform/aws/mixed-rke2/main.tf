terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    local = {
      source  = "hashicorp/local"
      version = "~> 2.5"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

provider "aws" {
  region     = var.aws_region
  access_key = var.lh_aws_access_key
  secret_key = var.lh_aws_secret_key
}

resource "random_id" "suffix" {
  byte_length = 4
}

resource "random_password" "cluster_token" {
  length  = 64
  special = false
}

locals {
  name           = "${var.cluster_name}-${random_id.suffix.hex}"
  linux_ami_id   = coalesce(var.linux_ami_id, data.aws_ami.ubuntu.id)
  windows_ami_id = coalesce(var.windows_ami_id, data.aws_ami.windows_server_2022.id)

  node_pools = {
    linux-server = {
      os               = "linux"
      role             = "server"
      count            = 1
      address_start    = 10
      ami_id           = local.linux_ami_id
      instance_type    = var.controlplane_instance_type
      root_volume_size = 64
      data_volume_size = 0
      filesystem       = ""
      labels           = { "node-role.longhorn.io/control-plane" = "true" }
      taints           = ["node-role.kubernetes.io/control-plane=true:NoSchedule"]
    }
    linux-worker = {
      os               = "linux"
      role             = "agent"
      count            = var.linux_worker_count
      address_start    = 20
      ami_id           = local.linux_ami_id
      instance_type    = var.linux_worker_instance_type
      root_volume_size = 64
      data_volume_size = var.worker_data_volume_size
      data_volume_type = "gp3"
      filesystem       = "ext4"
      labels           = { "node-role.longhorn.io/worker" = "true" }
      taints           = []
    }
    windows-ntfs = {
      os               = "windows"
      role             = "agent"
      count            = var.windows_ntfs_worker_count
      address_start    = 30
      ami_id           = local.windows_ami_id
      instance_type    = var.windows_worker_instance_type
      root_volume_size = 80
      data_volume_size = var.worker_data_volume_size
      data_volume_type = "gp3"
      filesystem       = "ntfs"
      labels           = { "node-role.longhorn.io/worker" = "true" }
      taints           = []
    }
    windows-refs = {
      os               = "windows"
      role             = "agent"
      count            = var.windows_refs_worker_count
      address_start    = 40
      ami_id           = local.windows_ami_id
      instance_type    = var.windows_worker_instance_type
      root_volume_size = 80
      data_volume_size = var.worker_data_volume_size
      data_volume_type = "gp3"
      filesystem       = "refs"
      labels           = { "node-role.longhorn.io/worker" = "true" }
      taints           = []
    }
  }
}

module "network" {
  source = "../modules/test-network"

  name              = local.name
  availability_zone = var.aws_availability_zone
  admin_cidrs       = var.admin_cidrs
  ssh_public_key    = file(pathexpand(var.aws_ssh_public_key_file_path))
  tags              = { "longhorn.io/test-purpose" = "windows-engine" }
}

module "cluster" {
  source = "../modules/rke2-node-pools"

  cluster_name         = local.name
  rke2_version         = var.k8s_distro_version
  cluster_token        = random_password.cluster_token.result
  cni                  = "calico"
  availability_zone    = var.aws_availability_zone
  subnet_id            = module.network.subnet_id
  subnet_cidr          = module.network.subnet_cidr
  security_group_ids   = [module.network.security_group_id]
  key_name             = module.network.key_name
  node_pools           = local.node_pools
  csi_proxy_binary_url = var.csi_proxy_binary_url
  csi_proxy_sha256     = var.csi_proxy_sha256
  tags                 = { "longhorn.io/test-purpose" = "windows-engine" }
}

resource "local_file" "node_inventory" {
  filename = "${path.module}/node-inventory.json"
  content = jsonencode({
    schema_version = 1
    cluster_name   = local.name
    provider       = "aws"
    kubernetes     = "rke2"
    nodes          = module.cluster.nodes
  })
}

resource "terraform_data" "kubeconfig" {
  triggers_replace = [
    module.cluster.server.instance_id,
    module.cluster.node_count,
  ]

  provisioner "remote-exec" {
    inline = [
      "cloud-init status --wait",
      "until [ -f /etc/rancher/rke2/rke2.yaml ]; do sleep 5; done",
      "until [ $(sudo KUBECONFIG=/etc/rancher/rke2/rke2.yaml /var/lib/rancher/rke2/bin/kubectl get nodes --no-headers 2>/dev/null | wc -l) -eq ${module.cluster.node_count} ]; do echo waiting for all VM nodes to register; sleep 15; done",
      "sudo KUBECONFIG=/etc/rancher/rke2/rke2.yaml /var/lib/rancher/rke2/bin/kubectl wait --for=condition=Ready nodes --all --timeout=30m",
    ]

    connection {
      type        = "ssh"
      user        = "ubuntu"
      host        = module.cluster.server.public_ip
      private_key = file(pathexpand(var.aws_ssh_private_key_file_path))
    }
  }

  provisioner "local-exec" {
    command = "rsync -az --rsync-path='sudo rsync' -e 'ssh -o StrictHostKeyChecking=no -i ${pathexpand(var.aws_ssh_private_key_file_path)}' ubuntu@${module.cluster.server.public_ip}:/etc/rancher/rke2/rke2.yaml ${path.module}/rke2.yaml && sed -i 's#https://127.0.0.1:6443#https://${module.cluster.server.public_ip}:6443#' ${path.module}/rke2.yaml"
  }
}
