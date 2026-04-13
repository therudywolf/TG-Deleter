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

# Пауза скана: is_set() = пользователь нажал «Пауза»
scan_paused = threading.Event()
# Останов скана: is_set() = пользователь нажал «Стоп»
scan_stop_requested = threading.Event()
