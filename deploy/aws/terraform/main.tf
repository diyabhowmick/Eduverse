# EduVerse on AWS, one environment per state: a VPC, one EC2 box running Docker Compose (Caddy for HTTPS,
# the API, a worker, Redis), RDS PostgreSQL, a private S3 bucket for books and voice notes, ECR for images,
# Secrets Manager for every secret. No SSH: the box is reached through SSM Session Manager.
locals {
  name = "eduverse-${var.env}"
  prod = var.env == "production"
}

data "aws_availability_zones" "az" { state = "available" }
data "aws_caller_identity" "me" {}
data "aws_ami" "al2023" {
  most_recent = true
  owners      = ["amazon"]
  filter {
    name   = "name"
    values = ["al2023-ami-2023.*-x86_64"]
  }
}

# ---------------- network ----------------
resource "aws_vpc" "main" {
  cidr_block           = "10.40.0.0/16"
  enable_dns_hostnames = true
  tags                 = { Name = local.name }
}
resource "aws_internet_gateway" "gw" { vpc_id = aws_vpc.main.id }
resource "aws_subnet" "public" {
  count                   = 2
  vpc_id                  = aws_vpc.main.id
  cidr_block              = cidrsubnet(aws_vpc.main.cidr_block, 8, count.index)
  availability_zone       = data.aws_availability_zones.az.names[count.index]
  map_public_ip_on_launch = true
  tags                    = { Name = "${local.name}-public-${count.index}" }
}
resource "aws_subnet" "private" { # the database only; it never talks to the internet
  count             = 2
  vpc_id            = aws_vpc.main.id
  cidr_block        = cidrsubnet(aws_vpc.main.cidr_block, 8, 10 + count.index)
  availability_zone = data.aws_availability_zones.az.names[count.index]
  tags              = { Name = "${local.name}-private-${count.index}" }
}
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.gw.id
  }
}
resource "aws_route_table_association" "public" {
  count          = 2
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

resource "aws_security_group" "app" {
  name        = "${local.name}-app"
  description = "Web traffic in, everything out. No SSH: use SSM."
  vpc_id      = aws_vpc.main.id
  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}
resource "aws_security_group" "db" {
  name        = "${local.name}-db"
  description = "PostgreSQL from the app server only"
  vpc_id      = aws_vpc.main.id
  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.app.id]
  }
}

# ---------------- secrets ----------------
resource "random_password" "jwt" {
  length  = 64
  special = false
}
resource "random_password" "settings" {
  length  = 48
  special = false
}
resource "random_password" "db" {
  length  = 32
  special = false
}
resource "random_password" "admin" {
  length  = 20
  special = true
}
resource "aws_secretsmanager_secret" "app" {
  name                    = "${local.name}/app"
  recovery_window_in_days = local.prod ? 30 : 0
}
resource "aws_secretsmanager_secret_version" "app" {
  secret_id = aws_secretsmanager_secret.app.id
  secret_string = jsonencode({
    JWT_SECRET          = random_password.jwt.result
    SETTINGS_KEY        = random_password.settings.result
    DB_PASSWORD         = random_password.db.result
    SUPERADMIN_PASSWORD = random_password.admin.result
    OPENAI_API_KEY      = ""
  })
  lifecycle { ignore_changes = [secret_string] } # you add keys (OPENAI_API_KEY) in the console; Terraform leaves them alone
}

