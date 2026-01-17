"""GitHub API service with GitHub App authentication."""

import logging
import time
from datetime import datetime, timedelta
from typing import Any, Optional

import httpx
import jwt

logger = logging.getLogger(__name__)


class GitHubService:
    """GitHub API interactions using GitHub App authentication."""

    GITHUB_API_BASE = "https://api.github.com"

    def __init__(self, app_id: str, private_key: str, installation_id: str):
        """
        Initialize GitHub service with App credentials.

        Args:
            app_id: GitHub App ID.
            private_key: PEM-formatted private key.
            installation_id: Installation ID for the repository.
        """
        self.app_id = app_id
        self.private_key = private_key
        self.installation_id = installation_id
        self._token_cache: Optional[tuple[str, datetime]] = None
        logger.debug("GitHubService initialized for app_id=%s, installation_id=%s", app_id, installation_id)

    def _generate_jwt(self) -> str:
        """
        Generate JWT for GitHub App authentication.

        Returns:
            Signed JWT token.

        Raises:
            Exception: If JWT generation fails.
        """
        # JWT expires in 10 minutes (GitHub's max is 10 minutes)
        now = int(time.time())
        expiry = now + (10 * 60)  # 10 minutes

        payload = {
            "iat": now,  # Issued at
            "exp": expiry,  # Expiry
            "iss": self.app_id,  # Issuer (App ID)
        }

        try:
            # Sign with RS256 algorithm using private key
            token = jwt.encode(payload, self.private_key, algorithm="RS256")
            logger.debug("Generated GitHub App JWT (expires in 10 minutes)")
            return token
        except Exception as e:
            logger.error("Failed to generate JWT: %s", e)
            raise

    async def _get_installation_token(self) -> str:
        """
        Get installation access token (cached for 1 hour).

        Returns:
            Installation access token.

        Raises:
            Exception: If token fetch fails.
        """
        # Check cache
        if self._token_cache:
            token, expiry = self._token_cache
            if datetime.now() < expiry:
                logger.debug("Using cached installation token")
                return token

        logger.debug("Fetching new installation access token...")

        # Generate JWT for authentication
        jwt_token = self._generate_jwt()

        # Exchange JWT for installation token
        url = f"{self.GITHUB_API_BASE}/app/installations/{self.installation_id}/access_tokens"
        headers = {
            "Authorization": f"Bearer {jwt_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(url, headers=headers)
                response.raise_for_status()
                data = response.json()

                token = data["token"]
                # Cache for 50 minutes (tokens expire in 1 hour, refresh early)
                expiry = datetime.now() + timedelta(minutes=50)
                self._token_cache = (token, expiry)

                logger.info("Fetched new installation access token (valid for 50 minutes)")
                return token

            except httpx.HTTPStatusError as e:
                logger.error("Failed to fetch installation token (HTTP %d): %s", e.response.status_code, e.response.text)
                raise
            except Exception as e:
                logger.error("Failed to fetch installation token: %s", e)
                raise

    async def create_pull_request(
        self,
        repo: str,
        title: str,
        body: str,
        head_branch: str,
        base_branch: str = "main",
    ) -> dict[str, Any]:
        """
        Create a pull request.

        Args:
            repo: Repository name in format "owner/repo".
            title: PR title.
            body: PR description (markdown supported).
            head_branch: Branch containing changes.
            base_branch: Target branch (default: main).

        Returns:
            PR data dict containing html_url, number, etc.

        Raises:
            Exception: If PR creation fails.
        """
        logger.info("Creating pull request: %s -> %s in %s", head_branch, base_branch, repo)

        token = await self._get_installation_token()
        url = f"{self.GITHUB_API_BASE}/repos/{repo}/pulls"
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        payload = {
            "title": title,
            "body": body,
            "head": head_branch,
            "base": base_branch,
        }

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                pr_data = response.json()

                logger.info("Created PR #%d: %s", pr_data["number"], pr_data["html_url"])
                return pr_data

            except httpx.HTTPStatusError as e:
                logger.error("Failed to create PR (HTTP %d): %s", e.response.status_code, e.response.text)
                raise
            except Exception as e:
                logger.error("Failed to create PR: %s", e)
                raise

    async def get_pull_request(self, repo: str, pr_number: int) -> dict[str, Any]:
        """
        Get pull request details.

        Args:
            repo: Repository name in format "owner/repo".
            pr_number: PR number.

        Returns:
            PR data dict.

        Raises:
            Exception: If fetch fails.
        """
        logger.debug("Fetching PR #%d from %s...", pr_number, repo)

        token = await self._get_installation_token()
        url = f"{self.GITHUB_API_BASE}/repos/{repo}/pulls/{pr_number}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                return response.json()

            except httpx.HTTPStatusError as e:
                logger.error("Failed to fetch PR (HTTP %d): %s", e.response.status_code, e.response.text)
                raise
            except Exception as e:
                logger.error("Failed to fetch PR: %s", e)
                raise

    async def list_repository_contents(
        self, repo: str, path: str = "", ref: str = "main"
    ) -> list[dict[str, Any]]:
        """
        List repository contents at a given path.

        Args:
            repo: Repository name in format "owner/repo".
            path: Path within repository (empty for root).
            ref: Git ref (branch, tag, or commit SHA).

        Returns:
            List of file/directory metadata dicts.

        Raises:
            Exception: If fetch fails.
        """
        logger.debug("Listing repository contents: %s/%s (ref=%s)", repo, path, ref)

        token = await self._get_installation_token()
        url = f"{self.GITHUB_API_BASE}/repos/{repo}/contents/{path}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        params = {"ref": ref}

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(url, headers=headers, params=params)
                response.raise_for_status()
                return response.json()

            except httpx.HTTPStatusError as e:
                logger.error("Failed to list contents (HTTP %d): %s", e.response.status_code, e.response.text)
                raise
            except Exception as e:
                logger.error("Failed to list contents: %s", e)
                raise
