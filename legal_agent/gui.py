from __future__ import annotations

try:
    from legal_agent_gui import run_app as run_new_gui
except ImportError:  # pragma: no cover
    run_new_gui = None

try:
    import tkinter as tk
    from tkinter import messagebox, simpledialog, ttk
except ImportError:  # pragma: no cover
    tk = None

from .authority_validation import add_authority, verify_authority
from .case_tracks import LEGAL_TRACK_CHOICES, normalize_legal_track
from .drafting import generate_outline, save_document
from .export import export_case
from .intake import (
    add_action_item,
    add_claim,
    add_evidence,
    add_fact,
    add_party,
    create_case,
    generate_timeline,
    get_case,
    list_case_ids,
)
from .db import init_db
from .jurisdiction import classify_case, get_procedural_rules


class LegalAgentGUI:
    def __init__(self, db_path: str | None = None) -> None:
        if tk is None:
            raise RuntimeError("Tkinter is not available on this system.")
        self.db_path = db_path
        init_db(db_path)
        self.root = tk.Tk()
        self.root.title("Litigation Expert AI System")
        self.root.geometry("1000x700")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        self._build_ui()
        self._refresh_cases()

    def _build_ui(self) -> None:
        main_frame = ttk.Frame(self.root, padding=12)
        main_frame.grid(sticky="NSEW")
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(0, weight=1)

        case_panel = ttk.LabelFrame(main_frame, text="Cases")
        case_panel.grid(row=0, column=0, sticky="NSWE", padx=(0, 12), pady=4)
        case_panel.columnconfigure(0, weight=1)
        self.case_listbox = tk.Listbox(case_panel, height=20, width=30)
        self.case_listbox.grid(row=0, column=0, sticky="NSWE", padx=4, pady=4)
        self.case_listbox.bind("<<ListboxSelect>>", lambda _: self._select_case())
        case_buttons = ttk.Frame(case_panel)
        case_buttons.grid(row=1, column=0, sticky="EW", padx=4, pady=4)
        ttk.Button(case_buttons, text="New Case", command=self._action_new_case).grid(row=0, column=0, sticky="EW")

        action_panel = ttk.LabelFrame(main_frame, text="Actions")
        action_panel.grid(row=0, column=1, sticky="NSEW", pady=4)
        action_panel.columnconfigure(0, weight=1)
        button_grid = [
            ("Add Party", self._action_add_party),
            ("Add Fact", self._action_add_fact),
            ("Add Claim", self._action_add_claim),
            ("Add Evidence", self._action_add_evidence),
            ("Add Action", self._action_add_action_item),
            ("Classify Jurisdiction", self._action_classify),
            ("Procedural Rules", self._action_procedural_rules),
            ("Timeline", self._action_timeline),
            ("Outline Document", self._action_outline_document),
            ("Draft Document", self._action_draft_document),
            ("Export Markdown", self._action_export_markdown),
        ]
        for idx, (label, handler) in enumerate(button_grid):
            ttk.Button(action_panel, text=label, command=handler).grid(row=idx, column=0, sticky="EW", padx=4, pady=2)

        output_panel = ttk.LabelFrame(main_frame, text="Output")
        output_panel.grid(row=1, column=0, columnspan=2, sticky="NSEW", pady=4)
        output_panel.columnconfigure(0, weight=1)
        output_panel.rowconfigure(0, weight=1)
        self.output_text = tk.Text(output_panel, wrap="word", state="disabled", height=18)
        self.output_text.grid(row=0, column=0, sticky="NSEW", padx=4, pady=4)
        scrollbar = ttk.Scrollbar(output_panel, command=self.output_text.yview)
        scrollbar.grid(row=0, column=1, sticky="NS")
        self.output_text.configure(yscrollcommand=scrollbar.set)

    def _refresh_cases(self) -> None:
        self.case_listbox.delete(0, tk.END)
        for case_id in list_case_ids(self.db_path):
            case = get_case(case_id, self.db_path)
            label = f"{case_id}: {case.get('title', 'Untitled')}"
            self.case_listbox.insert(tk.END, label)

    def _select_case(self) -> None:
        self.output_text.configure(state="normal")
        self.output_text.delete("1.0", tk.END)
        selection = self.case_listbox.curselection()
        if not selection:
            self.output_text.insert(tk.END, "No case selected.\n")
            self.output_text.configure(state="disabled")
            return
        index = selection[0]
        case_id = int(self.case_listbox.get(index).split(":", 1)[0])
        case = get_case(case_id, self.db_path)
        self.output_text.insert(tk.END, f"Selected case {case_id}: {case.get('title')}\n")
        self.output_text.insert(tk.END, f"Jurisdiction: {case.get('jurisdiction', 'Unknown')}\n")
        self.output_text.configure(state="disabled")

    def _get_selected_case_id(self) -> int | None:
        selection = self.case_listbox.curselection()
        if not selection:
            messagebox.showwarning("No Case", "Please select a case first.")
            return None
        index = selection[0]
        return int(self.case_listbox.get(index).split(":", 1)[0])

    def _action_new_case(self) -> None:
        title = simpledialog.askstring("New Case", "Case title:")
        if not title:
            return
        court_name = simpledialog.askstring("New Case", "Court name:", initialvalue="") or ""
        track_options = "\n".join(f"- {track}" for track in LEGAL_TRACK_CHOICES if track)
        track = simpledialog.askstring(
            "New Case",
            "Procedure track:\n" + track_options,
            initialvalue="",
        ) or ""
        case_id = create_case(title=title, legal_track=normalize_legal_track(track), court_name=court_name, db_path=self.db_path)
        self._refresh_cases()
        messagebox.showinfo("Case Created", f"Created case {case_id}.")

    def _action_add_party(self) -> None:
        case_id = self._get_selected_case_id()
        if case_id is None:
            return
        name = simpledialog.askstring("Add Party", "Party name:")
        if not name:
            return
        role = simpledialog.askstring("Add Party", "Role (plaintiff/defendant):", initialvalue="") or ""
        type_value = simpledialog.askstring("Add Party", "Type (individual/entity):", initialvalue="") or ""
        notes = simpledialog.askstring("Add Party", "Notes:", initialvalue="") or ""
        add_party(case_id, name, role, type_value, notes, self.db_path)
        messagebox.showinfo("Added", "Party added.")

    def _action_add_fact(self) -> None:
        case_id = self._get_selected_case_id()
        if case_id is None:
            return
        fact_text = simpledialog.askstring("Add Fact", "Fact text:")
        if not fact_text:
            return
        date = simpledialog.askstring("Add Fact", "Fact date (YYYY-MM-DD):", initialvalue="") or ""
        relevance = simpledialog.askstring("Add Fact", "Relevance:", initialvalue="") or ""
        add_fact(case_id, fact_text, date=date, relevance=relevance, db_path=self.db_path)
        messagebox.showinfo("Added", "Fact added.")

    def _action_add_claim(self) -> None:
        case_id = self._get_selected_case_id()
        if case_id is None:
            return
        claim_name = simpledialog.askstring("Add Claim", "Claim name:")
        if not claim_name:
            return
        claim_type = simpledialog.askstring("Add Claim", "Claim type:", initialvalue="") or ""
        basis = simpledialog.askstring("Add Claim", "Jurisdiction basis:", initialvalue="") or ""
        required = simpledialog.askstring("Add Claim", "Required elements as JSON list:", initialvalue='["Element1", "Element2"]') or "[]"
        add_claim(case_id, claim_name, claim_type, basis, required, db_path=self.db_path)
        messagebox.showinfo("Added", "Claim added.")

    def _action_add_evidence(self) -> None:
        case_id = self._get_selected_case_id()
        if case_id is None:
            return
        title = simpledialog.askstring("Add Evidence", "Evidence title:")
        if not title:
            return
        evidence_type = simpledialog.askstring("Add Evidence", "Evidence type:", initialvalue="") or ""
        description = simpledialog.askstring("Add Evidence", "Description:", initialvalue="") or ""
        supports = simpledialog.askstring("Add Evidence", "Supports claims list as JSON:", initialvalue='["Claim Name"]') or "[]"
        add_evidence(case_id, title, evidence_type, description, supports_claims_json=supports, db_path=self.db_path)
        messagebox.showinfo("Added", "Evidence added.")

    def _action_add_action_item(self) -> None:
        case_id = self._get_selected_case_id()
        if case_id is None:
            return
        action_text = simpledialog.askstring("Add Action", "Action text:")
        if not action_text:
            return
        category = simpledialog.askstring("Add Action", "Category:", initialvalue="") or ""
        due_date = simpledialog.askstring("Add Action", "Due date (YYYY-MM-DD):", initialvalue="") or ""
        add_action_item(case_id, action_text, category, due_date, db_path=self.db_path)
        messagebox.showinfo("Added", "Action item added.")

    def _action_classify(self) -> None:
        case_id = self._get_selected_case_id()
        if case_id is None:
            return
        result = classify_case(case_id, self.db_path)
        self._display_result(result)
        self._refresh_cases()

    def _action_procedural_rules(self) -> None:
        case_id = self._get_selected_case_id()
        if case_id is None:
            return
        result = get_procedural_rules(case_id, self.db_path)
        self._display_result(result)

    def _action_timeline(self) -> None:
        case_id = self._get_selected_case_id()
        if case_id is None:
            return
        timeline = generate_timeline(case_id, self.db_path)
        self._display_result({"timeline": timeline})

    def _action_outline_document(self) -> None:
        case_id = self._get_selected_case_id()
        if case_id is None:
            return
        doc_type = simpledialog.askstring("Outline Document", "Document type:", initialvalue="complaint") or "complaint"
        outline = generate_outline(case_id, doc_type, self.db_path)
        self._display_result(outline)

    def _action_draft_document(self) -> None:
        case_id = self._get_selected_case_id()
        if case_id is None:
            return
        doc_type = simpledialog.askstring("Draft Document", "Document type:", initialvalue="complaint") or "complaint"
        draft = save_document(case_id, doc_type, self.db_path)
        self._display_result(draft)

    def _action_export_markdown(self) -> None:
        case_id = self._get_selected_case_id()
        if case_id is None:
            return
        export_path = simpledialog.askstring("Export Markdown", "Export file path:", initialvalue="export.md") or "export.md"
        export_case(case_id, "markdown", output_path=export_path, db_path=self.db_path)
        messagebox.showinfo("Export", f"Markdown exported to {export_path}")

    def _display_result(self, data: object) -> None:
        self.output_text.configure(state="normal")
        self.output_text.delete("1.0", tk.END)
        self.output_text.insert(tk.END, f"{data}\n")
        self.output_text.configure(state="disabled")

    def run(self) -> None:
        self.root.mainloop()


def run_gui(db_path: str | None = None) -> None:
    if run_new_gui is not None:
        run_new_gui(db_path)
        return
    if tk is None:
        raise RuntimeError("A GUI backend is required but unavailable.")
    app = LegalAgentGUI(db_path)
    app.run()


def main() -> None:
    run_gui()


if __name__ == "__main__":
    main()
