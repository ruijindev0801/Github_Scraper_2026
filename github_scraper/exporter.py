from __future__ import annotations

import csv
import json
import re
from urllib import error, request
from pathlib import Path
from typing import Any

from github_scraper.models import DESTINATION_GOOGLE_SHEET, ExportSettings


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
    if not text:
        return ""

    match = EMAIL_PATTERN.search(text)
    return match.group(0) if match else ""


def extract_first_email(*texts: str | None) -> str:
    for text in texts:
        email = extract_email(text)
        if email:
            return email
    return ""


def extract_linkedin(*texts: str | None) -> str:
    for text in texts:
        if not text:
            continue

        match = LINKEDIN_PATTERN.search(text)
        if match:
            return match.group(0).rstrip(".,;:")
    return ""


def extract_discord(*texts: str | None) -> str:
    for text in texts:
        if not text:
            continue

        url_match = DISCORD_URL_PATTERN.search(text)
        if url_match:
            return url_match.group(0).rstrip(".,;:")

        labeled_match = DISCORD_TAG_PATTERN.search(text)
        if labeled_match:
            return labeled_match.group(1).rstrip(".,;:")

        legacy_match = LEGACY_DISCORD_TAG_PATTERN.search(text)
        if legacy_match:
            return legacy_match.group(1).rstrip(".,;:")

    return ""


def _matches_contact_mode(email: str, linkedin: str, discord: str, contact_mode: str) -> bool:
    if contact_mode == "email":
        return bool(email)
    if contact_mode == "linkedin":
        return bool(linkedin)
    if contact_mode == "discord":
        return bool(discord)
    return bool(email) or bool(linkedin) or bool(discord)


MALE_PRONOUN_PATTERN = re.compile(
    r"\b(?:he\s*/\s*(?:him|they)|him\s*/\s*his)\b",
    re.IGNORECASE,
)
FEMALE_PRONOUN_PATTERN = re.compile(
    r"\b(?:she\s*/\s*(?:her|they)|her\s*/\s*hers?)\b",
    re.IGNORECASE,
)


def _infer_gender_from_pronouns(*texts: str | None) -> str:
    for text in texts:
        if not text:
            continue
        if MALE_PRONOUN_PATTERN.search(text):
            return "male"
        if FEMALE_PRONOUN_PATTERN.search(text):
            return "female"
    return "unknown"


def _matches_gender(detail: dict[str, Any], gender_filter: str) -> bool:
    if gender_filter == "all":
        return True
    return _infer_gender_from_pronouns(
        detail.get("bio"),
        detail.get("readme_content"),
    ) == gender_filter


def _build_export_rows(
    details: list[dict[str, Any]],
    contact_mode: str,
    gender_filter: str = "all",
) -> list[list[str]]:
    rows: list[list[str]] = []

    for detail in details:
        username = str(detail.get("login") or "").strip()
        if not username:
            continue

        if not _matches_gender(detail, gender_filter):
            continue

        readme_content = str(detail.get("readme_content") or "").strip()
        email = str(
            detail.get("email")
            or extract_first_email(detail.get("bio"), detail.get("blog"), readme_content)
        ).strip()
        linkedin = extract_linkedin(detail.get("blog"), detail.get("bio"), readme_content).strip()
        discord = extract_discord(detail.get("blog"), detail.get("bio"), readme_content).strip()
        if not _matches_contact_mode(email, linkedin, discord, contact_mode):
            continue

        rows.append(
            [
                username,
                str(detail.get("html_url") or "").strip(),
                str(detail.get("location") or "").strip(),
                email,
                linkedin,
                discord,
            ]
        )

    return rows


def _normalize_csv_header_name(name: str) -> str:
    return name.strip().lower().lstrip("\ufeff")


def _load_existing_usernames(file_path: Path) -> set[str]:
    if not file_path.exists():
        return set()

    with file_path.open("r", newline="", encoding="utf-8") as file_obj:
        reader = csv.DictReader(file_obj)
        usernames = set()
        for row in reader:
            username = row.get("username")
            if username:
                usernames.add(username.strip())
        return usernames


def _upgrade_existing_csv_schema(file_path: Path) -> None:
    if not file_path.exists() or file_path.stat().st_size == 0:
        return

    with file_path.open("r", newline="", encoding="utf-8") as file_obj:
        rows = list(csv.reader(file_obj))

    if not rows:
        return

    current_header = rows[0]
    normalized_headers = [_normalize_csv_header_name(header) for header in current_header]
    if normalized_headers == [name.lower() for name in CSV_HEADERS]:
        return

    header_index = {name: index for index, name in enumerate(normalized_headers)}
    if "username" not in header_index:
        return

    upgraded_rows = [CSV_HEADERS]
    for row in rows[1:]:
        upgraded_rows.append(
            [
                row[header_index[name]].strip() if name in header_index and header_index[name] < len(row) else ""
                for name in CSV_HEADERS
            ]
        )

    with file_path.open("w", newline="", encoding="utf-8") as file_obj:
        writer = csv.writer(file_obj)
        writer.writerows(upgraded_rows)


