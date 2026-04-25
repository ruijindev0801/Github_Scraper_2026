# GitHub Scraper 2026

A desktop Tkinter app for searching public GitHub profiles by location and optional filters, then exporting the results to either a local CSV file or a Google Sheet.

## Features

- Search GitHub users by required location
- Narrow results with optional keyword, creation date, repository count, and follower count filters
- Filter results by inferred gender (All / Male / Female) using the user's profile name
- Export profile details to a local CSV file or a Google Sheet
- Include email, LinkedIn, and Discord details when they are publicly available
- Read each user's GitHub profile README and extract email, LinkedIn, or Discord details from there too
- Track progress while profile details are being fetched

## Requirements

- Python 3.10+
- `aiohttp`
- `customtkinter`
- `gender-guesser` for the gender filter
- `google-api-python-client` and `google-auth` only if you want the service-account Google Sheets fallback

## Install

```bash
pip install aiohttp customtkinter gender-guesser
```

For Google Sheets export, also install:

```bash
pip install google-api-python-client google-auth
```

You do not need these packages if you use the Apps Script Web App method below.

## Run

```bash
python main.py
```

## Screenshots

### Google Sheets Export

![GitHub Talent Scraper with Google Sheets export selected](Screenshot_1.png)

### Local CSV Export

![GitHub Talent Scraper with local CSV export selected](Screenshot_2.png)

## Google Sheets Setup

### Option 1: Apps Script Web App (Recommended)

1. Open your target Google Sheet.
2. Go to `Extensions` -> `Apps Script`.
3. Replace the default script with a web app handler.
4. Deploy it as a Web App.
5. In the deployment settings, use the actual `Web app` URL and choose access that does not require the desktop app to sign in.
6. In the app, choose `google sheet`, then fill in:
   - `Spreadsheet URL or ID`
   - `Worksheet Name`
   - `Apps Script Web App URL`

This method does not require a downloaded JSON key.

### Option 2: Service Account Fallback

1. Create or choose a Google Cloud project.
2. Enable the Google Sheets API for that project.
3. Create a service account and download its JSON key.
4. Share your target Google Sheet with the service account email as an editor.
5. In the app, fill in `Service Account JSON` instead of the Apps Script URL.

The app accepts either the full Google Sheet URL or just the spreadsheet ID for both methods.

## Exported Columns

Both destinations use the same columns:

- `username`
- `url`
- `location`
- `email`
- `linkedin`
- `discord`

## Notes

- A GitHub token is optional, but recommended to reduce rate-limit issues.
- `Location` is the only required search field.
- `Creation Date` must use `YYYY-MM-DD`.
- Min and max repo/follower fields must be whole numbers.
- Duplicate usernames are skipped for both CSV and Google Sheets exports.
- Profile README content is checked in addition to the GitHub bio and blog fields.
- The Discord column is extracted from public bio/blog/README text when it matches common Discord URLs or usernames.
- The gender filter infers gender from the user's profile name via `gender-guesser`. Profiles without a recognizable first name are skipped when `Male` or `Female` is selected; pick `All` to disable the filter.

## Project Structure

```text
main.py
github_scraper/
  exporter.py
  models.py
  scraper.py
  ui.py
```

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).
