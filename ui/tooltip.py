"""
Простой всплывающий tooltip по наведению мыши (Enter/Leave).
"""
import customtkinter as ctk


def bind_tooltip(widget, text: str, delay_ms: int = 500):
    """Показать подсказку text при наведении на widget. delay_ms — задержка перед показом."""
    if not text:
        return
    job = [None]
    tw = [None]

    def show():
        if tw[0] is not None:
            return
        root = widget.winfo_toplevel()
        tw[0] = ctk.CTkToplevel(root)
        tw[0].withdraw()
        tw[0].overrideredirect(True)
        tw[0].attributes("-topmost", True)
        lbl = ctk.CTkLabel(tw[0], text=text, font=ctk.CTkFont(size=12), fg_color=("gray20", "gray85"), corner_radius=6, padx=8, pady=6, wraplength=280)
        lbl.pack()
        tw[0].update_idletasks()
        w, h = tw[0].winfo_reqwidth(), tw[0].winfo_reqheight()
        x = root.winfo_pointerx() + 14
        y = root.winfo_pointery() + 14
        tw[0].geometry("+%d+%d" % (x, y))
        tw[0].deiconify()

    def hide():
        if job[0] is not None:
            widget.after_cancel(job[0])
            job[0] = None
        if tw[0] is not None:
            try:
                tw[0].destroy()
            except Exception:
                pass
            tw[0] = None

    def on_enter(e):
        job[0] = widget.after(delay_ms, show)

    def on_leave(e):
        hide()

    widget.bind("<Enter>", on_enter)
    widget.bind("<Leave>", on_leave)