def _export_profiles_to_csv(rows: list[list[str]], file_path: str) -> int:
    csv_path = Path(file_path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    _upgrade_existing_csv_schema(csv_path)
    seen = _load_existing_usernames(csv_path)
    appended_count = 0
    write_header = not csv_path.exists() or csv_path.stat().st_size == 0

    with csv_path.open("a", newline="", encoding="utf-8") as file_obj:
        writer = csv.writer(file_obj)
        if write_header:
            writer.writerow(CSV_HEADERS)

        for row in rows:
            username = row[0]
            if username in seen:
                continue

            seen.add(username)
            writer.writerow(row)
            appended_count += 1

    return appended_count


def _build_google_sheets_service(service_account_file: str) -> Any:
    try:
        from google.oauth2.service_account import Credentials
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise RuntimeError(
            "Google Sheets export requires `google-api-python-client` and "
            "`google-auth`. Install them before using this destination."
        ) from exc

    credentials = Credentials.from_service_account_file(
        service_account_file,
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    return build("sheets", "v4", credentials=credentials, cache_discovery=False)


def _parse_apps_script_response(response_body: str) -> dict[str, Any]:
    cleaned = response_body.strip()
    if not cleaned:
        return {}

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    json_match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(0))
        except json.JSONDecodeError:
            pass

    lowered = cleaned.lower()
    if "<html" in lowered or "<!doctype html" in lowered:
        if "sign in" in lowered or "accounts.google.com" in lowered:
            raise RuntimeError(
                "Apps Script returned a Google sign-in page. Redeploy the web app with access that "
                "does not require signing in from this desktop app."
            )
        raise RuntimeError(
            "Apps Script returned an HTML page instead of JSON. Check that you pasted the Web App URL "
            "from Deploy -> Manage deployments, not the editor URL."
        )

    preview = cleaned[:180].replace("\n", " ").replace("\r", " ")
    raise RuntimeError(f"Apps Script returned an unexpected response: {preview}")


def _export_profiles_to_google_sheet_via_apps_script(rows: list[list[str]], settings: ExportSettings) -> int:
    payload = {
        "spreadsheet_id": settings.spreadsheet_id(),
        "worksheet_name": settings.worksheet_name.strip(),
        "headers": CSV_HEADERS,
        "rows": rows,
    }
    body = json.dumps(payload).encode("utf-8")
    http_request = request.Request(
        settings.apps_script_url.strip(),
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with request.urlopen(http_request, timeout=20) as response:  # noqa: S310
            response_body = response.read().decode("utf-8").strip()
    except error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="ignore").strip()
        raise RuntimeError(f"Apps Script request failed with HTTP {exc.code}: {details[:180]}") from exc
    except error.URLError as exc:
        raise RuntimeError("Could not reach the Apps Script URL. Check the deployed web app URL and try again.") from exc

    data = _parse_apps_script_response(response_body)

    if data.get("status") != "success":
        raise RuntimeError(data.get("message") or "Apps Script export failed.")

    appended_count = data.get("appended_count")
    if isinstance(appended_count, int):
        return appended_count
    return len(rows)


def _load_existing_sheet_usernames(service: Any, spreadsheet_id: str, worksheet_name: str) -> set[str]:
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
    return usernames


def _ensure_sheet_header(service: Any, spreadsheet_id: str, worksheet_name: str) -> None:
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
            return

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


def _export_profiles_to_google_sheet(rows: list[list[str]], settings: ExportSettings) -> int:
    if settings.apps_script_url.strip():
        return _export_profiles_to_google_sheet_via_apps_script(rows, settings)

    service = _build_google_sheets_service(settings.service_account_file)
    spreadsheet_id = settings.spreadsheet_id()
    worksheet_name = settings.worksheet_name.strip()

    try:
        _ensure_sheet_header(service, spreadsheet_id, worksheet_name)
        seen = _load_existing_sheet_usernames(service, spreadsheet_id, worksheet_name)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            "Unable to access the Google Sheet. Confirm the spreadsheet ID/tab name is correct "
            "and that the service account has editor access."
        ) from exc

    rows_to_append = [row for row in rows if row[0] not in seen]
    if not rows_to_append:
        return 0

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
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("Failed to append rows to the Google Sheet.") from exc

    return len(rows_to_append)


def export_profiles(
    details: list[dict[str, Any]],
    settings: ExportSettings,
    contact_mode: str,
    gender_filter: str = "all",
) -> int:
    rows = _build_export_rows(details, contact_mode, gender_filter)
    if settings.destination == DESTINATION_GOOGLE_SHEET:
        return _export_profiles_to_google_sheet(rows, settings)
    return _export_profiles_to_csv(rows, settings.local_path)
