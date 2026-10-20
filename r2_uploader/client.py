"""Boto3 S3 client creation for Cloudflare R2."""

import boto3
from botocore.client import Config
from .config import R2Config


def get_r2_client(config: R2Config):
    """Create a configured boto3 S3 client for Cloudflare R2."""
    session = boto3.session.Session()
    client = session.client(
        service_name="s3",
        endpoint_url=config.endpoint_url,
        aws_access_key_id=config.access_key_id,
        aws_secret_access_key=config.secret_access_key,
        region_name="auto",
        config=Config(
            signature_version="s3v4",
            retries={"max_attempts": 5, "mode": "standard"},
            s3={"addressing_style": "path"},
        ),
    )
    return client
