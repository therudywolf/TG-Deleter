
# SPDX-License-Identifier: AGPL-3.0-only
# TG Deleter - Desktop utility for managing Telegram messages
# Copyright (C) 2024-2026 TG Deleter Contributors
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

"""Typed messages for worker <-> GUI communication."""
from dataclasses import dataclass, field
from typing import Any


@dataclass
class WorkerMsg:
    """Base class for all worker->GUI messages."""
    pass


@dataclass
class MeMsg(WorkerMsg):
    me_dict: dict
    session: str | None = None


@dataclass
class ScanProgressMsg(WorkerMsg):
    n: int
    title: str
    count: int | None = None


@dataclass
class ScanPlaceMsg(WorkerMsg):
    place: Any  # Place


@dataclass
class ScanDoneMsg(WorkerMsg):
    places: list
    stopped: bool
    session: str


@dataclass
class DeleteDoneMsg(WorkerMsg):
    chat_id: int
    deleted_ids: list[int]
    stopped: bool


@dataclass
class DeleteAllNoScanDoneMsg(WorkerMsg):
    chat_id: int
    count: int
    stopped: bool


@dataclass
class DeleteAllExceptDoneMsg(WorkerMsg):
    deleted_map: dict
    stopped: bool


@dataclass
class DeleteBatchProgressMsg(WorkerMsg):
    current: int
    total: int
    chat_id: int


@dataclass
class DeleteBatchDoneMsg(WorkerMsg):
    total_deleted: int
    chat_ids: list[int]
    stopped: bool


@dataclass
class DeleteOpStatusMsg(WorkerMsg):
    text: str


@dataclass
class ExportProgressMsg(WorkerMsg):
    kind: str
    payload: dict


@dataclass
class ExportDoneMsg(WorkerMsg):
    root: str
    manifest: dict
    stopped: bool


@dataclass
class ExportDialogsProgressMsg(WorkerMsg):
    n: int
    title: str


@dataclass
class ExportDialogsBatchMsg(WorkerMsg):
    batch: list


@dataclass
class ExportDialogsDoneMsg(WorkerMsg):
    dialogs: list
    stopped: bool
    session: str


@dataclass
class SwitchAccountDoneMsg(WorkerMsg):
    session: str


@dataclass
class LogMsg(WorkerMsg):
    text: str


@dataclass
class ErrorMsg(WorkerMsg):
    operation: str
    error: str


@dataclass
class FloodWaitMsg(WorkerMsg):
    seconds: int
    operation: str
