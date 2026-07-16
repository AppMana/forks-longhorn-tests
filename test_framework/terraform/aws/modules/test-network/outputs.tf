output "vpc_id" {
  value = aws_vpc.this.id
}

output "vpc_cidr" {
  value = aws_vpc.this.cidr_block
}

output "subnet_id" {
  value = aws_subnet.this.id
}

output "subnet_cidr" {
  value = aws_subnet.this.cidr_block
}

output "security_group_id" {
  value = aws_security_group.nodes.id
}

output "key_name" {
  value = aws_key_pair.this.key_name
}
