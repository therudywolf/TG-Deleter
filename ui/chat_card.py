"""Reusable chat card widget for displaying Place items."""
import customtkinter as ctk
from core import Place
from ui.theme import PAD, PAD_SM, RADIUS, CARD_BG, font


class ChatCard(ctk.CTkFrame):
    """A clickable card representing a chat/dialog with checkbox."""

    def __init__(
        self,
        parent,
        place: Place,
        *,
        selected: bool = False,
        compact: bool = False,
        on_check=None,
        on_click=None,
        on_double_click=None,
        **kw,
    ):
        super().__init__(parent, corner_radius=0 if compact else RADIUS, fg_color=CARD_BG, cursor="hand2", **kw)
        self.place = place
        self.on_click_cb = on_click
        self._check_var = ctk.BooleanVar(value=selected)

        if compact:
            self.configure(height=38)
            self.pack_propagate(False)

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="both" if compact else "x", expand=compact, padx=PAD_SM if compact else PAD, pady=PAD_SM if not compact else 0)

        cb = ctk.CTkCheckBox(
            row, text="", variable=self._check_var, width=24, height=24,
            command=lambda: on_check(place.chat_id, self._check_var.get()) if on_check else None,
        )
        cb.pack(side="left", padx=(0, PAD_SM))

        max_title_len = 72 if compact else 50
        title = place.title or ""
        title_short = (title[:max_title_len] + "\u2026") if len(title) > max_title_len else title

        if compact:
            ctk.CTkLabel(row, text=title_short, anchor="w", font=font(13)).pack(side="left", fill="x", expand=True)
            from ui.theme import TEXT_MUTED
            ctk.CTkLabel(row, text=place.type_str, width=130, anchor="w", font=font(12), text_color=TEXT_MUTED).pack(side="right")
        else:
            text_col = ctk.CTkFrame(row, fg_color="transparent")
            text_col.pack(side="left", fill="x", expand=True)
            label_text = f"{title_short}  \u00b7  {place.type_str}  \u00b7  {len(place.messages)} \u0441\u043e\u043e\u0431\u0449."
            lbl = ctk.CTkLabel(text_col, text=label_text, anchor="w", font=font(14, "bold"))
            lbl.pack(fill="x", anchor="w")
            if place.messages:
                mid, preview, date_str = place.messages[0]
                preview = (preview or "").replace("\n", " ")
                preview_short = preview[:90] + "\u2026" if len(preview) > 90 else preview
                sub = ctk.CTkLabel(
                    text_col, text=f"{date_str} \u00b7 #{mid} \u00b7 {preview_short}",
                    anchor="w", font=font(12), text_color="gray", wraplength=560,
                )
                sub.pack(fill="x", anchor="w", pady=(2, 0))
            if on_double_click:
                lbl.bind("<Double-1>", lambda e: on_double_click(place))
                text_col.bind("<Button-1>", lambda e: self._emit_click(e))

        if on_double_click:
            self.bind("<Double-1>", lambda e: on_double_click(place))
        if on_click:
            self.bind("<Button-1>", lambda e: self._emit_click(e))
            row.bind("<Button-1>", lambda e: self._emit_click(e))

    def _emit_click(self, event):
        if self.on_click_cb:
            self.on_click_cb(self)

    @property
    def is_checked(self) -> bool:
        return self._check_var.get()

    def set_checked(self, value: bool):
        self._check_var.set(value)
