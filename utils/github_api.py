import json
import logging
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass

logger = logging.getLogger(__name__)


@dataclass
class RepoInfo:
    name: str
    full_name: str
    description: str | None
    stars: int
    forks: int
    open_issues: int
    language: str | None
    url: str


GITHUB_API_BASE = "https://api.github.com"


def fetch_repo_info(owner: str, repo: str) -> RepoInfo:
    """Fetch basic repository info from GitHub API.

    Args:
        owner: Repository owner (user or organization).
        repo: Repository name.

    Returns:
        RepoInfo dataclass with repository metadata.

    Raises:
        urllib.error.HTTPError: If the API request fails (e.g. 404, 403).
        urllib.error.URLError: If the network request fails.
        json.JSONDecodeError: If the API response is not valid JSON.
    """
    url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}"
    logger.info("Fetching repo info: %s/%s", owner, repo)

    req = urllib.request.Request(url, headers={"User-Agent": "ai-action/0.1.0"})
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode())

    return RepoInfo(
        name=data["name"],
        full_name=data["full_name"],
        description=data.get("description"),
        stars=data["stargazers_count"],
        forks=data["forks_count"],
        open_issues=data["open_issues_count"],
        language=data.get("language"),
        url=data["html_url"],
    )


def repo_info_to_dict(repo: RepoInfo) -> dict:
    """Convert RepoInfo to a JSON-serializable dict.

    Args:
        repo: RepoInfo instance.

    Returns:
        Dictionary representation of the repo info.
    """
    return asdict(repo)
