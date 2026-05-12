"""
CLI TG Deleter: один чат из конфига (core.chat_id_cli).
Запуск: python script.py --cli
"""
import sys
import argparse
import logging

logging.basicConfig(
    level=logging.DEBUG,
    format="[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
    datefmt="%H:%M:%S",
)
logging.getLogger("pyrogram").setLevel(logging.WARNING)

from core import (
    __version__,
    create_client,
    get_current_session,
    set_current_session,
    normalize_session_name,
    set_app,
    set_me_from_dict,
    fetch_and_set_my_channels,
    add_account,
    get_chat_id_cli,
    get_api_id,
    get_api_hash,
    load_api_config,
    load_config,
    save_api_config,
    get_api_config,
    delete_message_ids,
    delete_all_my_in_chat_no_scan,
    scan_chat,
    log,
)

# Хранилище для CLI (один чат)
scanned_posts = []


def _require_api():
    load_api_config()
    load_config()
    if not get_api_id() or not get_api_hash():
        print("Сначала выполните первоначальную настройку в приложении.")
        sys.exit(1)


async def view_posts():
    global scanned_posts
    cid = get_chat_id_cli()
    print("\n*Принюхиваюсь к трафику...*")
    scanned_posts = await scan_chat(cid)
    if not scanned_posts:
        print("Твоих постов не найдено. Сектор чист.")
        return
    print("\n--- Список постов для удаления ---")
    for i, (mid, preview, date_str) in enumerate(scanned_posts, 1):
        print(f"  {i}. ID: {mid} | {date_str} | {preview}")
    print(f"\nИтог: найдено {len(scanned_posts)} твоих сообщений.")
    print("Дальше: точечное удаление (2) или удалить все (3).")


async def point_delete():
    global scanned_posts
    if not scanned_posts:
        print("\nСначала выполните просмотр постов (п. 1).")
        return
    cid = get_chat_id_cli()
    valid_ids = {mid for mid, _, _ in scanned_posts}
    prompt = "Введите ID сообщений через запятую (или один ID): "
    raw = input(prompt).strip()
    if not raw:
        print("Ничего не введено. Отмена.")
        return
    try:
        ids_input = [int(x.strip()) for x in raw.split(",") if x.strip()]
    except ValueError:
        print("Ошибка: введите числа через запятую.")
        return
    to_delete = [i for i in ids_input if i in valid_ids]
    unknown = set(ids_input) - set(to_delete)
    if unknown:
        print(f"Пропущены ID не из твоего списка: {unknown}")
    if not to_delete:
        print("Нет ни одного ID из списка для удаления.")
        return
    print(f"\n*Удаляю {len(to_delete)} постов...*")
    deleted_ids = await delete_message_ids(cid, to_delete)
    deleted_set = set(deleted_ids)
    scanned_posts = [(m, p, d) for m, p, d in scanned_posts if m not in deleted_set]
    print(f"\nУдалено {len(deleted_ids)} из {len(to_delete)}. В списке осталось {len(scanned_posts)} постов.")


async def delete_all():
    global scanned_posts
    if not scanned_posts:
        print("\nСначала выполните просмотр постов (п. 1).")
        return
    cid = get_chat_id_cli()
    n = len(scanned_posts)
    confirm = input(f"Удалить все {n} постов? (y/n): ")
    if confirm.lower() != "y":
        print("Отмена. Оружие на предохранителе.")
        return
    print("\n*Обнажаю клыки. Начинаю стерилизацию сектора...*")
    ids_all = [mid for mid, _, _ in scanned_posts]
    deleted_ids = await delete_message_ids(cid, ids_all)
    scanned_posts = []
    print(f"\nОперация завершена. Удалено {len(deleted_ids)} сообщений. Клиническая чистота.")


async def delete_all_no_scan():
    """Идём по истории чата и удаляем каждый свой пост сразу."""
    cid = get_chat_id_cli()
    confirm = input("Удалять все свои посты по ходу обхода без предварительного списка? (y/n): ")
    if confirm.lower() != "y":
        print("Отмена.")
        return
    print("\n*Обход сектора с зачисткой. Нашёл — удалил...*")
    count = await delete_all_my_in_chat_no_scan(
        cid,
        progress_callback=lambda n: print(f"  Удалено: {n}...", end="\r"),
    )
    print(f"\nГотово. Удалено {count} сообщений.")


