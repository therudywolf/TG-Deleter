
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

"""Logging configuration with file rotation."""
import os
import logging
from logging.handlers import RotatingFileHandler


def setup_file_logging(log_dir: str, level: int = logging.DEBUG):
    """Add a rotating file handler to the tg_deleter logger.
    
    Creates log files in log_dir with max 5MB per file, 3 backups.
    """
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "tg_deleter.log")
    
    handler = RotatingFileHandler(
        log_path,
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=3,
        encoding="utf-8",
    )
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(
        "[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    
    logger = logging.getLogger("tg_deleter")
    logger.addHandler(handler)
    
    return log_path
