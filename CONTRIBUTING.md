# Contributing

Thanks for improving TG Deleter.

## Development

```bash
python -m venv venv
source venv/bin/activate
pip install -e ".[dev]"
pytest
```

On Windows, use `venv\Scripts\activate` instead of `source`.

## Privacy Rules

Do not commit local Telegram data or credentials:

- `api_config.json`, `config.json`, `accounts_profiles.json`
- `*.session`, `*.session-*`, `*.sqlite*`, `*.db`
- scan caches and exported chats
- `.env` or `.env.*`

Use `api_config.example.json` for examples.

## License

By contributing, you agree that your contribution is licensed under AGPL-3.0-only.
