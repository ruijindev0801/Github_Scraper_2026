from __future__ import annotations

import asyncio
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from github_scraper.exporter import export_profiles
from github_scraper.models import (
    DESTINATION_GOOGLE_SHEET,
    DESTINATION_LOCAL,
    ExportSettings,
    SearchFilters,
)
from github_scraper.scraper import scrape_users


RESULT_CSV_PATH = Path(__file__).resolve().parent.parent / "result.csv"
SIDE_PANEL_WIDTH = 300
WINDOW_WIDTH = 960
WINDOW_HEIGHT = 720


class GitHubScraperApp:
    def __init__(self) -> None:
        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")

        self.root = ctk.CTk()
        self.root.title("GitHub Talent Scraper")
        self.root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
        self.root.minsize(900, 680)
        self.root.configure(fg_color="#eef3f8")

        self._create_variables()
        self._build_layout()
        self._refresh_destination_ui()
        self._center_window()
        self.root.after(100, self._center_window)

        self.is_running = False

    def _create_variables(self) -> None:
        self.token_var = tk.StringVar()
        self.specific_query_var = tk.StringVar()
        self.location_var = tk.StringVar()
        self.created_var = tk.StringVar()
        self.min_repos_var = tk.StringVar()
        self.max_repos_var = tk.StringVar()
        self.min_followers_var = tk.StringVar()
        self.max_followers_var = tk.StringVar()
        self.contact_mode_var = tk.StringVar(value="both")
        self.gender_var = tk.StringVar(value="male")
        self.destination_var = tk.StringVar(value=DESTINATION_LOCAL)
        self.local_result_var = tk.StringVar(value=str(RESULT_CSV_PATH))
        self.google_sheet_var = tk.StringVar()
        self.google_sheet_tab_var = tk.StringVar(value="Sheet1")
        self.google_apps_script_var = tk.StringVar()
        self.google_credentials_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Ready")
        self.progress_text_var = tk.StringVar(value="0 / 0")
        self.progress_percent_var = tk.StringVar(value="0%")
        self.result_var = tk.StringVar(value=str(RESULT_CSV_PATH))
        self.output_title_var = tk.StringVar(value="Local CSV")

        for variable in (
            self.destination_var,
            self.local_result_var,
            self.google_sheet_var,
            self.google_sheet_tab_var,
            self.google_apps_script_var,
        ):
            variable.trace_add("write", self._handle_destination_change)

    def _handle_destination_change(self, *_args: object) -> None:
        if hasattr(self, "root"):
            self.root.after_idle(self._refresh_destination_ui)

    def _build_layout(self) -> None:
        shell = ctk.CTkFrame(
            self.root,
            fg_color="#ffffff",
            corner_radius=18,
            border_width=1,
            border_color="#dde6f0",
        )
        shell.pack(fill="both", expand=True, padx=12, pady=12)
        shell.grid_columnconfigure(0, weight=1)
        shell.grid_columnconfigure(1, minsize=SIDE_PANEL_WIDTH)
        shell.grid_rowconfigure(1, weight=1)

        self._build_topbar(shell)
        self._build_form_panel(shell)
        self._build_side_panel(shell)

    def _build_topbar(self, parent: ctk.CTkFrame) -> None:
        topbar = ctk.CTkFrame(parent, fg_color="transparent")
        topbar.grid(row=0, column=0, columnspan=2, sticky="ew", padx=16, pady=(16, 12))
        topbar.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            topbar,
            text="GitHub Talent Scraper",
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color="#1b2b3d",
        ).grid(row=0, column=0, sticky="w")

        stats = ctk.CTkFrame(topbar, fg_color="transparent")
        stats.grid(row=0, column=1, sticky="e")

        stat_specs = [
            ("Location", "Required"),
            ("CSV or Sheet", "Output"),
            ("No duplicates", "Append only"),
        ]
        for index, (value, label) in enumerate(stat_specs):
            card = ctk.CTkFrame(
                stats,
                fg_color="#f4f8fc",
                corner_radius=14,
                border_width=1,
                border_color="#dce5ef",
            )
            card.grid(row=0, column=index, padx=(8 if index else 0, 0), sticky="e")
            ctk.CTkLabel(
                card,
                text=value,
                font=ctk.CTkFont(size=14, weight="bold"),
                text_color="#17324d",
            ).pack(anchor="w", padx=12, pady=(8, 0))
            ctk.CTkLabel(
                card,
                text=label,
                font=ctk.CTkFont(size=10),
                text_color="#71849a",
            ).pack(anchor="w", padx=12, pady=(1, 8))

    def _build_form_panel(self, parent: ctk.CTkFrame) -> None:
        panel = ctk.CTkFrame(parent, fg_color="transparent")
        panel.grid(row=1, column=0, sticky="nsew", padx=(16, 8), pady=(0, 16))
        panel.grid_columnconfigure(0, weight=1)
        panel.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            panel,
            text="Search Filters",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#223548",
        ).grid(row=0, column=0, columnspan=2, sticky="w")

        self._build_field(panel, 1, 0, "GitHub Token", self.token_var, masked=True, required=False)
        self._build_field(panel, 1, 1, "Location", self.location_var, masked=False, required=True)
        self._build_field(panel, 2, 0, "Specific Query", self.specific_query_var, masked=False, required=False)
        self._build_field(panel, 2, 1, "Creation Date", self.created_var, masked=False, required=False)
        self._build_field(panel, 3, 0, "Min Repos", self.min_repos_var, masked=False, required=False)
        self._build_field(panel, 3, 1, "Max Repos", self.max_repos_var, masked=False, required=False)
        self._build_field(panel, 4, 0, "Min Followers", self.min_followers_var, masked=False, required=False)
        self._build_field(panel, 4, 1, "Max Followers", self.max_followers_var, masked=False, required=False)

        self._build_contact_mode(panel, 5)
        self._build_gender_filter(panel, 6)
        self._build_actions(panel, 7)
        self._build_progress(panel, 8)

    def _build_field(
        self,
        parent: ctk.CTkFrame,
        row: int,
        column: int,
        label: str,
        variable: tk.StringVar,
        masked: bool,
        required: bool,
    ) -> None:
        field = ctk.CTkFrame(parent, fg_color="transparent")
        field.grid(
            row=row,
            column=column,
            sticky="ew",
            padx=(0, 6) if column == 0 else (6, 0),
            pady=(12, 0),
        )
        field.grid_columnconfigure(0, weight=1)

        title = f"{label} *" if required else label
        ctk.CTkLabel(
            field,
            text=title,
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#24374a",
        ).grid(row=0, column=0, sticky="w", pady=(0, 4))

        entry = ctk.CTkEntry(
            field,
            textvariable=variable,
            show="*" if masked else "",
            height=34,
            corner_radius=10,
            fg_color="#f8fbfe",
            border_color="#d7e1ec",
            text_color="#13273a",
        )
        entry.grid(row=1, column=0, sticky="ew")

    def _build_contact_mode(self, parent: ctk.CTkFrame, row: int) -> None:
        block = ctk.CTkFrame(parent, fg_color="transparent")
        block.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(14, 0))
        block.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            block,
            text="Valid Contact Type",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#223548",
        ).grid(row=0, column=0, sticky="w", pady=(0, 6))

        self.contact_segment = ctk.CTkSegmentedButton(
            block,
            values=["email", "linkedin", "discord", "both"],
            variable=self.contact_mode_var,
            height=32,
            corner_radius=10,
            fg_color="#e8eef7",
            selected_color="#2f6fed",
            selected_hover_color="#245ed5",
            unselected_color="#e8eef7",
            unselected_hover_color="#dce6f4",
            text_color="#1f3555",
            font=ctk.CTkFont(size=11, weight="bold"),
        )
        self.contact_segment.grid(row=1, column=0, sticky="ew")
        self.contact_segment.set("both")

    def _build_gender_filter(self, parent: ctk.CTkFrame, row: int) -> None:
        block = ctk.CTkFrame(parent, fg_color="transparent")
        block.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(14, 0))
        block.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            block,
            text="Gender",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#223548",
        ).grid(row=0, column=0, sticky="w", pady=(0, 6))

        options = ctk.CTkFrame(block, fg_color="transparent")
        options.grid(row=1, column=0, sticky="w")

        for index, (value, label) in enumerate(
            (("all", "All"), ("male", "Male"), ("female", "Female"))
        ):
            ctk.CTkRadioButton(
                options,
                text=label,
                value=value,
                variable=self.gender_var,
                radiobutton_width=18,
                radiobutton_height=18,
                border_width_unchecked=2,
                border_width_checked=5,
                fg_color="#2f6fed",
                hover_color="#245ed5",
                border_color="#b9c7d9",
                text_color="#1f3555",
                font=ctk.CTkFont(size=11, weight="bold"),
            ).grid(row=0, column=index, sticky="w", padx=(0 if index == 0 else 18, 0))

    def _build_actions(self, parent: ctk.CTkFrame, row: int) -> None:
        actions = ctk.CTkFrame(parent, fg_color="transparent")
        actions.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(16, 0))
        actions.grid_columnconfigure(0, weight=1)

        self.start_button = ctk.CTkButton(
            actions,
            text="Export Matching Profiles",
            command=self._start_scrape,
            height=34,
            corner_radius=10,
            fg_color="#2f6fed",
            hover_color="#245ed5",
            text_color="#ffffff",
            font=ctk.CTkFont(size=11, weight="bold"),
        )
        self.start_button.grid(row=0, column=0, sticky="w")

        ctk.CTkButton(
            actions,
            text="Clear",
            command=self._clear_filters,
            height=34,
            corner_radius=10,
            fg_color="#eaf1fb",
            hover_color="#dce7f7",
            text_color="#2958ab",
            font=ctk.CTkFont(size=11, weight="bold"),
        ).grid(row=0, column=1, sticky="e", padx=(8, 0))

    def _build_progress(self, parent: ctk.CTkFrame, row: int) -> None:
        card = ctk.CTkFrame(
            parent,
            fg_color="#f5f8fc",
            corner_radius=14,
            border_width=1,
            border_color="#dce5ef",
        )
        card.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(14, 0))
        card.grid_columnconfigure(0, weight=1)

        top = ctk.CTkFrame(card, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 0))
        top.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            top,
            text="Progress",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#203548",
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            top,
            textvariable=self.progress_percent_var,
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color="#18324f",
        ).grid(row=0, column=1, sticky="e")

        ctk.CTkLabel(
            card,
            textvariable=self.status_var,
            font=ctk.CTkFont(size=10),
            text_color="#6b8198",
        ).grid(row=1, column=0, sticky="w", padx=14, pady=(4, 8))

        self.progress = ctk.CTkProgressBar(
            card,
            height=10,
            corner_radius=999,
            fg_color="#dce7f4",
            progress_color="#2f6fed",
        )
        self.progress.grid(row=2, column=0, sticky="ew", padx=14)
        self.progress.set(0)

        ctk.CTkLabel(
            card,
            textvariable=self.progress_text_var,
            font=ctk.CTkFont(size=10),
            text_color="#6b8198",
        ).grid(row=3, column=0, sticky="e", padx=14, pady=(6, 12))

    def _build_side_panel(self, parent: ctk.CTkFrame) -> None:
        panel = ctk.CTkFrame(parent, fg_color="transparent", width=SIDE_PANEL_WIDTH)
        panel.grid(row=1, column=1, sticky="nsew", padx=(8, 16), pady=(0, 16))
        panel.grid_columnconfigure(0, weight=1, minsize=SIDE_PANEL_WIDTH)
        panel.grid_propagate(False)

        ctk.CTkLabel(
            panel,
            text="Output",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#223548",
        ).grid(row=0, column=0, sticky="w")

        destination_card = ctk.CTkFrame(
            panel,
            fg_color="#f5f8fc",
            width=SIDE_PANEL_WIDTH,
            corner_radius=14,
            border_width=1,
            border_color="#dce5ef",
        )
        destination_card.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        destination_card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            destination_card,
            text="Save Location",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#223548",
        ).grid(row=0, column=0, sticky="w", padx=12, pady=(12, 6))

        self.destination_segment = ctk.CTkSegmentedButton(
            destination_card,
            values=[DESTINATION_LOCAL, DESTINATION_GOOGLE_SHEET],
            variable=self.destination_var,
            command=lambda _value: self._refresh_destination_ui(),
            height=32,
            corner_radius=10,
            fg_color="#e8eef7",
            selected_color="#2f6fed",
            selected_hover_color="#245ed5",
            unselected_color="#e8eef7",
            unselected_hover_color="#dce6f4",
            text_color="#1f3555",
            font=ctk.CTkFont(size=11, weight="bold"),
        )
        self.destination_segment.grid(row=1, column=0, sticky="ew", padx=12)

        self.local_settings_frame = ctk.CTkFrame(destination_card, fg_color="transparent")
        self.local_settings_frame.grid(row=2, column=0, sticky="ew", padx=12, pady=(10, 12))
        self.local_settings_frame.grid_columnconfigure(0, weight=1)
        self.local_settings_frame.grid_columnconfigure(1, weight=0)
        ctk.CTkLabel(
            self.local_settings_frame,
            text="CSV File",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#24374a",
        ).grid(row=0, column=0, sticky="w", pady=(0, 4))
        ctk.CTkEntry(
            self.local_settings_frame,
            textvariable=self.local_result_var,
            height=34,
            corner_radius=10,
            fg_color="#ffffff",
            border_color="#d7e1ec",
            text_color="#13273a",
        ).grid(row=1, column=0, sticky="ew")
        ctk.CTkButton(
            self.local_settings_frame,
            text="Browse",
            command=self._browse_local_file,
            width=80,
            height=32,
            corner_radius=10,
            fg_color="#eaf1fb",
            hover_color="#dce7f7",
            text_color="#2958ab",
            font=ctk.CTkFont(size=11, weight="bold"),
        ).grid(row=1, column=1, padx=(8, 0))

        self.sheet_settings_frame = ctk.CTkFrame(destination_card, fg_color="transparent")
        self.sheet_settings_frame.grid(row=3, column=0, sticky="ew", padx=12, pady=(10, 12))
        self.sheet_settings_frame.grid_columnconfigure(0, weight=1)
        self.sheet_settings_frame.grid_columnconfigure(1, weight=0)
        ctk.CTkLabel(
            self.sheet_settings_frame,
            text="Spreadsheet URL or ID",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#24374a",
            wraplength=SIDE_PANEL_WIDTH - 48,
            justify="left",
        ).grid(row=0, column=0, sticky="w", pady=(0, 4))
        ctk.CTkEntry(
            self.sheet_settings_frame,
            textvariable=self.google_sheet_var,
            height=34,
            corner_radius=10,
            fg_color="#ffffff",
            border_color="#d7e1ec",
            text_color="#13273a",
        ).grid(row=1, column=0, sticky="ew")
        ctk.CTkLabel(
            self.sheet_settings_frame,
            text="Worksheet Name",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#24374a",
        ).grid(row=2, column=0, sticky="w", pady=(10, 4))
        ctk.CTkEntry(
            self.sheet_settings_frame,
            textvariable=self.google_sheet_tab_var,
            height=34,
            corner_radius=10,
            fg_color="#ffffff",
            border_color="#d7e1ec",
            text_color="#13273a",
        ).grid(row=3, column=0, sticky="ew")
        ctk.CTkLabel(
            self.sheet_settings_frame,
            text="Apps Script Web App URL",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#24374a",
            wraplength=SIDE_PANEL_WIDTH - 48,
            justify="left",
        ).grid(row=4, column=0, sticky="w", pady=(10, 4))
        ctk.CTkEntry(
            self.sheet_settings_frame,
            textvariable=self.google_apps_script_var,
            height=34,
            corner_radius=10,
            fg_color="#ffffff",
            border_color="#d7e1ec",
            text_color="#13273a",
        ).grid(row=5, column=0, columnspan=2, sticky="ew")
        ctk.CTkLabel(
            self.sheet_settings_frame,
            text="Service Account JSON (Optional Fallback)",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#24374a",
            wraplength=SIDE_PANEL_WIDTH - 48,
            justify="left",
        ).grid(row=6, column=0, sticky="w", pady=(10, 4))
        ctk.CTkEntry(
            self.sheet_settings_frame,
            textvariable=self.google_credentials_var,
            height=34,
            corner_radius=10,
            fg_color="#ffffff",
            border_color="#d7e1ec",
            text_color="#13273a",
        ).grid(row=7, column=0, sticky="ew")
        ctk.CTkButton(
            self.sheet_settings_frame,
            text="Browse",
            command=self._browse_credentials_file,
            width=80,
            height=32,
            corner_radius=10,
            fg_color="#eaf1fb",
            hover_color="#dce7f7",
            text_color="#2958ab",
            font=ctk.CTkFont(size=11, weight="bold"),
        ).grid(row=7, column=1, padx=(8, 0))

        result_card = ctk.CTkFrame(
            panel,
            fg_color="#f5f8fc",
            width=SIDE_PANEL_WIDTH,
            corner_radius=14,
            border_width=1,
            border_color="#dce5ef",
        )
        result_card.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        ctk.CTkLabel(
            result_card,
            textvariable=self.output_title_var,
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#18324f",
        ).pack(anchor="w", padx=12, pady=(12, 0))
        ctk.CTkLabel(
            result_card,
            textvariable=self.result_var,
            font=ctk.CTkFont(size=10),
            text_color="#6b8198",
            justify="left",
            wraplength=SIDE_PANEL_WIDTH - 48,
        ).pack(anchor="w", padx=12, pady=(4, 12))

    def _browse_local_file(self) -> None:
        file_path = filedialog.asksaveasfilename(
            title="Choose CSV file",
            defaultextension=".csv",
            filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")],
            initialfile=Path(self.local_result_var.get() or RESULT_CSV_PATH).name,
        )
        if file_path:
            self.local_result_var.set(file_path)
            self._refresh_destination_ui()

    def _browse_credentials_file(self) -> None:
        file_path = filedialog.askopenfilename(
            title="Choose service account JSON",
            filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")],
        )
        if file_path:
            self.google_credentials_var.set(file_path)
            self._refresh_destination_ui()

    def _refresh_destination_ui(self) -> None:
        destination = self.destination_var.get()
        if destination == DESTINATION_GOOGLE_SHEET:
            self.local_settings_frame.grid_remove()
            self.sheet_settings_frame.grid()
            self.output_title_var.set("Google Sheet")
            target = self.google_sheet_var.get().strip() or "Waiting for spreadsheet URL or ID"
            self.result_var.set(target)
        else:
            self.sheet_settings_frame.grid_remove()
            self.local_settings_frame.grid()
            self.output_title_var.set("Local CSV")
            self.result_var.set(self.local_result_var.get().strip() or str(RESULT_CSV_PATH))

    def _center_window(self) -> None:
        self.root.update_idletasks()
        width = max(self.root.winfo_width(), self.root.winfo_reqwidth(), WINDOW_WIDTH)
        height = max(self.root.winfo_height(), self.root.winfo_reqheight(), WINDOW_HEIGHT)
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x_pos = max((screen_width - width) // 2, 0)
        y_pos = max((screen_height - height) // 2, 0)
        self.root.geometry(f"{width}x{height}+{x_pos}+{y_pos}")

    def _clear_filters(self) -> None:
        if self.is_running:
            return

        for variable in (
            self.token_var,
            self.specific_query_var,
            self.location_var,
            self.created_var,
            self.min_repos_var,
            self.max_repos_var,
            self.min_followers_var,
            self.max_followers_var,
        ):
            variable.set("")

        self.contact_mode_var.set("both")
        self.gender_var.set("all")
        self.status_var.set("Ready")
        self.progress_text_var.set("0 / 0")
        self.progress_percent_var.set("0%")
        self.progress.set(0)
        self._refresh_destination_ui()

    def _collect_filters(self) -> SearchFilters:
        return SearchFilters(
            location=self.location_var.get().strip(),
            specific_query=self.specific_query_var.get().strip(),
            created_after=self.created_var.get().strip(),
            min_repos=self.min_repos_var.get().strip(),
            max_repos=self.max_repos_var.get().strip(),
            min_followers=self.min_followers_var.get().strip(),
            max_followers=self.max_followers_var.get().strip(),
        )

    def _collect_export_settings(self) -> ExportSettings:
        return ExportSettings(
            destination=self.destination_var.get().strip(),
            local_path=self.local_result_var.get().strip(),
            spreadsheet_id_or_url=self.google_sheet_var.get().strip(),
            worksheet_name=self.google_sheet_tab_var.get().strip(),
            apps_script_url=self.google_apps_script_var.get().strip(),
            service_account_file=self.google_credentials_var.get().strip(),
        )

    def _start_scrape(self) -> None:
        if self.is_running:
            return

        filters = self._collect_filters()
        error = filters.validate()
        if error:
            messagebox.showerror("Invalid Filters", error)
            return

        export_settings = self._collect_export_settings()
        export_error = export_settings.validate()
        if export_error:
            messagebox.showerror("Invalid Save Location", export_error)
            return

        self._set_running_state(True)
        self.status_var.set("Preparing search...")
        self.progress_text_var.set("0 / 0")
        self.progress_percent_var.set("0%")
        self.progress.set(0)
        self._refresh_destination_ui()

        worker = threading.Thread(
            target=self._scrape_worker,
            args=(
                filters,
                export_settings,
                self.token_var.get().strip(),
                self.contact_mode_var.get(),
                self.gender_var.get(),
            ),
            daemon=True,
        )
        worker.start()

    def _scrape_worker(
        self,
        filters: SearchFilters,
        export_settings: ExportSettings,
        token: str,
        contact_mode: str,
        gender: str,
    ) -> None:
        try:
            details = asyncio.run(scrape_users(filters, token, self._queue_progress))
            exported_count = export_profiles(details, export_settings, contact_mode, gender)
            self.root.after(0, lambda: self._handle_success(exported_count, export_settings))
        except Exception as exc:  # noqa: BLE001
            error_message = str(exc)
            self.root.after(0, lambda: self._handle_error(error_message))

    def _queue_progress(self, current: int, total: int, message: str) -> None:
        self.root.after(0, lambda: self._update_progress(current, total, message))

    def _update_progress(self, current: int, total: int, message: str) -> None:
        maximum = total if total > 0 else 1
        percentage = current / maximum if maximum else 0
        self.progress.set(percentage)
        self.progress_text_var.set(f"{current} / {total}")
        self.progress_percent_var.set(f"{int(percentage * 100)}%")
        self.status_var.set(message)

    def _handle_success(self, exported_count: int, export_settings: ExportSettings) -> None:
        self._set_running_state(False)
        self.progress.set(1)
        self.progress_text_var.set(f"{exported_count} appended")
        self.progress_percent_var.set("100%")
        self.status_var.set("Export complete")

        if export_settings.destination == DESTINATION_GOOGLE_SHEET:
            destination_text = (
                f"{export_settings.spreadsheet_id_or_url}\n"
                f"Tab: {export_settings.worksheet_name}\n"
                f"{exported_count} profiles appended"
            )
            completion_message = (
                f"Appended {exported_count} new profiles to Google Sheet:\n"
                f"{export_settings.spreadsheet_id_or_url}\n"
                f"Tab: {export_settings.worksheet_name}"
            )
        else:
            destination_text = f"{export_settings.local_path}\n{exported_count} profiles appended"
            completion_message = f"Appended {exported_count} new profiles to:\n{export_settings.local_path}"

        self.result_var.set(destination_text)
        messagebox.showinfo("Export Complete", completion_message)

    def _handle_error(self, error_message: str) -> None:
        self._set_running_state(False)
        self.progress.set(0)
        self.progress_percent_var.set("0%")
        self.status_var.set("Export failed")
        messagebox.showerror("Export Failed", error_message)

    def _set_running_state(self, is_running: bool) -> None:
        self.is_running = is_running
        self.start_button.configure(state="disabled" if is_running else "normal")
        self.destination_segment.configure(state="disabled" if is_running else "normal")

    def run(self) -> None:
        self.root.mainloop()


def launch_app() -> None:
    GitHubScraperApp().run()
