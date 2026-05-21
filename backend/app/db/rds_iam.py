"""AWS RDS IAM authentication tokens for PostgreSQL (asyncpg password)."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# IAM tokens expire in 15 minutes; recycle pooled connections before that.
RDS_IAM_POOL_RECYCLE_SECONDS = 540


def generate_rds_auth_token(
    *,
    host: str,
    port: int,
    user: str,
    region: str,
) -> str:
    """Return a signed IAM auth token to use as the Postgres password.

    Requires AWS credentials in the environment (``aws configure``, env vars, or
    Vercel OIDC-injected keys when ``AWS_ROLE_ARN`` is linked).
    """
    import boto3

    client = boto3.client("rds", region_name=region)
    token = client.generate_db_auth_token(
        DBHostname=host,
        Port=port,
        DBUsername=user,
    )
    logger.debug("Generated RDS IAM auth token for %s@%s:%s", user, host, port)
    return token
