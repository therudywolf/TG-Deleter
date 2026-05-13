
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

"""
Очереди и события для обмена между GUI и фоновым воркером.
"""
import queue
import threading

# GUI -> worker (запросы)
request_queue: queue.Queue = queue.Queue()
# worker -> GUI (ответы)
response_queue: queue.Queue = queue.Queue()
# Сообщения для панели лога (строка или (уровень, строка))
log_queue: queue.Queue = queue.Queue()

# Управление текущей долгой операцией: скан, удаление, экспорт.
# Старые имена оставлены для совместимости с существующими экранами.
operation_paused = threading.Event()
operation_stop_requested = threading.Event()

# Пауза скана: is_set() = пользователь нажал «Пауза»
scan_paused = operation_paused
# Останов скана: is_set() = пользователь нажал «Стоп»
scan_stop_requested = operation_stop_requested
