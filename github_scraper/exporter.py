from __future__ import annotations

import csv
import json
import re
from urllib import error, request
from pathlib import Path
from typing import Any

from github_scraper.models import DESTINATION_GOOGLE_SHEET, ExportSettings
from github_scraper.logger import get_logger


logger = get_logger(__name__)

EMAIL_PATTERN = re.compile(r"[\w\.-]+@[\w\.-]+")
LINKEDIN_PATTERN = re.compile(r"https?://(?:[\w-]+\.)?linkedin\.com/in/[^\s<>\]\)\"']+", re.IGNORECASE)
DISCORD_URL_PATTERN = re.compile(
    r"https?://(?:www\.)?(?:discord(?:app)?\.com/users/\d+|discord\.gg/[^\s<>\]\)\"']+)",
    re.IGNORECASE,
)
DISCORD_TAG_PATTERN = re.compile(r"(?:discord(?:\s+(?:id|tag|username|user|handle))?[:\s@-]+)([a-z0-9._]{2,32})", re.IGNORECASE)
LEGACY_DISCORD_TAG_PATTERN = re.compile(r"\b([A-Za-z0-9._]{2,32}#[0-9]{4})\b")
CSV_HEADERS = ["username", "url", "location", "email", "linkedin", "discord"]


def extract_email(text: str | None) -> str:
    """Extract email from text."""
    if not text:
        return ""
    
    match = EMAIL_PATTERN.search(text)
    if match:
        email = match.group(0)
        logger.debug("Extracted email", extra={"email": email[:10] + "..."})
        return email
    return ""


def extract_first_email(*texts: str | None) -> str:
    """Extract first email from multiple text sources."""
    for i, text in enumerate(texts):
        email = extract_email(text)
        if email:
            logger.debug("Found email in source", extra={"source_index": i, "email": email[:10] + "..."})
            return email
    return ""


def extract_linkedin(*texts: str | None) -> str:
    """Extract LinkedIn URL from text."""
    for i, text in enumerate(texts):
        if not text:
            continue
        
        match = LINKEDIN_PATTERN.search(text)
        if match:
            url = match.group(0).rstrip(".,;:")
            logger.debug("Extracted LinkedIn URL", extra={"source_index": i, "url": url[:50]})
            return url
    return ""


def extract_discord(*texts: str | None) -> str:
    """Extract Discord contact from text."""
    for i, text in enumerate(texts):
        if not text:
            continue
        
        # Check for Discord URL
        url_match = DISCORD_URL_PATTERN.search(text)
        if url_match:
            url = url_match.group(0).rstrip(".,;:")
            logger.debug("Extracted Discord URL", extra={"source_index": i, "url": url[:50]})
            return url
        
        # Check for labeled Discord tag
        labeled_match = DISCORD_TAG_PATTERN.search(text)
        if labeled_match:
            tag = labeled_match.group(1).rstrip(".,;:")
            logger.debug("Extracted Discord tag", extra={"source_index": i, "tag": tag[:30]})
            return tag
        
        # Check for legacy Discord tag format
        legacy_match = LEGACY_DISCORD_TAG_PATTERN.search(text)
        if legacy_match:
            tag = legacy_match.group(1).rstrip(".,;:")
            logger.debug("Extracted legacy Discord tag", extra={"source_index": i, "tag": tag[:30]})
            return tag
    
    return ""


def _matches_contact_mode(email: str, linkedin: str, discord: str, contact_mode: str) -> bool:
    """Check if contact matches the selected mode."""
    if contact_mode == "email":
        has_contact = bool(email)
    elif contact_mode == "linkedin":
        has_contact = bool(linkedin)
    elif contact_mode == "discord":
        has_contact = bool(discord)
    else:  # "both" or any
        has_contact = bool(email) or bool(linkedin) or bool(discord)
    
    logger.debug("Contact mode check", extra={
        "mode": contact_mode,
        "has_email": bool(email),
        "has_linkedin": bool(linkedin),
        "has_discord": bool(discord),
        "matches": has_contact
    })
    
    return has_contact


_GENDER_DETECTOR: Any = None


def _get_gender_detector() -> Any:
    """Get or create gender detector instance."""
    global _GENDER_DETECTOR
    if _GENDER_DETECTOR is not None:
        return _GENDER_DETECTOR

    try:
        from gender_guesser import detector as gender_detector
        logger.info("Gender detector initialized successfully")
    except ImportError as exc:
        logger.error("Failed to import gender-guesser package", exc_info=True)
        raise RuntimeError(
            "Gender filtering requires the `gender-guesser` package. "
            "Install it with `pip install gender-guesser`."
        ) from exc

    _GENDER_DETECTOR = gender_detector.Detector(case_sensitive=False)
    return _GENDER_DETECTOR


