"""
Экран «Сообщения в чате»: заголовок, Назад, список сообщений с чекбоксами, действия удаления и экспорт.
"""
from datetime import datetime
from typing import Optional
import customtkinter as ctk
from tkinter import messagebox, filedialog

from core import Place
from ui.theme import (
    PAD,
    PAD_SM,
    RADIUS,
    BTN_RADIUS,
    ACCENT,
    ACCENT_HOVER,
    DANGER,
    DANGER_HOVER,
    SCROLL_FRAME_BG,
    ROW_BG,
    BTN_SECONDARY_DANGER,
    font,
)
from ui.queues import request_queue, scan_paused, scan_stop_requested
from ui.cache_export import export_messages_to_csv, export_messages_to_json
from ui.tooltip import bind_tooltip


class PostsFrame(ctk.CTkFrame):
    """Экран 2: Название чата, Назад, список сообщений с чекбоксами, кнопки удаления с подсказками."""

    def __init__(self, parent, on_back, all_places_getter, **kw):
        super().__init__(parent, fg_color="transparent", **kw)
        self.on_back = on_back
        self.all_places_getter = all_places_getter
        self.current_place: Optional[Place] = None
        self.check_vars = []
        self._search_job = None

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", pady=(0, PAD))
        self.title_label = ctk.CTkLabel(top, text="", font=font(18, "bold"))
        self.title_label.pack(side="left")
        ctk.CTkButton(top, text="Назад", command=on_back, corner_radius=BTN_RADIUS, width=80, fg_color=ACCENT, hover_color=ACCENT_HOVER).pack(side="right", padx=PAD_SM)

        # Блок поиска и фильтра по дате
        filter_block = ctk.CTkFrame(self, fg_color=("gray92", "gray18"), corner_radius=RADIUS, border_width=1, border_color=("gray85", "gray25"))
        filter_block.pack(fill="x", pady=(0, PAD_SM))
        filter_inner = ctk.CTkFrame(filter_block, fg_color="transparent")
        filter_inner.pack(fill="x", padx=PAD, pady=PAD_SM)
        ctk.CTkLabel(filter_inner, text="Поиск и фильтр по дате", font=font(12, "bold"), text_color="gray").pack(anchor="w")
        search_row = ctk.CTkFrame(filter_inner, fg_color="transparent")
        search_row.pack(fill="x", pady=(PAD_SM, 0))
        ctk.CTkLabel(search_row, text="Поиск по тексту:").pack(side="left", padx=(0, PAD_SM))
        self.posts_search_var = ctk.StringVar()
        self.posts_search_var.trace_add("write", lambda *a: self._schedule_search())
        ctk.CTkEntry(search_row, placeholder_text="Подстрока в превью сообщения...", textvariable=self.posts_search_var, width=300).pack(side="left")
        date_row = ctk.CTkFrame(filter_inner, fg_color="transparent")
        date_row.pack(fill="x", pady=(PAD_SM, 0))
        ctk.CTkLabel(date_row, text="Удалять только за период:").pack(side="left", padx=(0, PAD_SM))
        self.date_from_var = ctk.StringVar()
        self.date_to_var = ctk.StringVar()
        ctk.CTkEntry(date_row, placeholder_text="От (YYYY-MM-DD)", textvariable=self.date_from_var, width=120).pack(side="left", padx=PAD_SM)
        ctk.CTkEntry(date_row, placeholder_text="До (YYYY-MM-DD)", textvariable=self.date_to_var, width=120).pack(side="left", padx=PAD_SM)

        self.scroll = ctk.CTkScrollableFrame(self, fg_color=SCROLL_FRAME_BG, corner_radius=RADIUS)
        self.scroll.pack(fill="both", expand=True, pady=(0, PAD))

        # Блок «Действия с сообщениями»
        actions_block = ctk.CTkFrame(self, fg_color=("gray92", "gray18"), corner_radius=RADIUS, border_width=1, border_color=("gray85", "gray25"))
        actions_block.pack(fill="x", pady=(0, PAD_SM))
        actions_inner = ctk.CTkFrame(actions_block, fg_color="transparent")
        actions_inner.pack(fill="x", padx=PAD, pady=PAD_SM)
        ctk.CTkLabel(actions_inner, text="Действия с сообщениями", font=font(12, "bold"), text_color="gray").pack(anchor="w")

        actions_grid = ctk.CTkFrame(actions_inner, fg_color="transparent")
        actions_grid.pack(fill="x", pady=(PAD_SM, 0))

        btn_delete_selected = ctk.CTkButton(
            actions_grid, text="Удалить выбранные", command=self._delete_selected,
            corner_radius=BTN_RADIUS, fg_color=DANGER, hover_color=DANGER_HOVER,
        )
        btn_delete_selected.grid(row=0, column=0, padx=PAD_SM, pady=4, sticky="ew")
        bind_tooltip(btn_delete_selected, "Только отмеченные в этом чате")

        btn_delete_all = ctk.CTkButton(
            actions_grid, text="Удалить всё здесь", command=self._delete_all_here,
            corner_radius=BTN_RADIUS, fg_color=DANGER, hover_color=DANGER_HOVER,
        )
        btn_delete_all.grid(row=0, column=1, padx=PAD_SM, pady=4, sticky="ew")
        bind_tooltip(btn_delete_all, "Все ваши сообщения в этом чате")

        btn_except = ctk.CTkButton(
            actions_grid, text="Удалить кроме этого", command=self._delete_all_except,
            corner_radius=BTN_RADIUS, fg_color=DANGER, hover_color=DANGER_HOVER,
        )
        btn_except.grid(row=0, column=2, padx=PAD_SM, pady=4, sticky="ew")
        bind_tooltip(btn_except, "Удалит все ваши сообщения во всех остальных чатах. В текущем чате ничего не будет удалено.")

        btn_no_scan = ctk.CTkButton(
            actions_grid, text="Без скана", command=self._delete_all_no_scan,
            corner_radius=BTN_RADIUS, fg_color=DANGER, hover_color=DANGER_HOVER,
        )
        btn_no_scan.grid(row=1, column=0, padx=PAD_SM, pady=4, sticky="ew")
        bind_tooltip(btn_no_scan, "Обходит историю чата и удаляет каждое ваше сообщение по ходу. Список сообщений не строится — подходит для очень длинных историй.")

        btn_csv = ctk.CTkButton(
            actions_grid, text="CSV", command=self._export_messages_csv,
            corner_radius=BTN_RADIUS, fg_color=BTN_SECONDARY_DANGER,
        )
        btn_csv.grid(row=1, column=1, padx=PAD_SM, pady=4, sticky="ew")

        btn_json = ctk.CTkButton(
            actions_grid, text="JSON", command=self._export_messages_json,
            corner_radius=BTN_RADIUS, fg_color=BTN_SECONDARY_DANGER,
        )
        btn_json.grid(row=1, column=2, padx=PAD_SM, pady=4, sticky="ew")

        for c in range(3):
            actions_grid.columnconfigure(c, weight=1)

    def _schedule_search(self):
        if self._search_job is not None:
            try:
                self.after_cancel(self._search_job)
            except Exception:
                pass
        self._search_job = self.after(300, self._refresh_posts_list)

    def set_place(self, place: Optional[Place]):
        self.current_place = place
        self.title_label.configure(text=place.title or "Без названия" if place else "")
        self.posts_search_var.set("")
        self._refresh_posts_list()

    def _refresh_posts_list(self):
        """Перестроить список сообщений с учётом поиска по превью."""
        if not self.current_place:
            return
        self.check_vars.clear()
        for w in self.scroll.winfo_children():
            w.destroy()
        search = (self.posts_search_var.get() or "").strip().lower()
        messages = self.current_place.messages
        if search:
            messages = [(m[0], m[1], m[2]) for m in messages if search in (m[1] or "").lower()]
        if not messages:
            empty = ctk.CTkFrame(self.scroll, fg_color="transparent")
            empty.pack(fill="both", expand=True, pady=PAD * 3)
            msg = "В этом чате нет ваших сообщений." if not search else "Поиск не дал результатов."
            ctk.CTkLabel(empty, text=msg, font=font(14), text_color="gray", justify="center").pack(expand=True)
            return
        for mid, preview, date_str in messages:
            row = ctk.CTkFrame(self.scroll, fg_color=ROW_BG, corner_radius=8)
            row.pack(fill="x", pady=2, padx=2)
            var = ctk.BooleanVar(value=False)
            self.check_vars.append((mid, var))
            cb = ctk.CTkCheckBox(row, text="", variable=var, width=24, height=24)
            cb.pack(side="left", padx=PAD_SM, pady=PAD_SM)
            preview = preview or ""
            prev_short = preview[:70] + "…" if len(preview) > 70 else preview
            ctk.CTkLabel(row, text=f"{date_str}  ·  {prev_short}", anchor="w", wraplength=500, font=font(12)).pack(side="left", fill="x", expand=True, padx=PAD_SM, pady=PAD_SM)

    def _messages_in_date_range(self, show_errors=False):
        """Сообщения текущего чата в заданном периоде (date_from, date_to). Пустые поля = без ограничения."""
        if not self.current_place:
            return []
        from_str = (self.date_from_var.get() or "").strip()
        to_str = (self.date_to_var.get() or "").strip()
        from_dt = None
        to_dt = None
        if from_str:
            try:
                from_dt = datetime.strptime(from_str, "%Y-%m-%d")
            except ValueError:
                if show_errors:
                    messagebox.showwarning("Фильтр по дате", "Неверная дата 'От'. Используйте формат YYYY-MM-DD.")
                return None
        if to_str:
            try:
                to_dt = datetime.strptime(to_str, "%Y-%m-%d")
            except ValueError:
                if show_errors:
                    messagebox.showwarning("Фильтр по дате", "Неверная дата 'До'. Используйте формат YYYY-MM-DD.")
                return None
        if from_dt and to_dt and from_dt > to_dt:
            if show_errors:
                messagebox.showwarning("Фильтр по дате", "Дата 'От' не может быть позже даты 'До'.")
            return None
        if not from_str and not to_str:
            return self.current_place.messages
        result = []
        for mid, preview, date_str in self.current_place.messages:
            if from_str and (date_str or "") < from_str + " 00:00":
                continue
            if to_str and (date_str or "") > to_str + " 23:59":
                continue
            result.append((mid, preview, date_str))
        return result

    def _delete_selected(self):
        if not self.current_place:
            return
        in_range = self._messages_in_date_range(show_errors=True)
        if in_range is None:
            return
        ids = [mid for mid, var in self.check_vars if var.get()]
        in_range_ids = {m[0] for m in in_range}
        ids = [i for i in ids if i in in_range_ids]
        if not ids:
            messagebox.showinfo("Удаление", "Отметьте сообщения для удаления (или задайте период).")
            return
        if not messagebox.askyesno("Подтверждение", f"Удалить {len(ids)} выбранных сообщений? Продолжить?"):
            return
        scan_paused.clear()
        scan_stop_requested.clear()
        request_queue.put(("delete_here", self.current_place.chat_id, ids))

    def _delete_all_here(self):
        if not self.current_place or not self.current_place.messages:
            return
        in_range = self._messages_in_date_range(show_errors=True)
        if in_range is None:
            return
        if not in_range:
            messagebox.showinfo("Удаление", "Нет сообщений в выбранном периоде.")
            return
        n = len(in_range)
        if not messagebox.askyesno("Подтверждение", f"Удалить все {n} сообщений в этом чате (в выбранном периоде)? Продолжить?"):
            return
        ids = [m[0] for m in in_range]
        scan_paused.clear()
        scan_stop_requested.clear()
        request_queue.put(("delete_here", self.current_place.chat_id, ids))

    def _delete_all_except(self):
        if not self.current_place:
            return
        places = self.all_places_getter()
        others = [p for p in places if p.chat_id != self.current_place.chat_id and p.messages]
        if not others:
            messagebox.showinfo("Удаление", "Нет других чатов с вашими сообщениями.")
            return
        total = sum(len(p.messages) for p in others)
        chat_list = "\n".join(f"  \u2022 {p.title} ({len(p.messages)} \u0441\u043e\u043e\u0431\u0449.)" for p in others[:15])
        if len(others) > 15:
            chat_list += f"\n  ... \u0438 \u0435\u0449\u0451 {len(others) - 15} \u0447\u0430\u0442\u043e\u0432"
        if not messagebox.askyesno(
            "Подтверждение",
            f"Удалить {total} сообщений в {len(others)} чатах?\n\n{chat_list}\n\nВ текущем чате ничего не удалится. Продолжить?"
        ):
            return
        scan_paused.clear()
        scan_stop_requested.clear()
        request_queue.put(("delete_all_except", self.current_place.chat_id, places))

    def _delete_all_no_scan(self):
        if not self.current_place:
            return
        if not messagebox.askyesno("Подтверждение", "Удалять все ваши сообщения в этом чате по ходу обхода (без предварительного списка)? Продолжить?"):
            return
        scan_paused.clear()
        scan_stop_requested.clear()
        request_queue.put(("delete_all_no_scan", self.current_place.chat_id))

    def remove_deleted_ids(self, deleted_ids):
        if not self.current_place:
            return
        deleted_set = set(deleted_ids)
        self.current_place.messages = [(m[0], m[1], m[2]) for m in self.current_place.messages if m[0] not in deleted_set]
        self.set_place(self.current_place)

    def _export_messages_csv(self):
        if not self.current_place:
            messagebox.showinfo("Экспорт", "Откройте чат с сообщениями.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if path:
            try:
                export_messages_to_csv(self.current_place, path)
                messagebox.showinfo("Экспорт", f"Сохранено: {path}")
            except Exception as e:
                messagebox.showerror("Ошибка", str(e))

    def _export_messages_json(self):
        if not self.current_place:
            messagebox.showinfo("Экспорт", "Откройте чат с сообщениями.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json")])
        if path:
            try:
                export_messages_to_json(self.current_place, path)
                messagebox.showinfo("Экспорт", f"Сохранено: {path}")
            except Exception as e:
                messagebox.showerror("Ошибка", str(e))
