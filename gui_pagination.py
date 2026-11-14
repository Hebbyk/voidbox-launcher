"""
gui_pagination.py - one-time script. Run from C:\\MCLauncher:   py gui_pagination.py
Run search_pagination.py FIRST - this script's search results now use search.py's
new offset parameter, and search.py must already support it.

Two small UI changes:
  1. AddInstanceDialog's "Minecraft version" free-text box becomes a dropdown, filled
     from Mojang's real release list (same version_change.release_versions() call
     ChangeVersionDialog already uses), loaded in the background so opening the dialog
     doesn't block on a network request. Falls back to a plain typed box if the list
     can't be fetched, so creating an instance still isn't blocked by it.
  2. Search results (both modpacks and mods) add a "Load more" button at the bottom
     that fetches the next page and appends it, instead of only ever showing the
     first ~10-20. Pressing it again keeps going; it's removed once a page comes
     back empty.

Only gui.py is touched. Nothing is changed unless every edit matches exactly.
Backup: gui.py.bak. LF and CRLF both fine.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------
# 1. Minecraft version dropdown in AddInstanceDialog
# ---------------------------------------------------------------------------

OLD_ADDINST_INIT = '''        ctk.CTkLabel(self, text=tr("Minecraft version (e.g. 1.20.1):")).pack(pady=(10, 0))
        self.mc_entry = ctk.CTkEntry(self, width=300)
        self.mc_entry.pack(pady=5)
'''
NEW_ADDINST_INIT = '''        ctk.CTkLabel(self, text=tr("Minecraft version:")).pack(pady=(10, 0))
        self.mc_entry = ctk.CTkComboBox(self, width=300, values=[tr("Loading versions...")], state="disabled")
        self.mc_entry.pack(pady=5)

        def load_versions():
            import version_change
            try:
                versions = version_change.release_versions()
            except Exception:
                versions = []
            self.app.run_on_main_thread(lambda: self._versions_loaded(versions))
        threading.Thread(target=load_versions, daemon=True).start()
'''

OLD_ADDINST_CREATE_BLANK = '''    def create_blank(self):
        name, mc = self.name_entry.get().strip(), self.mc_entry.get().strip()
'''
NEW_ADDINST_CREATE_BLANK = '''    def _versions_loaded(self, versions):
        if getattr(self, "_closed", False) or not self.mc_entry.winfo_exists():
            return
        if not versions:
            # Couldn't reach Mojang - fall back to free typing rather than blocking creation.
            self.mc_entry.configure(values=[], state="normal")
            self.mc_entry.set("")
            return
        self.mc_entry.configure(values=versions, state="readonly")
        self.mc_entry.set(versions[0])

    def create_blank(self):
        name, mc = self.name_entry.get().strip(), self.mc_entry.get().strip()
'''

# ---------------------------------------------------------------------------
# 2. "Load more" pagination for search results
# ---------------------------------------------------------------------------

# lazy_imports.py (if already applied) moves "import search" to be the first line inside
# do_search, since that's where search.search_all()/search_all_mods() used to be called. In
# the new version those calls move to _fetch_search_page, so that's where the import needs to
# end up - try the shape with the local import first, then the plain one.
OLD_DO_SEARCH_WITH_IMPORT = '''    def do_search(self):
        import search
        query = self.search_entry.get().strip()
        if not query:
            return
        api_key = settings.get_curseforge_api_key()
        adding_to = self.add_target_instance

        for widget in self.results_frame.winfo_children():
            widget.destroy()
        self._start_progress(tr("Searching for '{0}'...", query))

        def worker():
            try:
                if adding_to:
                    results = search.search_all_mods(query, curseforge_api_key=api_key)
                else:
                    results = search.search_all(query, curseforge_api_key=api_key)
                self.run_on_main_thread(lambda: self._show_search_results(results))
            except Exception as e:
                msg = str(e)
                self.run_on_main_thread(lambda: messagebox.showerror(tr("Search failed"), msg))
            finally:
                self.run_on_main_thread(self._stop_progress)

        threading.Thread(target=worker, daemon=True).start()
'''
NEW_DO_SEARCH_WITH_IMPORT = '''    SEARCH_PAGE_SIZE = 10  # matches search.search_all()'s/search_all_mods()'s own default "limit"

    def do_search(self):
        query = self.search_entry.get().strip()
        if not query:
            return
        self._search_query = query
        self._search_offset = 0
        for widget in self.results_frame.winfo_children():
            widget.destroy()
        self._current_results = []
        self._fetch_search_page(reset=True)

    def _fetch_search_page(self, reset: bool):
        """reset=True: a brand new search, replaces whatever was shown.
        reset=False: the "Load more" button was pressed, appends the next page."""
        import search
        query, offset = self._search_query, self._search_offset
        api_key = settings.get_curseforge_api_key()
        adding_to = self.add_target_instance
        if reset:
            self._start_progress(tr("Searching for '{0}'...", query))

        def worker():
            try:
                if adding_to:
                    results = search.search_all_mods(query, curseforge_api_key=api_key, offset=offset)
                else:
                    results = search.search_all(query, curseforge_api_key=api_key, offset=offset)
                self.run_on_main_thread(lambda: self._show_search_results(results, reset))
            except Exception as e:
                msg = str(e)
                self.run_on_main_thread(lambda: messagebox.showerror(tr("Search failed"), msg))
            finally:
                if reset:
                    self.run_on_main_thread(self._stop_progress)

        threading.Thread(target=worker, daemon=True).start()

    def _do_load_more(self):
        if getattr(self, "_load_more_btn", None) is not None and self._load_more_btn.winfo_exists():
            self._load_more_btn.configure(text=tr("Loading..."), state="disabled")
        self._fetch_search_page(reset=False)
'''

OLD_DO_SEARCH_NO_IMPORT = '''    def do_search(self):
        query = self.search_entry.get().strip()
        if not query:
            return
        api_key = settings.get_curseforge_api_key()
        adding_to = self.add_target_instance

        for widget in self.results_frame.winfo_children():
            widget.destroy()
        self._start_progress(tr("Searching for '{0}'...", query))

        def worker():
            try:
                if adding_to:
                    results = search.search_all_mods(query, curseforge_api_key=api_key)
                else:
                    results = search.search_all(query, curseforge_api_key=api_key)
                self.run_on_main_thread(lambda: self._show_search_results(results))
            except Exception as e:
                msg = str(e)
                self.run_on_main_thread(lambda: messagebox.showerror(tr("Search failed"), msg))
            finally:
                self.run_on_main_thread(self._stop_progress)

        threading.Thread(target=worker, daemon=True).start()
'''
NEW_DO_SEARCH_NO_IMPORT = '''    SEARCH_PAGE_SIZE = 10  # matches search.search_all()'s/search_all_mods()'s own default "limit"

    def do_search(self):
        query = self.search_entry.get().strip()
        if not query:
            return
        self._search_query = query
        self._search_offset = 0
        for widget in self.results_frame.winfo_children():
            widget.destroy()
        self._current_results = []
        self._fetch_search_page(reset=True)

    def _fetch_search_page(self, reset: bool):
        """reset=True: a brand new search, replaces whatever was shown.
        reset=False: the "Load more" button was pressed, appends the next page."""
        query, offset = self._search_query, self._search_offset
        api_key = settings.get_curseforge_api_key()
        adding_to = self.add_target_instance
        if reset:
            self._start_progress(tr("Searching for '{0}'...", query))

        def worker():
            try:
                if adding_to:
                    results = search.search_all_mods(query, curseforge_api_key=api_key, offset=offset)
                else:
                    results = search.search_all(query, curseforge_api_key=api_key, offset=offset)
                self.run_on_main_thread(lambda: self._show_search_results(results, reset))
            except Exception as e:
                msg = str(e)
                self.run_on_main_thread(lambda: messagebox.showerror(tr("Search failed"), msg))
            finally:
                if reset:
                    self.run_on_main_thread(self._stop_progress)

        threading.Thread(target=worker, daemon=True).start()

    def _do_load_more(self):
        if getattr(self, "_load_more_btn", None) is not None and self._load_more_btn.winfo_exists():
            self._load_more_btn.configure(text=tr("Loading..."), state="disabled")
        self._fetch_search_page(reset=False)
'''

OLD_SHOW_RESULTS = '''    def _show_search_results(self, results: list[dict]):
        self._current_results = results
        for widget in self.results_frame.winfo_children():
            widget.destroy()
        if not results:
            ctk.CTkLabel(self.results_frame, text=tr("No results.")).pack(pady=20)
            return
        for r in results:
            self._add_result_row(r)
'''
NEW_SHOW_RESULTS = '''    def _show_search_results(self, results: list[dict], reset: bool = True):
        if reset:
            for widget in self.results_frame.winfo_children():
                widget.destroy()
            self._load_more_btn = None
            self._current_results = []
            if not results:
                ctk.CTkLabel(self.results_frame, text=tr("No results.")).pack(pady=20)
                return
        else:
            if getattr(self, "_load_more_btn", None) is not None and self._load_more_btn.winfo_exists():
                self._load_more_btn.destroy()
            self._load_more_btn = None
            if not results:
                ctk.CTkLabel(self.results_frame, text=tr("No more results."),
                              text_color=COLOR_TEXT_MUTED).pack(pady=10)
                return
        self._current_results += results
        for r in results:
            self._add_result_row(r)
        self._search_offset += self.SEARCH_PAGE_SIZE
        self._load_more_btn = ctk.CTkButton(self.results_frame, text=tr("Load more"),
                                             command=self._do_load_more,
                                             fg_color=COLOR_BUTTON_SECONDARY,
                                             hover_color=COLOR_BUTTON_SECONDARY_HOVER)
        self._load_more_btn.pack(pady=12)
'''


def apply_edits(text, edits):
    problems = []
    for old, _new in edits:
        if text.count(old) != 1:
            problems.append(f"found {text.count(old)} match(es), expected 1, for:\n    {old.strip().splitlines()[0]}")
    if problems:
        return None, problems
    for old, new in edits:
        text = text.replace(old, new, 1)
    return text, []


def main():
    p = os.path.join(HERE, "gui.py")
    if not os.path.exists(p):
        print("NOTHING CHANGED. gui.py not found."); sys.exit(1)
    with open(p, "rb") as f:
        raw = f.read()
    crlf = b"\r\n" in raw
    text = raw.decode("utf-8").replace("\r\n", "\n")

    with_import = text.count(OLD_DO_SEARCH_WITH_IMPORT)
    no_import = text.count(OLD_DO_SEARCH_NO_IMPORT)
    do_search_problems = []
    if with_import == 1 and no_import == 0:
        do_search_edit = (OLD_DO_SEARCH_WITH_IMPORT, NEW_DO_SEARCH_WITH_IMPORT)
    elif no_import == 1 and with_import == 0:
        do_search_edit = (OLD_DO_SEARCH_NO_IMPORT, NEW_DO_SEARCH_NO_IMPORT)
    else:
        do_search_edit = None
        do_search_problems.append(
            f"do_search block: found {with_import} match(es) with a local 'import search' and "
            f"{no_import} without; expected exactly one of the two to be 1")

    edits = [
        (OLD_ADDINST_INIT, NEW_ADDINST_INIT),
        (OLD_ADDINST_CREATE_BLANK, NEW_ADDINST_CREATE_BLANK),
        (OLD_SHOW_RESULTS, NEW_SHOW_RESULTS),
    ]
    if do_search_edit:
        edits.append(do_search_edit)
    new_text, problems = apply_edits(text, edits)
    problems += do_search_problems
    if problems:
        print("NOTHING CHANGED. Problems:")
        for pr in problems:
            print("  -", pr)
        sys.exit(1)

    with open(p + ".bak", "wb") as f:
        f.write(raw)
    out = new_text.replace("\n", "\r\n") if crlf else new_text
    with open(p, "wb") as f:
        f.write(out.encode("utf-8"))
    print("patched gui.py: version dropdown + Load more pagination")
    print("\nDone. Next: py -m py_compile gui.py   then open Add Instance and Browse to check both.")


if __name__ == "__main__":
    main()
