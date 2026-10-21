"""Configuration loader for Cloudflare R2 credentials and settings."""

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse
from dotenv import load_dotenv


@dataclass
class R2Config:
    endpoint_url: str
    access_key_id: str
    secret_access_key: str
    bucket_name: str

    @classmethod
    def load(cls, env_path: Path | str | None = None) -> "R2Config":
        """Load and validate configuration from .env or system environment."""
        if env_path:
            load_dotenv(dotenv_path=env_path)
        else:
            # Hierarchical search for .env:
            # 1. Current working directory .env (if present)
            # 2. ~/.config/r2up/.env or ~/.r2up.env
            # 3. Legacy ~/.config/r2-uploader/.env or ~/.r2.env
            # 4. Project directory where package is installed
            potential_paths = [
                Path.cwd() / ".env",
                Path.home() / ".config" / "r2up" / ".env",
                Path.home() / ".r2up.env",
                Path.home() / ".config" / "r2-uploader" / ".env",
                Path.home() / ".r2.env",
                Path(__file__).resolve().parent.parent / ".env",
            ]
            for candidate in potential_paths:
                if candidate.is_file():
                    load_dotenv(dotenv_path=candidate)
                    # If this file supplied credentials, we can stop searching
                    if os.getenv("R2_ACCESS_KEY_ID"):
                        break


        raw_endpoint = os.getenv("R2_ENDPOINT_URL", "").strip().strip("'\"")
        access_key_id = os.getenv("R2_ACCESS_KEY_ID", "").strip().strip("'\"")
        secret_access_key = os.getenv("R2_SECRET_ACCESS_KEY", "").strip().strip("'\"")
        bucket_name = os.getenv("R2_BUCKET_NAME", "").strip().strip("'\"")

        # Normalize endpoint URL:
        # Cloudflare R2 endpoints are of form https://<ACCOUNT_ID>.r2.cloudflarestorage.com
        # Strip any bucket name or path trailing in the endpoint URL if present
        if raw_endpoint:
            parsed = urlparse(raw_endpoint)
            scheme = parsed.scheme or "https"
            netloc = parsed.netloc or parsed.path.split("/")[0]
            clean_endpoint = f"{scheme}://{netloc}"

            # If bucket_name is empty but path had a bucket name, extract it
            if not bucket_name and parsed.path.strip("/"):
                bucket_name = parsed.path.strip("/").split("/")[0]
        else:
            clean_endpoint = ""

        missing = []
        if not clean_endpoint:
            missing.append("R2_ENDPOINT_URL")
        if not access_key_id:
            missing.append("R2_ACCESS_KEY_ID")
        if not secret_access_key:
            missing.append("R2_SECRET_ACCESS_KEY")
        if not bucket_name:
            missing.append("R2_BUCKET_NAME")

        if missing:
            raise ValueError(
                f"Missing required environment variables: {', '.join(missing)}\n\n"
                f"Please provide them via system environment variables, a local '.env', "
                f"or in '~/.config/r2up/.env' (or '~/.r2up.env').\n\n"
                f"Quick setup:\n"
                f"  mkdir -p ~/.config/r2up\n"
                f"  cat << 'EOF' > ~/.config/r2up/.env\n"
                f'  R2_ENDPOINT_URL="https://<ACCOUNT_ID>.r2.cloudflarestorage.com"\n'
                f'  R2_ACCESS_KEY_ID="your_access_key_id"\n'
                f'  R2_SECRET_ACCESS_KEY="your_secret_access_key"\n'
                f'  R2_BUCKET_NAME="your_bucket_name"\n'
                f"  EOF"
            )

        return cls(
            endpoint_url=clean_endpoint,
            access_key_id=access_key_id,
            secret_access_key=secret_access_key,
            bucket_name=bucket_name,
        )
