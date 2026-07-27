import re
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

import sqlglot
from sqlglot.dialects import Dialects

from lib.sql_parser import describe

GENERIC_DIALECT = "generic (default)"

# sqlglot underlines the offending token in ParseError messages with ANSI codes,
# which a Tk text widget renders as literal escape sequences.
ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")

SAMPLE_QUERY = """SELECT Customers.CustomerName, Orders.OrderID
FROM Customers
LEFT JOIN Orders
  ON Customers.CustomerID = Orders.CustomerID
ORDER BY Customers.CustomerName;"""

# --- palette -----------------------------------------------------------------

BG = "#0f1117"          # window background
SURFACE = "#171a23"     # panel background
SURFACE_ALT = "#1e222e"  # inputs, chips
BORDER = "#272c3a"
TEXT = "#e6e8ef"
MUTED = "#8b93a7"
ACCENT = "#6d5cff"
ACCENT_HOVER = "#8274ff"
SUCCESS = "#3ddc97"
ERROR = "#ff5c7a"
SELECTION = "#2f3550"

# syntax colours for the query editor
SYNTAX = {
    "keyword": "#c792ea",
    "function": "#5ccfe6",
    "string": "#a5e075",
    "number": "#ffb86c",
    "comment": "#5c6478",
}

KEYWORDS = {
    "ALL", "AND", "ANY", "AS", "ASC", "BETWEEN", "BY", "CASE", "CAST", "CROSS",
    "DESC", "DISTINCT", "ELSE", "END", "EXCEPT", "EXISTS", "FALSE", "FROM",
    "FULL", "GROUP", "HAVING", "IN", "INNER", "INTERSECT", "IS", "JOIN",
    "LEFT", "LIKE", "LIMIT", "NOT", "NULL", "OFFSET", "ON", "OR", "ORDER",
    "OUTER", "OVER", "PARTITION", "RIGHT", "SELECT", "THEN", "TRUE", "UNION",
    "USING", "WHEN", "WHERE", "WITH",
}

TOKEN_RE = re.compile(
    r"""(?P<comment>--[^\n]*|/\*.*?\*/)
      | (?P<string>'(?:[^']|'')*'|"(?:[^"]|"")*"|`[^`]*`)
      | (?P<number>\b\d+(?:\.\d+)?\b)
      | (?P<function>\b[A-Za-z_]\w*(?=\s*\())
      | (?P<word>\b[A-Za-z_]\w*\b)""",
    re.VERBOSE | re.DOTALL,
)


def pick_font(candidates, fallback):
    available = set(tkfont.families())
    for name in candidates:
        if name in available:
            return name
    return fallback


def enable_dark_titlebar(root):
    """Ask Windows for a dark window frame so the title bar matches the app."""
    try:
        import ctypes

        root.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, 20, ctypes.byref(ctypes.c_int(1)), ctypes.sizeof(ctypes.c_int)
        )
    except Exception:
        pass  # non-Windows, or an older build without the attribute


