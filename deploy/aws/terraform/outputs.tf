output "server_ip" { value = aws_eip.app.public_ip }
output "instance_id" { value = aws_instance.app.id }
output "ecr_repository" { value = aws_ecr_repository.app.repository_url }
output "bucket" { value = aws_s3_bucket.files.bucket }
output "db_address" { value = aws_db_instance.db.address }
output "secret_name" { value = aws_secretsmanager_secret.app.name }
output "url" { value = "https://${var.domain}" }
output "dns_to_add" {
  value = var.route53_zone_id == "" ? "Add an A record: ${var.domain} -> ${aws_eip.app.public_ip}" : "Route 53 record created"
}
