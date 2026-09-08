---
name: gws
description: >
  Google Workspace -- универсальный доступ ко всем сервисам Google.
  CLI: gws (Google official). Аккаунт: your-email@gmail.com.
  Используй когда: (1) Gmail -- читать/отправлять, (2) Calendar -- события,
  (3) Drive -- файлы, (4) Sheets -- таблицы, (5) Docs -- документы,
  (6) Tasks -- задачи Google. Работает на всех серверах через OAuth + Tailscale.
---

# GWS -- Google Workspace

CLI: `gws` (v0.6.3, Google official). Аккаунт: `your-email@gmail.com`.
Проект GCP: `your-gcp-project`.

## Auth

### Статус
```bash
gws auth status
```

### Mac mini (master) -- уже настроен
Config: `~/.config/gws/`
- `client_secret.json` -- OAuth client
- `credentials.json` -- refresh token
- `token_cache.json` -- access token (auto-refresh)

### Новый сервер -- setup за 2 минуты

```bash
# 1. На новом сервере: установить gws
pip install google-workspace-cli  # или brew install gws

# 2. С Mac mini: скопировать credentials через Tailscale
ssh NEW_SERVER "mkdir -p ~/.config/gws"
scp ~/.config/gws/client_secret.json NEW_SERVER:~/.config/gws/
scp ~/.config/gws/credentials.json NEW_SERVER:~/.config/gws/
scp ~/.config/gws/token_cache.json NEW_SERVER:~/.config/gws/

# 3. На новом сервере: проверить
ssh NEW_SERVER "gws auth status"
ssh NEW_SERVER "gws gmail users messages list --params '{\"userId\":\"me\",\"maxResults\":1}'"

# 4. Защитить credentials
ssh NEW_SERVER "chmod 600 ~/.config/gws/credentials.json ~/.config/gws/token_cache.json"
```

Tailscale IP серверов:
- Mac mini: YOUR_SERVER_IP
- Server-2: YOUR_SERVER_IP
- Server-3: YOUR_SERVER_IP
- Server-4: YOUR_SERVER_IP

### Health check
```bash
gws auth status | python3 -c "
import json, sys
s = json.load(sys.stdin)
print(f'User: {s.get(\"user\",\"?\")}')
print(f'Token valid: {s.get(\"token_valid\",\"?\")}')
print(f'Scopes: {s.get(\"scope_count\",0)}')
if not s.get('token_valid'):
    print('WARN: token expired, gws will auto-refresh on next call')
"
```

## Gmail

```bash
# Список писем
gws gmail users messages list --params '{"userId":"me","maxResults":10,"q":"newer_than:7d"}'

# Прочитать письмо
gws gmail users messages get --params '{"userId":"me","id":"MSG_ID","format":"full"}'

# Поиск
gws gmail users messages list --params '{"userId":"me","q":"from:someone@gmail.com subject:urgent","maxResults":5}'

# Отправить (ПОДТВЕРДИ у принца перед отправкой)
# gws работает с raw API, для отправки нужен base64-encoded MIME
# Проще использовать python:
python3 -c "
import base64, json, subprocess
from email.mime.text import MIMEText

msg = MIMEText('Текст письма')
msg['to'] = 'recipient@email.com'
msg['subject'] = 'Тема'
raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
result = subprocess.run([
    'gws', 'gmail', 'users', 'messages', 'send',
    '--params', '{\"userId\":\"me\"}',
    '--json', json.dumps({'raw': raw})
], capture_output=True, text=True)
print(result.stdout)
"
```

## Calendar

```bash
# Список календарей
gws calendar calendarList list

# События за период
gws calendar events list --params '{
  "calendarId":"primary",
  "timeMin":"2026-03-07T00:00:00Z",
  "timeMax":"2026-03-14T00:00:00Z",
  "singleEvents":true,
  "orderBy":"startTime"
}'

# Создать событие (ПОДТВЕРДИ у принца)
gws calendar events insert --params '{"calendarId":"primary"}' --json '{
  "summary":"Встреча",
  "start":{"dateTime":"2026-03-08T10:00:00+03:00"},
  "end":{"dateTime":"2026-03-08T11:00:00+03:00"}
}'
```

## Drive

```bash
# Список файлов
gws drive files list --params '{"pageSize":10,"q":"name contains \"report\""}'

# Метаданные файла
gws drive files get --params '{"fileId":"FILE_ID","fields":"name,mimeType,size,modifiedTime"}'

# Скачать файл
gws drive files get --params '{"fileId":"FILE_ID","alt":"media"}' --output /tmp/file.pdf

# Загрузить файл
gws drive files create --params '{"uploadType":"multipart"}' --json '{"name":"file.txt","parents":["FOLDER_ID"]}' --upload /path/to/file.txt
```

## Sheets

```bash
# Прочитать данные
gws sheets spreadsheets values get --params '{
  "spreadsheetId":"SHEET_ID",
  "range":"Sheet1!A1:D10"
}'

# Записать данные
gws sheets spreadsheets values update --params '{
  "spreadsheetId":"SHEET_ID",
  "range":"Sheet1!A1:B2",
  "valueInputOption":"USER_ENTERED"
}' --json '{"values":[["A","B"],["1","2"]]}'

# Добавить строки
gws sheets spreadsheets values append --params '{
  "spreadsheetId":"SHEET_ID",
  "range":"Sheet1!A:C",
  "valueInputOption":"USER_ENTERED",
  "insertDataOption":"INSERT_ROWS"
}' --json '{"values":[["x","y","z"]]}'

# Метаданные (список вкладок)
gws sheets spreadsheets get --params '{"spreadsheetId":"SHEET_ID","fields":"sheets.properties"}'
```

## Docs

```bash
# Прочитать документ
gws docs documents get --params '{"documentId":"DOC_ID"}'

# Экспорт в текст (через Drive)
gws drive files export --params '{"fileId":"DOC_ID","mimeType":"text/plain"}' --output /tmp/doc.txt
```

## Tasks (Google Tasks)

```bash
# Списки задач
gws tasks tasklists list

# Задачи из списка
gws tasks tasks list --params '{"tasklist":"TASKLIST_ID"}'
```

## Правила

1. **ПОДТВЕРЖДАЙ** перед отправкой email и созданием событий
2. Для скриптов: выход всегда JSON (по умолчанию)
3. `--page-all` для пагинации, `--page-limit N` для лимита
4. Token auto-refresh через refresh_token -- ручного обновления не нужно
5. Credentials в `~/.config/gws/` -- chmod 600 на всех серверах
6. Один аккаунт: `your-email@gmail.com` -- для всех агентов

## Дефолтные напоминания для событий

При создании ЛЮБОГО события в Calendar — ставить 3 напоминания:
- За 24 часа (1440 минут)
- За 3 часа (180 минут)
- За 15 минут

```json
"reminders": {
  "useDefault": false,
  "overrides": [
    {"method": "popup", "minutes": 1440},
    {"method": "popup", "minutes": 180},
    {"method": "popup", "minutes": 15}
  ]
}
```

Без исключений. Владелец хочет знать заранее.
