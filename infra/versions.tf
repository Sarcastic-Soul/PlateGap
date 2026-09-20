terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project   = "plategap"
      ManagedBy = "terraform"
    }
  }
}

# CloudFront reads its certificate and a few other resources only from
# us-east-1, whatever region everything else lives in.
provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"

  default_tags {
    tags = {
      Project   = "plategap"
      ManagedBy = "terraform"
    }
  }
}