# ---------------- database ----------------
resource "aws_db_subnet_group" "db" {
  name       = local.name
  subnet_ids = aws_subnet.private[*].id
}
resource "aws_db_parameter_group" "pg" {
  name   = local.name
  family = "postgres16"
  parameter {
    name  = "rds.force_ssl"
    value = "1"
  }
}
resource "aws_db_instance" "db" {
  identifier                   = local.name
  engine                       = "postgres"
  engine_version               = "16"
  instance_class               = var.db_instance_class
  allocated_storage            = var.db_storage_gb
  max_allocated_storage        = var.db_storage_gb * 5
  storage_type                 = "gp3"
  storage_encrypted            = true
  db_name                      = "eduverse"
  username                     = "eduverse"
  password                     = random_password.db.result
  db_subnet_group_name         = aws_db_subnet_group.db.name
  vpc_security_group_ids       = [aws_security_group.db.id]
  parameter_group_name         = aws_db_parameter_group.pg.name
  multi_az                     = false # single AZ, as on AnAi; switch on when paying clients need it
  publicly_accessible          = false
  backup_retention_period      = var.db_backup_days # daily snapshots + point-in-time restore
  backup_window                = "20:30-21:30"      # 2:00 to 3:00 am India time
  maintenance_window           = "sun:21:30-sun:22:30"
  auto_minor_version_upgrade   = true
  deletion_protection          = local.prod
  skip_final_snapshot          = !local.prod
  final_snapshot_identifier    = local.prod ? "${local.name}-final" : null
  copy_tags_to_snapshot        = true
  performance_insights_enabled = false
}

# ---------------- files ----------------
resource "aws_s3_bucket" "files" {
  bucket        = "${local.name}-files-${data.aws_caller_identity.me.account_id}"
  force_destroy = !local.prod
}
resource "aws_s3_bucket_public_access_block" "files" {
  bucket                  = aws_s3_bucket.files.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
resource "aws_s3_bucket_ownership_controls" "files" {
  bucket = aws_s3_bucket.files.id
  rule { object_ownership = "BucketOwnerEnforced" }
}
resource "aws_s3_bucket_server_side_encryption_configuration" "files" {
  bucket = aws_s3_bucket.files.id
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "AES256" }
  }
}
resource "aws_s3_bucket_versioning" "files" { # a deleted or overwritten book can be brought back
  bucket = aws_s3_bucket.files.id
  versioning_configuration { status = "Enabled" }
}
resource "aws_s3_bucket_lifecycle_configuration" "files" {
  bucket = aws_s3_bucket.files.id
  rule {
    id     = "old-versions"
    status = "Enabled"
    filter {}
    noncurrent_version_expiration { noncurrent_days = 30 }
    abort_incomplete_multipart_upload { days_after_initiation = 2 }
  }
}

# ---------------- images ----------------
resource "aws_ecr_repository" "app" {
  name                 = local.name
  image_tag_mutability = "MUTABLE"
  force_delete         = !local.prod
  image_scanning_configuration { scan_on_push = true }
}
resource "aws_ecr_lifecycle_policy" "app" {
  repository = aws_ecr_repository.app.name
  policy = jsonencode({ rules = [{ rulePriority = 1, description = "keep the last 15 images",
    selection = { tagStatus = "any", countType = "imageCountMoreThan", countNumber = 15 }, action = { type = "expire" } }] })
}

# ---------------- logs ----------------
resource "aws_cloudwatch_log_group" "app" {
  name              = "/eduverse/${var.env}"
  retention_in_days = local.prod ? 90 : 14
}

# ---------------- the server's permissions: exactly what it uses ----------------
resource "aws_iam_role" "app" {
  name = "${local.name}-app"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Action = "sts:AssumeRole",
    Principal = { Service = "ec2.amazonaws.com" } }] })
}
resource "aws_iam_role_policy_attachment" "ssm" {
  role       = aws_iam_role.app.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}
