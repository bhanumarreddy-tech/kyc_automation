"""RDS IAM token helper."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.db.rds_iam import generate_rds_auth_token


def test_generate_rds_auth_token_delegates_to_boto3() -> None:
    mock_client = MagicMock()
    mock_client.generate_db_auth_token.return_value = "host:5432/?Action=connect&DBUser=postgres"

    with patch("boto3.client", return_value=mock_client) as mock_boto_client:
        token = generate_rds_auth_token(
            host="db.example.com",
            port=5432,
            user="postgres",
            region="us-east-1",
        )

    mock_boto_client.assert_called_once_with("rds", region_name="us-east-1")
    mock_client.generate_db_auth_token.assert_called_once_with(
        DBHostname="db.example.com",
        Port=5432,
        DBUsername="postgres",
    )
    assert token.startswith("host:5432/")
