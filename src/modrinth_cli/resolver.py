from concurrent.futures import ThreadPoolExecutor
import os

import requests
from dataclasses import dataclass

from .exceptions import DependencyConflictError, DependencyNotFoundError

# We must provide a unique User-Agent header
HEADERS = {
    "User-Agent": "Modrinth CLI v0.1.0 (Unoffical) / me.amiralimollaei@gmail.com"
}


@dataclass(frozen=True)
class ResolvedVersion:
    version_id: str
    project_id: str
    project_type: str
    file_url: str
    filename: str


class ModrinthResolver:
    base_url = "https://api.modrinth.com/v2/"

    def __init__(self, verbose: bool = True):
        self.verbose = verbose

        # re-use connection
        self.session = requests.Session()
        # Cache to prevent redundant API calls
        self.project_cache: dict[str, dict] = {}
        self.version_cache: dict[str, list[dict]] = {}

    def get(self, url: str, **params):
        if self.verbose:
            print(f"GET {url} ({params=}) ... ", end="")
        response = self.session.get(self.base_url + url, params=params)
        if self.verbose:
            print(response.status_code)
        response.raise_for_status()
        return response.json()

    def _get_project(self, identifier: str) -> dict:
        if identifier not in self.project_cache:
            self.project_cache[identifier] = self.get(f"project/{identifier}")
        return self.project_cache[identifier]

    def _get_versions(self, identifier: str) -> list[dict]:
        if identifier not in self.version_cache:
            self.version_cache[identifier] = self.get(f"project/{identifier}/version")
        return self.version_cache[identifier]

    def _find_best_version(self, project_id: str, game_version: str, loader: str) -> dict:
        """Finds the latest version that matches the game version and loader."""
        project = self._get_project(project_id)
        project_slug: str = project["slug"].lower()
        project_type: str = project["project_type"].lower()

        versions = self._get_versions(project_id)

        # Filter versions by game version and loader
        compatible_versions = []
        for version in versions:
            if game_version not in version.get("game_versions", []):
                continue
            # Only check loader for mods and plugins
            if project_type in ["mod", "plugin"] and loader not in version.get("loaders", []):
                continue
            compatible_versions.append(version)

        if not compatible_versions:
            raise DependencyNotFoundError(f"No compatible version found for project {project_slug} "
                                  f"(Game: {game_version}, Loader: {loader})")

        # Sort by date_published descending to get the newest one
        compatible_versions.sort(key=lambda x: x["date_published"], reverse=True)
        return compatible_versions[0]

    def resolve(self, target_slugs: list[str], game_version: str, loader: str) -> list[ResolvedVersion]:
        """
        Resolves a list of target project slugs into a flat list of specific versions.
        """
        # The "Queue" for BFS
        to_resolve = []
        for slug in target_slugs:
            project = self._get_project(slug)
            to_resolve.append(project["id"])

        resolved_map: dict[str, dict] = {}  # project_id -> version_object
        forbidden_projects: set[str] = set()  # Set of project_ids that are 'incompatible'

        # We use a list as a queue for BFS
        idx = 0
        while idx < len(to_resolve):
            current_project_id = to_resolve[idx]
            idx += 1

            # 1. Check if this project was marked as incompatible by another mod
            if current_project_id in forbidden_projects:
                raise DependencyConflictError(f"Project {current_project_id} is incompatible with a required mod.")

            # 2. If already resolved, skip to avoid infinite loops
            if current_project_id in resolved_map:
                continue

            # 3. Find the best version for the current environment
            version_obj = self._find_best_version(current_project_id, game_version, loader)
            resolved_map[current_project_id] = version_obj

            # 4. Process dependencies of this version
            for dep in version_obj.get("dependencies", []):
                dep_project_id = dep["project_id"]
                dep_type = dep["dependency_type"]

                if dep_type == "required":
                    if dep_project_id not in resolved_map:
                        to_resolve.append(dep_project_id)

                    # Double check if the required mod was previously marked as forbidden
                    if dep_project_id in forbidden_projects:
                        raise DependencyConflictError(f"Required mod {dep_project_id} is marked as incompatible.")

                elif dep_type == "incompatible":
                    forbidden_projects.add(dep_project_id)
                    # If we already resolved this mod, we have a conflict
                    if dep_project_id in resolved_map:
                        raise DependencyConflictError(f"Required mod {dep_project_id} is incompatible with {current_project_id}.")

        # Convert the resolved map into a clean list of ResolvedMod objects
        final_mods = []
        for p_id, v_obj in resolved_map.items():
            # Get the primary file (the jar)
            file = next((f for f in v_obj["files"] if f["primary"]), v_obj["files"][0])
            project = self._get_project(p_id)
            final_mods.append(ResolvedVersion(
                version_id=v_obj["id"],
                project_id=p_id,
                project_type=project["project_type"],
                file_url=file["url"],
                filename=file["filename"]
            ))

        return final_mods

    def _download_task(self, version: ResolvedVersion):
        try:
            resp = self.session.get(version.file_url, headers=HEADERS, stream=True)
            resp.raise_for_status()
            
            download_dir = os.path.join(self.download_direcotry, version.project_type)
            os.makedirs(download_dir, exist_ok=True)

            # read from stream
            with open(os.path.join(download_dir, version.filename), "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    if not chunk:
                        break
                    f.write(chunk)
            
            return version
        except Exception as e:
            print(f"Failed to download {version.filename}: {e}")
            raise

    def download(self, versions: list[ResolvedVersion], directory: str):
        self.download_direcotry = directory
        with ThreadPoolExecutor(max_workers=4) as pool:
            for result in pool.map(self._download_task, versions):
                if result:
                    print(f"Downloaded {result.file_url}.")
