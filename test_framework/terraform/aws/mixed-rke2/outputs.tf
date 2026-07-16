output "controlplane_public_ip" {
  value = module.cluster.server.public_ip
}

output "instance_mapping" {
  value = jsonencode([
    for name, node in module.cluster.nodes : {
      name = name
      id   = node.instance_id
    }
  ])
}

output "public_ip_mapping" {
  value = jsonencode([
    for name, node in module.cluster.nodes : {
      name = name
      ip   = node.public_ip
    }
  ])
}

output "node_inventory" {
  value = local_file.node_inventory.content
}

output "resource_suffix" {
  value = random_id.suffix.hex
}
