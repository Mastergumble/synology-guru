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

    # ========== Package APIs ==========

    async def get_installed_packages(self) -> dict[str, Any]:
        """Get list of installed packages."""
        return await self.request(
            api="SYNO.Core.Package",
            method="list",
            version=1,
        )

    async def get_available_packages(self) -> dict[str, Any]:
        """Get list of available packages from server."""
        return await self.request(
            api="SYNO.Core.Package.Server",
            method="list",
            version=2,
            params={"blforcereload": True},
        )

    async def get_package_updates(self) -> list[dict[str, Any]]:
        """Get list of packages with available updates."""
        installed = await self.get_installed_packages()
        available = await self.get_available_packages()

        installed_map = {p["id"]: p for p in installed.get("packages", [])}
        updates = []

        for pkg in available.get("packages", []):
            pkg_id = pkg.get("id")
            if pkg_id in installed_map:
                installed_ver = installed_map[pkg_id].get("version", "")
                server_ver = pkg.get("version", "")
                if server_ver != installed_ver:
                    updates.append({
                        "id": pkg_id,
                        "name": pkg.get("name") or pkg.get("dname") or pkg_id,
                        "installed_version": installed_ver,
                        "available_version": server_ver,
                    })

        return updates

    async def upgrade_package(self, package_id: str) -> dict[str, Any]:
        """Upgrade a specific package to the latest version.

        This method downloads the SPK file from Synology's server and uploads
        it to the NAS for installation.
        """
        import httpx

        # Get package info from server to find download URL
        available = await self.get_available_packages()
        pkg_info = None
        for pkg in available.get("packages", []):
            if pkg.get("id") == package_id:
                pkg_info = pkg
                break

        if not pkg_info:
            raise SynologyAPIError(0, f"Package {package_id} not found on server")

        spk_url = pkg_info.get("link")
        if not spk_url:
            raise SynologyAPIError(0, f"No download URL for package {package_id}")

        # Download SPK file
        async with httpx.AsyncClient(verify=False, timeout=300.0, follow_redirects=True) as http:
            response = await http.get(spk_url)
            spk_data = response.content

        if len(spk_data) < 100000:
            raise SynologyAPIError(0, f"Download failed for {package_id}")

        # Upload SPK to NAS
        if self._client is None:
            raise SynologyAPIError(0, "Client not connected")

        files = {
            'file': (f'{package_id}.spk', spk_data, 'application/octet-stream'),
        }
        data = {
            'api': 'SYNO.Core.Package.Installation',
            'method': 'upload',
            'version': '1',
        }
        if self._sid:
            data['_sid'] = self._sid

        response = await self._client.post(
            "/webapi/entry.cgi",
            files=files,
            data=data,
        )
        result = response.json()

        if not result.get("success"):
            error = result.get("error", {})
            raise SynologyAPIError(error.get("code", 0), f"Upload failed: {error}")

        task_id = result.get("data", {}).get("task_id")

        # Install the uploaded package
        install_result = await self.request(
            api="SYNO.Core.Package.Installation",
            method="install",
            version=1,
            params={"task_id": task_id},
        )

        return {
            "package_id": package_id,
            "name": pkg_info.get("name", package_id),
            "version": pkg_info.get("version"),
            "task_id": task_id,
            "install_result": install_result,
        }

    async def upgrade_all_packages(self) -> list[dict[str, Any]]:
        """Upgrade all packages with available updates."""
        updates = await self.get_package_updates()
        results = []
        for pkg in updates:
            try:
                result = await self.upgrade_package(pkg["id"])
                results.append({
                    "id": pkg["id"],
                    "name": pkg["name"],
                    "success": True,
                    "result": result,
                })
            except Exception as e:
                results.append({
                    "id": pkg["id"],
                    "name": pkg["name"],
                    "success": False,
                    "error": str(e),
                })
        return results
