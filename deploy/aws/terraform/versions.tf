terraform {
  required_version = ">= 1.6"
  required_providers {
    aws    = { source = "hashicorp/aws", version = "~> 5.60" }
    random = { source = "hashicorp/random", version = "~> 3.6" }
  }
  # State in S3. bootstrap.ps1 creates the bucket and runs init; staging and production are Terraform
  # workspaces, so each keeps its own state under the same key.
  backend "s3" {}
}

provider "aws" {
  region = var.region
  default_tags { tags = { Project = "eduverse", Environment = var.env, ManagedBy = "terraform" } }
}
