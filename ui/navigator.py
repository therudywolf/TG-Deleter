"""Navigation controller for switching between content frames."""
import customtkinter as ctk


class Navigator:
    """Manages frame visibility — only one frame is shown at a time."""

    def __init__(self, container: ctk.CTkFrame):
        self._container = container
        self._frames: dict[str, ctk.CTkFrame] = {}
        self._current_key: str | None = None

    def register(self, key: str, frame: ctk.CTkFrame):
        self._frames[key] = frame

    @property
    def current(self) -> str | None:
        return self._current_key

    def show(self, key: str):
        if self._current_key == key:
            return
        if self._current_key and self._current_key in self._frames:
            self._frames[self._current_key].pack_forget()
        frame = self._frames.get(key)
        if frame:
            frame.pack(fill="both", expand=True)
            self._current_key = key

    def hide_all(self):
        for frame in self._frames.values():
            frame.pack_forget()
        self._current_key = None