def _infer_gender(name: str | None) -> str:
    """Infer gender from name using gender-guesser."""
    if not name:
        logger.debug("No name provided for gender inference", extra={"result": "unknown"})
        return "unknown"

    first_name = name.strip().split()[0] if name.strip() else ""
    if not first_name:
        logger.debug("Empty first name", extra={"result": "unknown"})
        return "unknown"

    try:
        detector = _get_gender_detector()
        guess = detector.get_gender(first_name)
        logger.debug("Gender inference result", extra={
            "name": first_name,
            "guess": guess
        })
        
        if guess in ("male", "mostly_male"):
            return "male"
        if guess in ("female", "mostly_female"):
            return "female"
        return "unknown"
    except Exception as exc:
        logger.error("Gender inference failed", extra={
            "name": first_name,
            "error": str(exc)
        }, exc_info=True)
        return "unknown"


def _matches_gender(name: str | None, gender_filter: str) -> bool:
    """Check if user matches gender filter."""
    if gender_filter == "all":
        logger.debug("Gender filter disabled", extra={"filter": "all"})
        return True
    
    inferred = _infer_gender(name)
    matches = inferred == gender_filter
    
    logger.debug("Gender filter check", extra={
        "name": name[:50] if name else None,
        "filter": gender_filter,
        "inferred": inferred,
        "matches": matches
    })
    
    return matches


def _build_export_rows(
    details: list[dict[str, Any]],
    contact_mode: str,
    gender_filter: str = "all",
) -> list[list[str]]:
    """Build export rows from user details."""
    logger.info("Building export rows", extra={
        "total_users": len(details),
        "contact_mode": contact_mode,
        "gender_filter": gender_filter
    })
    
    rows: list[list[str]] = []
    skipped_count = 0

    for detail in details:
        username = str(detail.get("login") or "").strip()
        if not username:
            logger.warning("Skipping user with no username", extra={"detail": str(detail)[:100]})
            skipped_count += 1
            continue

        if not _matches_gender(detail.get("name"), gender_filter):
            logger.debug("Skipping user due to gender filter", extra={"username": username})
            skipped_count += 1
            continue

        readme_content = str(detail.get("readme_content") or "").strip()
        
        # Extract contact information
        email = str(
            detail.get("email")
            or extract_first_email(detail.get("bio"), detail.get("blog"), readme_content)
        ).strip()
        
        linkedin = extract_linkedin(detail.get("blog"), detail.get("bio"), readme_content).strip()
        discord = extract_discord(detail.get("blog"), detail.get("bio"), readme_content).strip()
        
        if not _matches_contact_mode(email, linkedin, discord, contact_mode):
            logger.debug("Skipping user due to contact mode filter", extra={
                "username": username,
                "contact_mode": contact_mode,
                "has_email": bool(email),
                "has_linkedin": bool(linkedin),
                "has_discord": bool(discord)
            })
            skipped_count += 1
            continue

        rows.append([
            username,
            str(detail.get("html_url") or "").strip(),
            str(detail.get("location") or "").strip(),
            email,
            linkedin,
            discord,
        ])
        
        logger.debug("Added user to export rows", extra={"username": username})

    logger.info("Export rows built", extra={
        "total_rows": len(rows),
        "skipped_users": skipped_count,
        "original_users": len(details)
    })
    
    return rows


def _normalize_csv_header_name(name: str) -> str:
    """Normalize CSV header name for comparison."""
    return name.strip().lower().lstrip("\ufeff")


def _load_existing_usernames(file_path: Path) -> set[str]:
    """Load existing usernames from CSV file."""
    if not file_path.exists():
        logger.debug("CSV file does not exist", extra={"path": str(file_path)})
        return set()
    
    logger.debug("Loading existing usernames from CSV", extra={"path": str(file_path)})
    
    try:
        with file_path.open("r", newline="", encoding="utf-8") as file_obj:
            reader = csv.DictReader(file_obj)
            usernames = set()
            for row_num, row in enumerate(reader, 1):
                username = row.get("username")
                if username:
                    usernames.add(username.strip())
            
            logger.info("Loaded existing usernames", extra={
                "count": len(usernames),
                "path": str(file_path)
            })
            return usernames
    except Exception as exc:
        logger.error("Failed to load existing usernames", extra={
            "path": str(file_path),
            "error": str(exc)
        }, exc_info=True)
        return set()