class RoundedButton(tk.Canvas):
    """A flat, rounded button. Tk's own buttons can't do rounded corners."""

    def __init__(self, parent, text, command, font, *, fill, hover, fg,
                 outline=None, padx=20, height=38, radius=12):
        measure = tkfont.Font(font=font)
        width = measure.measure(text) + padx * 2
        super().__init__(
            parent, width=width, height=height, bg=parent["bg"],
            highlightthickness=0, bd=0, cursor="hand2",
        )
        self.command = command
        self.fill = fill
        self.hover = hover

        self.shape = self._round_rect(
            1, 1, width - 1, height - 1, radius,
            fill=fill, outline=outline or fill,
        )
        self.create_text(width // 2, height // 2 + 1, text=text, fill=fg, font=font)

        self.bind("<Enter>", lambda _: self.itemconfigure(self.shape, fill=self.hover))
        self.bind("<Leave>", lambda _: self.itemconfigure(self.shape, fill=self.fill))
        self.bind("<ButtonRelease-1>", self._click)

    def _round_rect(self, x1, y1, x2, y2, r, **kwargs):
        points = [
            x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
            x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
            x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
        ]
        return self.create_polygon(points, smooth=True, **kwargs)

    def _click(self, event):
        if 0 <= event.x <= self.winfo_width() and 0 <= event.y <= self.winfo_height():
            self.command()


class SqlToNlApp:
    def __init__(self, root):
        self.root = root
        root.title("SQL → Natural Language")
        root.geometry("880x720")
        root.minsize(620, 560)
        root.configure(bg=BG)
        enable_dark_titlebar(root)

        ui = pick_font(["Segoe UI Variable Text", "Segoe UI"], "TkDefaultFont")
        mono = pick_font(
            ["Cascadia Code", "Cascadia Mono", "JetBrains Mono", "Consolas"],
            "TkFixedFont",
        )
        self.font_title = (ui, 19, "bold")
        self.font_body = (ui, 10)
        self.font_label = (ui, 9, "bold")
        self.font_button = (ui, 10, "bold")
        self.font_code = (mono, 11)
        self.font_result = (ui, 12)

        self._init_styles()

        page = tk.Frame(root, bg=BG, padx=26, pady=22)
        page.pack(fill="both", expand=True)
        page.columnconfigure(0, weight=1)
        page.rowconfigure(3, weight=3)
        page.rowconfigure(6, weight=2)

        self._build_header(page, row=0)
        self._build_toolbar(page, row=1)

        self._section(page, "SQL QUERY", row=2)
        editor, self.input, _ = self._text_panel(page, height=11, code=True)
        editor.grid(row=3, column=0, sticky="nsew", pady=(0, 14))
        self.input.insert("1.0", SAMPLE_QUERY)
        self.input.bind("<KeyRelease>", self.highlight)
        self.input.bind("<<Paste>>", lambda e: self.after(1, self.highlight))
        self.highlight()

        self._build_buttons(page, row=4)

        self._section(page, "DESCRIPTION", row=5)
        result, self.output, self.stripe = self._text_panel(
            page, height=5, stripe=True
        )
        result.grid(row=6, column=0, sticky="nsew", pady=(0, 14))
        self.output.configure(state="disabled")
        self.output.tag_configure("ok", foreground=TEXT)
        self.output.tag_configure("error", foreground=ERROR)

        self._build_status(page, row=7)

        root.bind("<Control-Return>", self.on_describe)
        self.input.focus_set()

    # -- chrome ---------------------------------------------------------------

    def _init_styles(self):
        style = ttk.Style()
        style.theme_use("clam")  # the only built-in theme that honours colours

        style.configure(
            "Dark.TCombobox",
            fieldbackground=SURFACE_ALT, background=SURFACE_ALT, foreground=TEXT,
            selectbackground=SURFACE_ALT, selectforeground=TEXT,
            arrowcolor=MUTED, bordercolor=BORDER,
            lightcolor=SURFACE_ALT, darkcolor=SURFACE_ALT,
            borderwidth=0, padding=(10, 7),
        )
        style.map(
            "Dark.TCombobox",
            fieldbackground=[("readonly", SURFACE_ALT)],
            foreground=[("readonly", TEXT)],
            arrowcolor=[("active", ACCENT)],
            bordercolor=[("focus", ACCENT), ("hover", ACCENT)],
        )
        for option, value in (
            ("background", SURFACE_ALT), ("foreground", TEXT),
            ("selectBackground", ACCENT), ("selectForeground", "#ffffff"),
            ("borderWidth", 0), ("relief", "flat"),
        ):
            self.root.option_add(f"*TCombobox*Listbox.{option}", value)

        style.configure(
            "Slim.Vertical.TScrollbar",
            troughcolor=SURFACE, background=BORDER, bordercolor=SURFACE,
            lightcolor=BORDER, darkcolor=BORDER, arrowcolor=SURFACE,
            borderwidth=0, arrowsize=1, width=9,
        )
        style.map("Slim.Vertical.TScrollbar", background=[("active", MUTED)])

    def _build_header(self, parent, row):
        header = tk.Frame(parent, bg=BG)
        header.grid(row=row, column=0, sticky="ew", pady=(0, 18))

        bar = tk.Frame(header, bg=ACCENT, width=4, height=46)
        bar.pack(side="left", fill="y", padx=(0, 14))
        bar.pack_propagate(False)

        titles = tk.Frame(header, bg=BG)
        titles.pack(side="left", anchor="w")
        tk.Label(
            titles, text="SQL → Natural Language",
            bg=BG, fg=TEXT, font=self.font_title,
        ).pack(anchor="w")
        tk.Label(
            titles, text="Read any query back as plain English",
            bg=BG, fg=MUTED, font=self.font_body,
        ).pack(anchor="w", pady=(2, 0))

    def _build_toolbar(self, parent, row):
        bar = tk.Frame(parent, bg=BG)
        bar.grid(row=row, column=0, sticky="ew", pady=(0, 16))
        tk.Label(
            bar, text="Dialect", bg=BG, fg=MUTED, font=self.font_label,
        ).pack(side="left", padx=(0, 10))
        self.dialect = ttk.Combobox(
            bar, state="readonly", width=22, style="Dark.TCombobox",
            font=self.font_body,
            values=[GENERIC_DIALECT] + sorted(d.value for d in Dialects if d.value),
        )
        self.dialect.current(0)
        self.dialect.pack(side="left")

    def _section(self, parent, text, row):
        tk.Label(
            parent, text=text, bg=BG, fg=MUTED, font=self.font_label,
        ).grid(row=row, column=0, sticky="w", pady=(0, 7))

    def _text_panel(self, parent, height, code=False, stripe=False):
        """A bordered dark panel wrapping a Text widget and a slim scrollbar."""
        border = tk.Frame(parent, bg=BORDER)
        inner = tk.Frame(border, bg=SURFACE)
        inner.pack(fill="both", expand=True, padx=1, pady=1)

        accent = None
        if stripe:
            accent = tk.Frame(inner, bg=ACCENT, width=3)
            accent.pack(side="left", fill="y")

        text = tk.Text(
            inner, height=height, wrap="word", bd=0, highlightthickness=0,
            bg=SURFACE, fg=TEXT, insertbackground=ACCENT, insertwidth=2,
            selectbackground=SELECTION, selectforeground=TEXT,
            padx=16, pady=13, spacing1=1, spacing3=4,
            font=self.font_code if code else self.font_result,
            undo=code,
        )
        scroll = ttk.Scrollbar(
            inner, orient="vertical", command=text.yview,
            style="Slim.Vertical.TScrollbar",
        )
        text.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y", padx=(0, 3), pady=3)
        text.pack(side="left", fill="both", expand=True)

        if code:
            for name, colour in SYNTAX.items():
                text.tag_configure(name, foreground=colour)

        return border, text, accent

    def _build_buttons(self, parent, row):
        bar = tk.Frame(parent, bg=BG)
        bar.grid(row=row, column=0, sticky="ew", pady=(0, 18))

        RoundedButton(
            bar, "Describe   ⌃↵", self.on_describe, self.font_button,
            fill=ACCENT, hover=ACCENT_HOVER, fg="#ffffff",
        ).pack(side="left")
        RoundedButton(
            bar, "Clear", self.on_clear, self.font_button,
            fill=SURFACE_ALT, hover=BORDER, fg=TEXT, outline=BORDER,
        ).pack(side="left", padx=(10, 0))
        RoundedButton(
            bar, "Copy", self.on_copy, self.font_button,
            fill=SURFACE_ALT, hover=BORDER, fg=TEXT, outline=BORDER,
        ).pack(side="left", padx=(10, 0))

    def _build_status(self, parent, row):
        bar = tk.Frame(parent, bg=BG)
        bar.grid(row=row, column=0, sticky="ew")
        self.dot = tk.Label(bar, text="●", bg=BG, fg=BORDER, font=(None, 9))
        self.dot.pack(side="left", padx=(0, 7))
        self.status = tk.Label(bar, text="Ready", bg=BG, fg=MUTED, font=self.font_body)
        self.status.pack(side="left")

    # -- behaviour ------------------------------------------------------------

    def after(self, ms, func):
        return self.root.after(ms, func)

    def highlight(self, event=None):
        """Recolour the query editor. Cheap enough to run on every keystroke."""
        for tag in SYNTAX:
            self.input.tag_remove(tag, "1.0", "end")

        content = self.input.get("1.0", "end-1c")
        for match in TOKEN_RE.finditer(content):
            kind = match.lastgroup
            if kind == "word":
                if match.group().upper() not in KEYWORDS:
                    continue
                kind = "keyword"
            self.input.tag_add(
                kind, f"1.0+{match.start()}c", f"1.0+{match.end()}c"
            )

    def set_status(self, message, colour=MUTED, dot=None):
        self.status.configure(text=message, fg=colour)
        self.dot.configure(fg=dot or colour)

    def selected_dialect(self):
        value = self.dialect.get()
        return None if value == GENERIC_DIALECT else value

    def show(self, text, error=False):
        self.output.configure(state="normal")
        self.output.delete("1.0", "end")
        self.output.insert("1.0", text, "error" if error else "ok")
        self.output.configure(state="disabled")
        if self.stripe is not None:
            self.stripe.configure(bg=ERROR if error else ACCENT)

    def on_describe(self, event=None):
        sql = self.input.get("1.0", "end").strip()
        if not sql:
            self.show("")
            self.set_status("Enter a query first.", MUTED)
            return "break"

        # The parser assumes a well-formed SELECT with a FROM clause, so anything
        # else surfaces here as a raw exception rather than being handled upstream.
        try:
            tree = sqlglot.parse_one(sql, dialect=self.selected_dialect())
            description = describe(tree)
        except Exception as exc:
            self.show(ANSI_ESCAPE.sub("", f"{type(exc).__name__}: {exc}"), error=True)
            self.set_status("Could not describe this query.", ERROR)
            return "break"

        self.show(description)
        self.set_status("Described.", SUCCESS)
        return "break"

    def on_clear(self):
        self.input.delete("1.0", "end")
        self.show("")
        self.set_status("Ready", MUTED, dot=BORDER)
        self.input.focus_set()

    def on_copy(self):
        text = self.output.get("1.0", "end").strip()
        if not text:
            self.set_status("Nothing to copy yet.", MUTED)
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.set_status("Description copied to clipboard.", SUCCESS)


def main():
    root = tk.Tk()
    SqlToNlApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
