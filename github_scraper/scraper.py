from __future__ import annotations

import asyncio
import base64
from collections.abc import Callable

import aiohttp

from github_scraper.models import SearchFilters
from github_scraper.logger import get_logger


logger = get_logger(__name__)

BASE_URL = "https://api.github.com"
ProgressCallback = Callable[[int, int, str], None]


def build_headers(token: str) -> dict[str, str]:
    """Build headers for GitHub API requests."""
    headers = {}
    if token:
        headers["Authorization"] = f"token {token}"
        logger.debug("Using authenticated request with token", extra={"has_token": True})
    else:
        logger.warning("No GitHub token provided - using unauthenticated requests (60/hour rate limit)")
    return headers


def build_query(filters: SearchFilters) -> str:
    """Build GitHub search query from filters."""
    logger.debug("Building search query", extra={"filters": str(filters)})
    
    query = f'location:"{filters.location}"'

    if filters.specific_query:
        query += f" {filters.specific_query}"
        logger.debug("Added specific query", extra={"query": filters.specific_query})

    if filters.created_after:
        query += f" created:>{filters.created_after}"
        logger.debug("Added creation date filter", extra={"created_after": filters.created_after})

    if filters.min_repos and filters.max_repos:
        query += f" repos:{filters.min_repos}..{filters.max_repos}"
    elif filters.min_repos:
        query += f" repos:>{filters.min_repos}"
    elif filters.max_repos:
        query += f" repos:<{filters.max_repos}"

    if filters.min_followers and filters.max_followers:
        query += f" followers:{filters.min_followers}..{filters.max_followers}"
    elif filters.min_followers:
        query += f" followers:>{filters.min_followers}"
    elif filters.max_followers:
        query += f" followers:<{filters.max_followers}"

    logger.info("Built search query", extra={"query": query})
    return query


async def fetch(
    session: aiohttp.ClientSession,
    url: str,
    headers: dict[str, str],
    params: dict[str, str | int] | None = None,
) -> dict:
    """Fetch data from GitHub API with retry logic and error handling."""
    last_error = "Request failed."
    
    logger.debug("Fetching from GitHub API", extra={"url": url, "params": params, "attempts": 3})

    for attempt in range(3):
        try:
            logger.debug(f"API request attempt {attempt + 1}", extra={"url": url, "attempt": attempt + 1})
            
            async with session.get(url, headers=headers, params=params, timeout=10) as response:
                logger.debug("Received response", extra={
                    "url": url,
                    "status": response.status,
                    "headers": dict(response.headers)
                })
                
                if response.status == 403:
                    logger.error("GitHub API rate limit exceeded", extra={
                        "status": 403,
                        "url": url,
                        "has_token": bool(headers.get("Authorization"))
                    })
                    raise RuntimeError("GitHub rate limit exceeded. Add a token or try again later.")
                
                if response.status == 404:
                    logger.warning("GitHub API returned 404", extra={"url": url})
                    return {}
                    
                if response.status >= 400:
                    text = await response.text()
                    logger.error("GitHub API error", extra={
                        "status": response.status,
                        "url": url,
                        "response_preview": text[:200]
                    })
                    raise RuntimeError(f"GitHub returned {response.status}: {text[:120]}")
                
                data = await response.json()
                logger.debug("Successfully fetched data", extra={
                    "url": url,
                    "data_size": len(str(data))
                })
                return data
                
        except RuntimeError:
            raise
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
            logger.warning(f"API request failed (attempt {attempt + 1}/3)", extra={
                "url": url,
                "error": str(exc),
                "attempt": attempt + 1
            })
            await asyncio.sleep(1)

    logger.error("All API request attempts failed", extra={
        "url": url,
        "last_error": last_error
    })
    raise RuntimeError(last_error)


async def search_users_all(
    session: aiohttp.ClientSession,
    query: str,
    headers: dict[str, str],
    max_pages: int = 10,
) -> list[dict]:
    """Search for GitHub users with pagination."""
    url = f"{BASE_URL}/search/users"
    all_users: list[dict] = []
    
    logger.info("Starting user search", extra={
        "query": query,
        "max_pages": max_pages
    })

    for page in range(1, max_pages + 1):
        logger.debug(f"Searching page {page}", extra={"page": page})
        params = {"q": query, "per_page": 100, "page": page}
        
        try:
            data = await fetch(session, url, headers, params)
            users = data.get("items", [])
            
            logger.debug(f"Found {len(users)} users on page {page}", extra={
                "page": page,
                "users_found": len(users),
                "total_users": len(all_users) + len(users)
            })
            
            if not users:
                logger.info("No more users found", extra={"last_page": page})
                break
                
            all_users.extend(users)
            
        except Exception as exc:
            logger.error(f"Failed to fetch page {page}", extra={
                "page": page,
                "error": str(exc)
            })
            break

    logger.info("User search completed", extra={
        "total_users_found": len(all_users),
        "pages_checked": page
    })
    
    return all_users


async def get_user_detail(
    session: aiohttp.ClientSession,
    username: str,
    headers: dict[str, str],
) -> dict:
    """Get detailed information for a single user."""
    logger.debug("Fetching user details", extra={"username": username})
    
    url = f"{BASE_URL}/users/{username}"
    try:
        data = await fetch(session, url, headers)
        logger.debug("Successfully fetched user details", extra={
            "username": username,
            "data_size": len(str(data))
        })
        return data
    except Exception as exc:
        logger.error("Failed to fetch user details", extra={
            "username": username,
            "error": str(exc)
        })
        raise