def _upgrade_existing_csv_schema(file_path: Path) -> None:
    """Upgrade existing CSV to current schema if needed."""
    if not file_path.exists() or file_path.stat().st_size == 0:
        logger.debug("No existing CSV to upgrade", extra={"path": str(file_path)})
        return
    
    logger.debug("Checking CSV schema", extra={"path": str(file_path)})
    
    try:
        with file_path.open("r", newline="", encoding="utf-8") as file_obj:
            rows = list(csv.reader(file_obj))
        
        if not rows:
            logger.debug("CSV file is empty", extra={"path": str(file_path)})
            return
        
        current_header = rows[0]
        normalized_headers = [_normalize_csv_header_name(header) for header in current_header]
        
        if normalized_headers == [name.lower() for name in CSV_HEADERS]:
            logger.debug("CSV schema is already current", extra={"path": str(file_path)})
            return
        
        logger.info("Upgrading CSV schema", extra={
            "path": str(file_path),
            "old_headers": current_header,
            "new_headers": CSV_HEADERS
        })
        
        header_index = {name: index for index, name in enumerate(normalized_headers)}
        if "username" not in header_index:
            logger.warning("No username column found in CSV", extra={"path": str(file_path)})
            return
        
        upgraded_rows = [CSV_HEADERS]
        for row in rows[1:]:
            upgraded_rows.append([
                row[header_index[name]].strip() if name in header_index and header_index[name] < len(row) else ""
                for name in CSV_HEADERS
            ])
        
        with file_path.open("w", newline="", encoding="utf-8") as file_obj:
            writer = csv.writer(file_obj)
            writer.writerows(upgraded_rows)
        
        logger.info("CSV schema upgraded successfully", extra={"path": str(file_path)})
        
    except Exception as exc:
        logger.error("Failed to upgrade CSV schema", extra={
            "path": str(file_path),
            "error": str(exc)
        }, exc_info=True)


def _export_profiles_to_csv(rows: list[list[str]], file_path: str) -> int:
    """Export profiles to local CSV file."""
    csv_path = Path(file_path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    
    logger.info("Starting CSV export", extra={
        "path": str(csv_path),
        "row_count": len(rows)
    })
    
    try:
        _upgrade_existing_csv_schema(csv_path)
        seen = _load_existing_usernames(csv_path)
        appended_count = 0
        write_header = not csv_path.exists() or csv_path.stat().st_size == 0
        
        with csv_path.open("a", newline="", encoding="utf-8") as file_obj:
            writer = csv.writer(file_obj)
            if write_header:
                writer.writerow(CSV_HEADERS)
                logger.debug("Writing CSV headers", extra={"headers": CSV_HEADERS})
            
            for row in rows:
                username = row[0]
                if username in seen:
                    logger.debug("Skipping duplicate username", extra={"username": username})
                    continue
                
                seen.add(username)
                writer.writerow(row)
                appended_count += 1
                logger.debug("Appended user to CSV", extra={"username": username})
        
        logger.info("CSV export completed", extra={
            "path": str(csv_path),
            "new_rows": appended_count,
            "total_unique_users": len(seen)
        })
        
        return appended_count
        
    except Exception as exc:
        logger.error("CSV export failed", extra={
            "path": str(csv_path),
            "error": str(exc)
        }, exc_info=True)
        raise


def _build_google_sheets_service(service_account_file: str) -> Any:
    """Build Google Sheets service from service account file."""
    logger.info("Building Google Sheets service", extra={
        "service_account_file": Path(service_account_file).name
    })
    
    try:
        from google.oauth2.service_account import Credentials
        from googleapiclient.discovery import build
        logger.debug("Google API libraries imported successfully")
    except ImportError as exc:
        logger.error("Failed to import Google API libraries", exc_info=True)
        raise RuntimeError(
            "Google Sheets export requires `google-api-python-client` and "
            "`google-auth`. Install them before using this destination."
        ) from exc
    
    try:
        credentials = Credentials.from_service_account_file(
            service_account_file,
            scopes=["https://www.googleapis.com/auth/spreadsheets"],
        )
        service = build("sheets", "v4", credentials=credentials, cache_discovery=False)
        logger.info("Google Sheets service built successfully")
        return service
    except Exception as exc:
        logger.error("Failed to build Google Sheets service", exc_info=True)
        raise


def _parse_apps_script_response(response_body: str) -> dict[str, Any]:
    """Parse Apps Script response with error handling."""
    cleaned = response_body.strip()
    if not cleaned:
        logger.error("Empty Apps Script response")
        return {}
    
    try:
        data = json.loads(cleaned)
        logger.debug("Successfully parsed Apps Script JSON response")
        return data
    except json.JSONDecodeError:
        logger.warning("Failed to parse Apps Script response as JSON", extra={
            "preview": cleaned[:100]
        })
        pass
    
    # Try to extract JSON from HTML response
    json_match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group(0))
            logger.debug("Extracted JSON from HTML response")
            return data
        except json.JSONDecodeError:
            logger.error("Failed to parse extracted JSON", exc_info=True)
            pass
    
    # Check for sign-in page
    lowered = cleaned.lower()
    if "<html" in lowered or "<!doctype html" in lowered:
        if "sign in" in lowered or "accounts.google.com" in lowered:
            logger.error("Apps Script returned Google sign-in page")
            raise RuntimeError(
                "Apps Script returned a Google sign-in page. Redeploy the web app with access that "
                "does not require signing in from this desktop app."
            )
        logger.error("Apps Script returned HTML instead of JSON")
        raise RuntimeError(
            "Apps Script returned an HTML page instead of JSON. Check that you pasted the Web App URL "
            "from Deploy -> Manage deployments, not the editor URL."
        )
    
    preview = cleaned[:180].replace("\n", " ").replace("\r", " ")
    logger.error("Apps Script returned unexpected response", extra={"preview": preview})
    raise RuntimeError(f"Apps Script returned an unexpected response: {preview}")