resource "aws_iam_role_policy" "app" {
  name = "${local.name}-app"
  role = aws_iam_role.app.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"], Resource = "${aws_s3_bucket.files.arn}/*" },
    { Effect = "Allow", Action = ["s3:ListBucket"], Resource = aws_s3_bucket.files.arn },
    { Effect = "Allow", Action = ["secretsmanager:GetSecretValue"], Resource = aws_secretsmanager_secret.app.arn },
    { Effect = "Allow", Action = ["ecr:GetAuthorizationToken"], Resource = "*" },
    { Effect = "Allow", Action = ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer", "ecr:BatchCheckLayerAvailability"], Resource = aws_ecr_repository.app.arn },
    { Effect = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents", "logs:DescribeLogStreams"], Resource = "${aws_cloudwatch_log_group.app.arn}:*" },
  ] })
}
resource "aws_iam_instance_profile" "app" {
  name = "${local.name}-app"
  role = aws_iam_role.app.name
}

# ---------------- the server ----------------
resource "aws_instance" "app" {
  ami                         = data.aws_ami.al2023.id
  instance_type               = var.instance_type
  subnet_id                   = aws_subnet.public[0].id
  vpc_security_group_ids      = [aws_security_group.app.id]
  iam_instance_profile        = aws_iam_instance_profile.app.name
  associate_public_ip_address = true
  metadata_options {
    http_tokens                 = "required" # IMDSv2 only
    http_put_response_hop_limit = 2          # containers can read the instance role
  }
  root_block_device {
    volume_size = var.root_volume_gb
    volume_type = "gp3"
    encrypted   = true
  }
  user_data = templatefile("${path.module}/user_data.sh.tpl", {
    region     = var.region
    env        = var.env
    domain     = var.domain
    acme_email = var.acme_email
    image      = "${aws_ecr_repository.app.repository_url}:latest"
    registry   = split("/", aws_ecr_repository.app.repository_url)[0]
    secret_id  = aws_secretsmanager_secret.app.name
    db_host    = aws_db_instance.db.address
    bucket     = aws_s3_bucket.files.bucket
    log_group  = aws_cloudwatch_log_group.app.name
    admin      = var.superadmin_email
    compose_b64 = filebase64("${path.module}/../docker-compose.aws.yml")
    caddy_b64   = filebase64("${path.module}/../Caddyfile")
    deploy_b64  = filebase64("${path.module}/../server-deploy.sh")
  })
  user_data_replace_on_change = false
  lifecycle { ignore_changes = [ami, user_data] } # a new AMI or start script never rebuilds the running server by surprise
  tags = { Name = local.name }
}
resource "aws_eip" "app" {
  instance = aws_instance.app.id
  domain   = "vpc"
}
resource "aws_route53_record" "app" {
  count   = var.route53_zone_id == "" ? 0 : 1
  zone_id = var.route53_zone_id
  name    = var.domain
  type    = "A"
  ttl     = 300
  records = [aws_eip.app.public_ip]
}

# ---------------- alarms: recover a broken server, tell someone ----------------
resource "aws_sns_topic" "alarms" { name = "${local.name}-alarms" }
resource "aws_sns_topic_subscription" "email" {
  count     = var.alarm_email == "" ? 0 : 1
  topic_arn = aws_sns_topic.alarms.arn
  protocol  = "email"
  endpoint  = var.alarm_email
}
resource "aws_cloudwatch_metric_alarm" "recover" {
  alarm_name          = "${local.name}-recover"
  namespace           = "AWS/EC2"
  metric_name         = "StatusCheckFailed_System"
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 2
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  dimensions          = { InstanceId = aws_instance.app.id }
  alarm_actions       = ["arn:aws:automate:${var.region}:ec2:recover", aws_sns_topic.alarms.arn]
}
resource "aws_cloudwatch_metric_alarm" "cpu" {
  alarm_name          = "${local.name}-cpu-high"
  namespace           = "AWS/EC2"
  metric_name         = "CPUUtilization"
  statistic           = "Average"
  period              = 300
  evaluation_periods  = 6
  threshold           = 85
  comparison_operator = "GreaterThanThreshold"
  dimensions          = { InstanceId = aws_instance.app.id }
  alarm_actions       = [aws_sns_topic.alarms.arn]
}
resource "aws_cloudwatch_metric_alarm" "db_storage" {
  alarm_name          = "${local.name}-db-storage-low"
  namespace           = "AWS/RDS"
  metric_name         = "FreeStorageSpace"
  statistic           = "Minimum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 2147483648 # 2 GB
  comparison_operator = "LessThanThreshold"
  dimensions          = { DBInstanceIdentifier = aws_db_instance.db.identifier }
  alarm_actions       = [aws_sns_topic.alarms.arn]
}