async def main_cli(chat_title: str | None = None):
    while True:
        print("\n" + "=" * 40)
        print(" ТЕРМИНАЛ ЗАЧИСТКИ ")
        print("=" * 40)
        print("1. Просмотреть посты (сканировать и показать список)")
        print("2. Точечное удаление (по ID из списка)")
        print("3. Удалить все посты (из сохранённого списка)")
        print("4. Удалить все без скана (обход с удалением по ходу)")
        print("5. Уйти в тень (Выход)")
        print("=" * 40)
        if scanned_posts:
            print(f"   [В памяти: {len(scanned_posts)} постов]")
        cid = get_chat_id_cli()
        if cid is not None:
            label = f"{chat_title} ({cid})" if chat_title else str(cid)
            print(f"   Чат/канал: {label}")
        choice = input("Введи команду (1/2/3/4/5): ").strip()
        if choice == "1":
            await view_posts()
        elif choice == "2":
            await point_delete()
        elif choice == "3":
            await delete_all()
        elif choice == "4":
            await delete_all_no_scan()
        elif choice == "5":
            print("*Растворяюсь в цифровом шуме.*")
            break
        else:
            print("Мимо. Жми 1, 2, 3, 4 или 5.")


async def _cli_run(app):
    """Использует переданный клиент app (уже в async with app в вызывающем коде)."""
    set_app(app)
    try:
        try:
            me = await app.get_me()
            me_dict = {
                "id": getattr(me, "id", None),
                "username": (getattr(me, "username", None) or "").strip() or None,
                "first_name": getattr(me, "first_name", None) or None,
                "last_name": getattr(me, "last_name", None) or None,
            }
            set_me_from_dict(me_dict)
        except Exception as e:
            log.warning("CLI get_me failed: %s", e)
        try:
            await fetch_and_set_my_channels(app)
        except Exception as e:
            log.warning("CLI fetch_and_set_my_channels failed: %s", e)
        chat_title = None
        try:
            cid = get_chat_id_cli()
            if cid is not None:
                chat_info = await app.get_chat(cid)
                chat_title = getattr(chat_info, "title", None) or str(cid)
        except Exception as e:
            log.warning("CLI get_chat title failed: %s", e)
        await main_cli(chat_title=chat_title)
    finally:
        set_app(None)


def parse_args():
    parser = argparse.ArgumentParser(description="TG Deleter — удаление своих сообщений в Telegram")
    parser.add_argument("--version", action="version", version=f"TG Deleter {__version__}")
    sub = parser.add_subparsers(dest="command")

    cli_parser = sub.add_parser("cli", help="Режим CLI")
    cli_parser.add_argument("--chat-id", type=int, help="ID чата/канала")

    login_parser = sub.add_parser("login", help="Авторизация сессии")
    login_parser.add_argument("session", help="Имя сессии")

    args, _ = parser.parse_known_args()

    if args.command is None:
        if "--login" in sys.argv:
            args.command = "login"
            idx = sys.argv.index("--login")
            if idx + 1 < len(sys.argv):
                args.session = sys.argv[idx + 1].strip()
            else:
                args.session = None
        elif "--cli" in sys.argv:
            args.command = "cli"
            args.chat_id = None
            if "--chat-id" in sys.argv:
                idx = sys.argv.index("--chat-id")
                if idx + 1 < len(sys.argv):
                    try:
                        args.chat_id = int(sys.argv[idx + 1].strip())
                    except ValueError:
                        pass

    return args


def main():
    args = parse_args()

    if args.command == "login":
        _require_api()
        session = getattr(args, "session", None)
        session = normalize_session_name(session)
        if not session:
            print("Укажите безопасное имя сессии: 2-64 символа, только буквы, цифры, _ и -.")
            sys.exit(1)
        add_account(session)
        set_current_session(session)
        app = create_client(session)
        async def _do_login():
            async with app:
                set_app(app)
                me = await app.get_me()
                name = getattr(me, "first_name", "") or ""
                print(f"\nВход выполнен: {name}. Сессия «{session}» сохранена.")
        app.run(_do_login())
    elif args.command == "cli":
        _require_api()
        if not get_current_session():
            print("Сначала добавьте аккаунт в приложении (Настройки / левая панель).")
            sys.exit(1)
        chat_id_arg = getattr(args, "chat_id", None)
        if chat_id_arg is not None:
            cfg = get_api_config()
            cfg["chat_id_cli"] = chat_id_arg
            save_api_config(cfg)
        elif get_chat_id_cli() is None:
            print("Chat_id канала не задан (в api_config.json или через --chat-id).")
            raw = input("Введи chat_id канала (например -1001863361946): ").strip()
            try:
                cid = int(raw) if raw else None
            except ValueError:
                cid = None
            if cid is None:
                print("Неверный chat_id. Выход.")
                sys.exit(1)
            cfg = get_api_config()
            cfg["chat_id_cli"] = cid
            save_api_config(cfg)
        log.info("CLI режим: chat_id_cli=%s", get_chat_id_cli())
        app = create_client(get_current_session())

        async def _run():
            async with app:
                await _cli_run(app)

        app.run(_run())
    else:
        from gui import run_gui
        run_gui()


if __name__ == "__main__":
    main()
