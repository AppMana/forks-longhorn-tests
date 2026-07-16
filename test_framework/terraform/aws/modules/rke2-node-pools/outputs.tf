output "nodes" {
  description = "Machine-readable node inventory shared with the E2E topology selector."
  value = {
    for name, instance in aws_instance.node : name => {
      instance_id = instance.id
      pool        = local.nodes[name].pool
      pool_index  = local.nodes[name].pool_index
      os          = local.nodes[name].os
      role        = local.nodes[name].role
      filesystem  = local.nodes[name].filesystem
      private_ip  = instance.private_ip
      public_ip   = instance.public_ip
      labels      = local.node_labels[name]
      taints      = local.nodes[name].taints
    }
  }
}

output "server" {
  value = one([
    for name, instance in aws_instance.node : {
      name        = name
      instance_id = instance.id
      private_ip  = instance.private_ip
      public_ip   = instance.public_ip
    } if local.nodes[name].role == "server"
  ])
}

output "node_count" {
  value = length(local.nodes)
}