def _export_profiles_to_google_sheet_via_apps_script(rows: list[list[str]], settings: ExportSettings) -> int:
    """Export to Google Sheet via Apps Script Web App."""
    logger.info("Exporting to Google Sheet via Apps Script", extra={
        "spreadsheet_id": settings.spreadsheet_id(),
        "worksheet_name": settings.worksheet_name,
        "row_count": len(rows)
    })
    
    payload = {
        "spreadsheet_id": settings.spreadsheet_id(),
        "worksheet_name": settings.worksheet_name.strip(),
        "headers": CSV_HEADERS,
        "rows": rows,
    }
    body = json.dumps(payload).encode("utf-8")
    
    logger.debug("Sending request to Apps Script", extra={
        "url": settings.apps_script_url.strip()[:60] + "..."
    })
    
    http_request = request.Request(
        settings.apps_script_url.strip(),
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    
    try:
        with request.urlopen(http_request, timeout=20) as response:  # noqa: S310
            response_body = response.read().decode("utf-8").strip()
            logger.debug("Received response from Apps Script", extra={
                "status": response.status,
                "content_length": len(response_body)
            })
    except error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="ignore").strip()
        logger.error("Apps Script HTTP error", extra={
            "status": exc.code,
            "details": details[:180]
        })
        raise RuntimeError(f"Apps Script request failed with HTTP {exc.code}: {details[:180]}") from exc
    except error.URLError as exc:
        logger.error("Apps Script URL error", exc_info=True)
        raise RuntimeError("Could not reach the Apps Script URL. Check the deployed web app URL and try again.") from exc
    except Exception as exc:
        logger.error("Apps Script request failed", exc_info=True)
        raise
    
    try:
        data = _parse_apps_script_response(response_body)
        
        if data.get("status") != "success":
            message = data.get("message") or "Apps Script export failed."
            logger.error("Apps Script export failed", extra={"message": message})
            raise RuntimeError(message)
        
        appended_count = data.get("appended_count")
        if isinstance(appended_count, int):
            logger.info("Apps Script export completed", extra={"appended_count": appended_count})
            return appended_count
        
        logger.warning("Apps Script did not return appended count, using row count")
        return len(rows)
        
    except Exception as exc:
        logger.error("Failed to parse Apps Script response", exc_info=True)
        raise


def _load_existing_sheet_usernames(service: Any, spreadsheet_id: str, worksheet_name: str) -> set[str]:
    """Load existing usernames from Google Sheet."""
    logger.debug("Loading existing usernames from Google Sheet", extra={
        "spreadsheet_id": spreadsheet_id,
        "worksheet_name": worksheet_name
    })
    
    try:
        response = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=spreadsheet_id, range=f"{worksheet_name}!A:A")
            .execute()
        )
        values = response.get("values", [])
        usernames = {
            row[0].strip()
            for index, row in enumerate(values)
            if row and row[0].strip() and not (index == 0 and row[0].strip().lower() == "username")
        }
        logger.info("Loaded existing usernames from Google Sheet", extra={"count": len(usernames)})
        return usernames
    except Exception as exc:
        logger.error("Failed to load existing sheet usernames", exc_info=True)
        raise