async def get_profile_readme(
    session: aiohttp.ClientSession,
    username: str,
    headers: dict[str, str],
) -> str:
    """Get user's profile README content."""
    logger.debug("Fetching profile README", extra={"username": username})
    
    url = f"{BASE_URL}/repos/{username}/{username}/readme"

    for attempt in range(3):
        try:
            logger.debug(f"README fetch attempt {attempt + 1}", extra={
                "username": username,
                "attempt": attempt + 1
            })
            
            async with session.get(url, headers=headers, timeout=10) as response:
                if response.status == 404:
                    logger.debug("No README found for user", extra={"username": username})
                    return ""
                
                if response.status == 403:
                    logger.error("Rate limit exceeded while fetching README", extra={
                        "username": username,
                        "status": 403
                    })
                    raise RuntimeError("GitHub rate limit exceeded. Add a token or try again later.")
                
                if response.status >= 400:
                    text = await response.text()
                    logger.warning("Failed to fetch README", extra={
                        "username": username,
                        "status": response.status,
                        "preview": text[:100]
                    })
                    raise RuntimeError(f"GitHub returned {response.status}: {text[:120]}")

                data = await response.json()
                encoded_content = data.get("content", "")
                
                if not encoded_content:
                    logger.debug("README content empty", extra={"username": username})
                    return ""

                normalized = encoded_content.replace("\n", "")
                try:
                    readme_content = base64.b64decode(normalized).decode("utf-8", errors="ignore")
                    logger.debug("Successfully decoded README", extra={
                        "username": username,
                        "content_length": len(readme_content)
                    })
                    return readme_content
                except Exception as exc:  # noqa: BLE001
                    logger.error("Failed to decode README content", extra={
                        "username": username,
                        "error": str(exc)
                    })
                    return ""
                    
        except RuntimeError:
            raise
        except Exception:  # noqa: BLE001
            logger.warning(f"README fetch attempt {attempt + 1} failed", extra={
                "username": username,
                "attempt": attempt + 1
            })
            await asyncio.sleep(1)

    logger.error("All README fetch attempts failed", extra={"username": username})
    return ""


async def get_user_detail_with_readme(
    session: aiohttp.ClientSession,
    username: str,
    headers: dict[str, str],
) -> dict:
    """Get user details and README content concurrently."""
    logger.debug("Fetching user details and README concurrently", extra={"username": username})
    
    try:
        detail, readme_content = await asyncio.gather(
            get_user_detail(session, username, headers),
            get_profile_readme(session, username, headers),
        )
        detail["readme_content"] = readme_content
        logger.debug("Successfully fetched user details and README", extra={
            "username": username,
            "has_readme": bool(readme_content)
        })
        return detail
    except Exception as exc:
        logger.error("Failed to fetch user details and README", extra={
            "username": username,
            "error": str(exc)
        })
        raise


async def fetch_all_details(
    users: list[dict],
    headers: dict[str, str],
    progress_callback: ProgressCallback | None = None,
) -> list[dict]:
    """Fetch detailed information for all users with progress tracking."""
    logger.info("Starting to fetch details for all users", extra={
        "user_count": len(users)
    })
    
    async with aiohttp.ClientSession() as session:
        tasks = [get_user_detail_with_readme(session, user["login"], headers) for user in users]
        results: list[dict] = []

        for index, task in enumerate(asyncio.as_completed(tasks), start=1):
            try:
                result = await task
                results.append(result)
                
                if progress_callback:
                    progress_callback(index, len(tasks), "Loading profile details and README content...")
                    
                logger.debug(f"Fetched details for user {index}/{len(tasks)}", extra={
                    "username": result.get("login"),
                    "progress": f"{index}/{len(tasks)}"
                })
                
            except Exception as exc:
                logger.error(f"Failed to fetch details for user", extra={
                    "index": index,
                    "total": len(tasks),
                    "error": str(exc)
                })
                # Continue with other users even if one fails

        logger.info("Completed fetching user details", extra={
            "total_users": len(results),
            "failed_users": len(tasks) - len(results)
        })
        
        return results


async def scrape_users(
    filters: SearchFilters,
    token: str,
    progress_callback: ProgressCallback | None = None,
) -> list[dict]:
    """Main function to scrape GitHub users based on filters."""
    logger.info("Starting GitHub user scraping", extra={
        "filters": str(filters),
        "has_token": bool(token)
    })
    
    headers = build_headers(token)
    query = build_query(filters)

    async with aiohttp.ClientSession() as session:
        logger.info("Searching for users", extra={"query": query})
        users = await search_users_all(session, query, headers)

        if not users:
            logger.warning("No users found matching the search criteria")
            if progress_callback:
                progress_callback(0, 1, "No profiles matched this search.")
            return []

        logger.info(f"Found {len(users)} users, fetching details...", extra={
            "user_count": len(users)
        })
        
        if progress_callback:
            progress_callback(0, len(users), f"Found {len(users)} profiles. Loading details...")

        return await fetch_all_details(users, headers, progress_callback)