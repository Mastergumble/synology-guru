"""Synology DSM API client."""

from typing import Any

import httpx


class SynologyAPIError(Exception):
    """Exception raised for Synology API errors."""

    def __init__(self, code: int, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"Synology API Error {code}: {message}")


class SynologyClient:
    """Client for Synology DSM Web API."""

    # Common API error codes
    ERROR_CODES = {
        100: "Unknown error",
        101: "No parameter of API, method or version",
        102: "Requested API does not exist",
        103: "Requested method does not exist",
        104: "Requested version does not support this functionality",
        105: "Session not logged in",
        106: "Session timeout",
        107: "Session interrupted by duplicate login",
        400: "Invalid username or password",
        401: "Account disabled",
        402: "Permission denied",
        403: "2FA required",
        404: "2FA failed",
    }

    def __init__(
        self,
        host: str,
        port: int = 5001,
        https: bool = True,
        username: str = "",
        password: str = "",
        timeout: float = 30.0,
    ) -> None:
        """Initialize Synology client."""
        self.host = host
        self.port = port
        self.https = https
        self.username = username
        self.password = password
        self.timeout = timeout

        self._sid: str | None = None
        self._client: httpx.AsyncClient | None = None

    @property
    def base_url(self) -> str:
        """Get base URL for API requests."""
        protocol = "https" if self.https else "http"
        return f"{protocol}://{self.host}:{self.port}"

    async def connect(self) -> None:
        """Connect and authenticate with the Synology NAS."""
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            verify=False,  # Many Synology use self-signed certs
        )

        # Authenticate
        response = await self.request(
            api="SYNO.API.Auth",
            method="login",
            version=3,
            params={
                "account": self.username,
                "passwd": self.password,
                "session": "SynologyGuru",
                "format": "sid",
            },
            require_auth=False,
        )

        self._sid = response.get("sid")
        if not self._sid:
            raise SynologyAPIError(400, "Failed to obtain session ID")

    async def disconnect(self) -> None:
        """Disconnect and logout from the Synology NAS."""
        if self._sid:
            try:
                await self.request(
                    api="SYNO.API.Auth",
                    method="logout",
                    version=1,
                    params={"session": "SynologyGuru"},
                )
            except Exception:
                pass  # Ignore logout errors
            self._sid = None

        if self._client:
            await self._client.aclose()
            self._client = None

    async def request(
        self,
        api: str,
        method: str,
        version: int = 1,
        params: dict[str, Any] | None = None,
        require_auth: bool = True,
    ) -> dict[str, Any]:
        """Make an API request to Synology DSM."""
        if self._client is None:
            raise SynologyAPIError(0, "Client not connected")

        if require_auth and not self._sid:
            raise SynologyAPIError(105, "Not logged in")

        request_params = {
            "api": api,
            "method": method,
            "version": version,
            **(params or {}),
        }

        if require_auth and self._sid:
            request_params["_sid"] = self._sid

        response = await self._client.get(
            "/webapi/entry.cgi",
            params=request_params,
        )
        response.raise_for_status()

        data = response.json()

        if not data.get("success"):
            error = data.get("error", {})
            code = error.get("code", 100)
            message = self.ERROR_CODES.get(code, f"Unknown error: {code}")
            raise SynologyAPIError(code, message)

        return data.get("data", {})

    # ========== Storage APIs ==========

    async def get_storage_info(self) -> dict[str, Any]:
        """Get storage/volume information."""
        return await self.request(
            api="SYNO.Storage.CGI.Storage",
            method="load_info",
            version=1,
        )

    async def get_volume_info(self) -> dict[str, Any]:
        """Get volume usage information."""
        return await self.request(
            api="SYNO.Core.System",
            method="info",
            version=1,
            params={"type": "storage"},
        )

    # ========== Disk APIs ==========

    async def get_disk_info(self) -> dict[str, Any]:
        """Get disk information including S.M.A.R.T. data."""
        return await self.request(
            api="SYNO.Storage.CGI.Storage",
            method="load_info",
            version=1,
        )

    # ========== System APIs ==========

    async def get_system_info(self) -> dict[str, Any]:
        """Get system information."""
        return await self.request(
            api="SYNO.Core.System",
            method="info",
            version=1,
        )

    async def get_dsm_info(self) -> dict[str, Any]:
        """Get DSM version information."""
        return await self.request(
            api="SYNO.DSM.Info",
            method="getinfo",
            version=2,
        )

    # ========== Update APIs ==========

    async def check_updates(self) -> dict[str, Any]:
        """Check for DSM updates."""
        return await self.request(
            api="SYNO.Core.Upgrade.Server",
            method="check",
            version=1,
        )

    # ========== Backup APIs ==========

    async def get_hyper_backup_info(self) -> dict[str, Any]:
        """Get Hyper Backup task information."""
        return await self.request(
            api="SYNO.Backup.Task",
            method="list",
            version=1,
        )

    # ========== Security APIs ==========

    async def get_security_scan(self) -> dict[str, Any]:
        """Get security advisor scan results."""
        return await self.request(
            api="SYNO.Core.SecurityScan.Status",
            method="get",
            version=1,
        )

    async def get_connection_logs(self, limit: int = 100) -> dict[str, Any]:
        """Get connection/login logs."""
        return await self.request(
            api="SYNO.Core.SyslogClient.Log",
            method="list",
            version=1,
            params={"limit": limit},
        )

    # ========== Log APIs ==========

    async def get_system_logs(self, limit: int = 100) -> dict[str, Any]:
        """Get system logs."""
        return await self.request(
            api="SYNO.Core.SyslogClient.Log",
            method="list",
            version=1,
            params={"limit": limit, "filter": {"log_type": "system"}},
        )