def _ensure_sheet_header(service: Any, spreadsheet_id: str, worksheet_name: str) -> None:
    """Ensure Google Sheet has correct header row."""
    logger.debug("Checking Google Sheet headers", extra={
        "spreadsheet_id": spreadsheet_id,
        "worksheet_name": worksheet_name
    })
    
    try:
        response = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=spreadsheet_id, range=f"{worksheet_name}!A1:F1")
            .execute()
        )
        values = response.get("values", [])
        
        if values:
            current_header = values[0]
            if current_header[: len(CSV_HEADERS)] == CSV_HEADERS:
                logger.debug("Sheet headers are correct")
                return
        
        logger.info("Updating sheet headers", extra={"headers": CSV_HEADERS})
        (
            service.spreadsheets()
            .values()
            .update(
                spreadsheetId=spreadsheet_id,
                range=f"{worksheet_name}!A1:F1",
                valueInputOption="RAW",
                body={"values": [CSV_HEADERS]},
            )
            .execute()
        )
        logger.info("Sheet headers updated successfully")
        
    except Exception as exc:
        logger.error("Failed to ensure sheet headers", exc_info=True)
        raise


def _export_profiles_to_google_sheet(rows: list[list[str]], settings: ExportSettings) -> int:
    """Export profiles to Google Sheet via service account."""
    logger.info("Exporting to Google Sheet via service account", extra={
        "spreadsheet_id": settings.spreadsheet_id(),
        "worksheet_name": settings.worksheet_name,
        "row_count": len(rows)
    })
    
    service = _build_google_sheets_service(settings.service_account_file)
    spreadsheet_id = settings.spreadsheet_id()
    worksheet_name = settings.worksheet_name.strip()
    
    try:
        _ensure_sheet_header(service, spreadsheet_id, worksheet_name)
        seen = _load_existing_sheet_usernames(service, spreadsheet_id, worksheet_name)
    except Exception as exc:
        logger.error("Failed to access Google Sheet", exc_info=True)
        raise RuntimeError(
            "Unable to access the Google Sheet. Confirm the spreadsheet ID/tab name is correct "
            "and that the service account has editor access."
        ) from exc
    
    rows_to_append = [row for row in rows if row[0] not in seen]
    
    if not rows_to_append:
        logger.info("No new users to append", extra={
            "existing_users": len(seen),
            "total_rows": len(rows)
        })
        return 0
    
    logger.info("Appending new rows", extra={
        "new_rows": len(rows_to_append),
        "total_unique_users": len(seen) + len(rows_to_append)
    })
    
    try:
        (
            service.spreadsheets()
            .values()
            .append(
                spreadsheetId=spreadsheet_id,
                range=f"{worksheet_name}!A:F",
                valueInputOption="RAW",
                insertDataOption="INSERT_ROWS",
                body={"values": rows_to_append},
            )
            .execute()
        )
        logger.info("Successfully appended rows to Google Sheet")
        return len(rows_to_append)
        
    except Exception as exc:
        logger.error("Failed to append rows to Google Sheet", exc_info=True)
        raise RuntimeError("Failed to append rows to the Google Sheet.") from exc


def export_profiles(
    details: list[dict[str, Any]],
    settings: ExportSettings,
    contact_mode: str,
    gender_filter: str = "all",
) -> int:
    """Main export function that handles both CSV and Google Sheet exports."""
    logger.info("Starting profile export", extra={
        "destination": settings.destination,
        "contact_mode": contact_mode,
        "gender_filter": gender_filter,
        "user_count": len(details)
    })
    
    try:
        rows = _build_export_rows(details, contact_mode, gender_filter)
        
        if settings.destination == DESTINATION_GOOGLE_SHEET:
            if settings.apps_script_url.strip():
                logger.debug("Using Apps Script method")
                result = _export_profiles_to_google_sheet_via_apps_script(rows, settings)
            else:
                logger.debug("Using service account method")
                result = _export_profiles_to_google_sheet(rows, settings)
        else:
            logger.debug("Using CSV export method")
            result = _export_profiles_to_csv(rows, settings.local_path)
        
        logger.info("Profile export completed", extra={
            "destination": settings.destination,
            "exported_count": result
        })
        
        return result
        
    except Exception as exc:
        logger.error("Profile export failed", exc_info=True)
        raise