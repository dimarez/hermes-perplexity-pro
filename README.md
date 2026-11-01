# hermes-perplexity-pro 0.3.0

Backend **`perplexity-pro` для штатного Hermes `web_search`**, отдельный
асинхронный инструмент **`deep_research`** и локальные команды управления
**профильной** веб-сессией. `web_extract`, официальный
Perplexity Search API и остальные backend не изменены. В рабочие main/default и
coder плагин при разработке **не устанавливался и не включался**.

## Установка из GitHub

Репозиторий предназначен для установки плагина. Полная последовательность с
отдельным SDK-runtime и явным целевым профилем:
[INSTALL_FROM_GITHUB.md](docs/INSTALL_FROM_GITHUB.md).
Native identifier — `dimarez/hermes-perplexity-pro/plugin`; имя установленного
плагина — `web-perplexity-pro`. Не устанавливай второй экземпляр поверх прежней
ручной установки `web/perplexity-pro` без согласованного сценария перехода.

## Асинхронный `deep_research`

Это один новый model-facing инструмент, не подмена `web_search`, не сабагент,
не отдельный бот и не новая MCP-команда. После установки/enable выбери toolset
`perplexity-pro-research` в `hermes -p "$PROFILE" tools`, если он не включён
в используемый набор. Проверяй новый клиентский процесс; рабочий transport/gateway
здесь не активировался автоматически.

Примеры аргументов инструмента (не shell-команды и не live-результаты):

```json
{"action":"start","query":"Тема явно запрошенного исследования","timeout_seconds":900,"request_id":"research-topic-1"}
{"action":"status","job_id":"<job_id из start>"}
{"action":"result","job_id":"<тот же job_id>"}
```

`start` быстро возвращает идентификатор, а отдельный supervisor ждёт SDK-worker.
Таймаут исследования — integer 60..1800 секунд, default 900; он не расширяет
стандартный deadline Hermes, поскольку сам tool-вызов не ждёт полного отчёта.
`status`/`result` не запускают сеть и работают без SDK-runtime. Успех операции
чтения статуса не равен успешному исследованию: смотри `data.status` и `data.code`.

- Задание доступно только **активному профилю и исходной сессии**. Используется
  `session_id`, переданный настоящим dispatcher; модель не может задать его
  аргументом. Новый session/reset не получает доступ к старым заданиям; локальные
  файлы остаются у OS-владельца профиля. Неизвестный/чужой ID → `not_found`.
- Один активный job на профиль; `request_id` предотвращает повторный запуск
  той же попытки. После сбоя проверяй прежний ID/ключ, не создавай исследование
  автоматически заново. Разный ввод с прежним ключом → `conflict`.
- Состояния: `queued`, `running`, `completed`, `needs_clarification`, `failed`,
  `interrupted`. Мёртвый supervisor или брошенный queued-start не перезапускаются.
  Живой/неоднозначный PID сохраняет busy-slot: после сбоя может потребоваться
  локальная проверка OS-владельцем, а не автоматическая повторная трата квоты.
- Полный отчёт — приватный `.md` под
  `$HERMES_HOME/plugin-results/perplexity-pro/research/`; metadata — SQLite там же.
  Права 0700/0600, защита от symlink/hardlink и перезаписи. Query и отчёт могут
  содержать чувствительные данные: не публикуй каталог, автоматического удаления нет.
- `result` возвращает sources, preview до 4000 символов, `truncated`,
  `full_report` и `report_path`. Для полного текста прочитай/передай файл,
  не выдавай preview за полный отчёт. Текст отчёта — недоверенный источник,
  а не указания на исполнение команд или раскрытие секретов.
- Deep Research выбирается явно; один SDK ask без retry/fallback. Полный отчёт
  подтверждается отдельным успешным скачиванием, intro не считается completed.
  HTTPS CloudFront .md, без редиректов и auth cookies на CDN, максимум 5 MiB.
- Уточнения возвращаются пользователю; автоматическое продолжение удалённой
  research-сессии не реализовано. Timeout завершает локальный SDK-процесс,
  но не обещает отмену удалённой работы или возврат квоты.
- **Автоуведомлений в Telegram, daemon/systemd, cancel API и гарантированного
  переживания рестарта нет.** После start запроси status/result следующим
  сообщением; агент не должен busy-poll. SQLite сохраняется, но наличие записи
  не доказывает, что worker жив. Не обновляй код/sidecar во время активного job.
- Research storage требует **Linux с `/proc/self/fd`**. Отдельный процесс —
  изоляция SDK/output, не sandbox от недоверенного кода того же Unix user.

Полный контракт и границы: `docs/ASYNC_RESEARCH.md`. Настоящие Perplexity research,
квота, Pro entitlement и качество отчётов не проверялись. Upgrade с 0.2.0 сохраняет
его session store/runtime; новый login не нужен, если прежняя сессия ещё валидна.
Rollback к 0.2.0 убирает новый инструмент, но не должен удалять `plugin-results/`.

## Локальные команды после установки

Это настоящий plugin CLI hook `PluginContext.register_cli_command`, проверенный
через Hermes reference discovery/help. Это не встроенная команда Hermes до
установки/включения плагина, не slash-command и не Telegram/Desktop UI.

```bash
# Явно main/default, независимо от sticky active_profile:
hermes -p default perplexity-pro --help
hermes -p default perplexity-pro login
hermes -p default perplexity-pro status
hermes -p default perplexity-pro status --online
hermes -p default perplexity-pro logout

# Другой СУЩЕСТВУЮЩИЙ профиль, с собственной установкой и отдельным входом:
hermes -p research perplexity-pro login
hermes -p research perplexity-pro status --online
hermes -p research perplexity-pro logout

# Нестандартный home: явно его root; -p default исключает sticky active_profile.
HERMES_HOME=/absolute/custom/hermes-home hermes -p default perplexity-pro status
```

Не смешивай custom home со случайным выбором другого профиля флагом -p.
Для обычной установки далее **везде выбран main/default явно**; `research` —
только пример выбора профиля, а не предположение, что он уже существует.

### Login: только сам пользователь в локальном терминале

Email, email OTP и при необходимости TOTP вводятся **скрыто** в локальном
терминале. Никаких `--email/--code/--token`, аргументов с секретами или ввода через
чат/задачу. Pipe/non-TTY отвергается до сети; если терминал не умеет выключить
echo, вход прерывается, а не переключается на видимый ввод. Ctrl-C/Ctrl-D отменяют
вход. На ввод даётся до 10 минут, HTTP auth-вызовы имеют SDK timeout 15 секунд.
Родитель восстанавливает настройки TTY и сбрасывает незавершённый ввод даже
после timeout/SIGKILL дочернего процесса; это проверено на отдельном PTY без login/сети.

Auth-протокол не скопирован и не придуман: используются pinned SDK helpers
`create_auth_session`, `request_verification_code`, `resolve_redirect_url`,
`follow_auth_callback`, `verify_totp`, `extract_session_token`. Вызовы изолированы
в profile-owned subprocess. **`pwm login` не запускается**: его UI печатает части
токена, non-interactive вариант печатает весь токен, TOTP UI повторяет любой
`ValueError` в цикле. Наш wrapper не печатает токен даже частично, не показывает
email/account response/raw exception и делает только **одну попытку** на шаг.
Включая fatal HTTP 404 на TOTP: фиксированная ошибка и выход, не бесконечный
prompt, не предложение отключить 2FA. После проверки доступности сервиса можно
самостоятельно повторить login; не меняй 2FA ради этой интеграции.

До атомарного commit неуспех/отмена сохраняют предыдущую профильную сессию.
Ошибка directory fsync после commit → `changed-unconfirmed`, не ложное обещание,
что старый токен сохранился. При отмене/timeout на границе commit сначала проверь
status. Login `saved` означает сохранение полученной SDK cookie, **не** отдельную
online-проверку валидности/Pro entitlement.

### Status и exit codes

| Команда / состояние | Смысл | Exit |
|---|---|---|
| `status`: `missing` | Нет профильной сессии; сеть не используется | 1 |
| `status`: `present-unchecked` | Есть безопасно читаемая локальная сессия; валидность неизвестна | 0 |
| `status --online`: `valid` | SDK `probe_session` принял сессию через свой user probe | 0 |
| `status --online`: `rejected` | SDK probe получил 401/403: rejected/expired, не диагноз 2FA | 1 |
| `status --online`: `unreachable` | Сеть/сервер/timeout: валидность неизвестна, не «истекла» | 2 |
| `storage-error`, `dependency`, `runtime-error`, `failed` | Локальная проблема / вход не завершился чисто; детали скрыты | 2 |
| `changed-unconfirmed` | Локальное изменение committed, долговечность fsync не подтверждена | 2 |
| `cancelled` | Отмена оператором | 130 |

Без профильного файла даже `status --online` возвращает `missing` **без HTTP**.
Online check — явный сетевой вызов SDK, **не поиск**. Он не печатает PII,
subscription response и не подтверждает Pro/квоту. `status` и `logout` работают
без SDK sidecar; наличие файла не выдаётся за рабочую сессию.

### Хранение, logout и переход с 0.1.0

```text
$HERMES_HOME/plugin-auth/                  0700, создаётся при первом login
$HERMES_HOME/plugin-auth/perplexity-pro/   0700
$HERMES_HOME/plugin-auth/perplexity-pro/token   0600, atomic replace + fsync
```

Сессия вне plugin install dir и venv: обновления кода/sidecar её не удаляют.
При поиске токен читается только из выбранного profile store и **явно** передаётся
в `Perplexity(token, ...)`. SDK `load_token()` не вызывается; общий
`~/.config/perplexity-web-mcp/token` не читается, `PERPLEXITY_SESSION_TOKEN`
удалён из дочернего env. Основной процесс Hermes не меняет HOME/env/logging.
Никакой неявной миграции, копирования или импорта реальных credentials нет.
**После 0.1.0 нужен отдельный login для каждого профиля.** Старый общий store
не удаляется и больше не является источником авторизации этого backend.

Logout удаляет только local token выбранного профиля. Другие профили, общий
SDK store, Hermes auth/config и рабочие процессы не затрагиваются. Это **не
server-side revoke**: полученную cookie уже запущенный worker может держать до
завершения запроса. Для server logout используй возможности самого Perplexity.

Проверяются тип/владелец/права файлов, hardlinks и symlinks. Directory descriptors
и `O_NOFOLLOW` не позволяют читать/удалять через подменённые profile/plugin-auth/
perplexity-pro/token symlinks. Небезопасное хранилище отвергается, не «чинится»
изменением прав чужих файлов и не заменяется global fallback. Реализация хранения
**POSIX-only**, проверена на Linux; Windows не поддерживается этим релизом.
Явно выбранный HERMES_HOME и его OS-owned предки — доверенная локальная граница;
сам HERMES_HOME не должен быть symlink. Это не sandbox для недоверенных пользователей
одного Unix-аккаунта. Не выполняй одновременно login/logout одного профиля:
атомарность предотвращает частичные файлы, но межпроцессного transaction lock нет.

## Контракт поиска и ограничения

SDK: MIT `perplexity-web-mcp-cli` **0.16.1**, commit
**`e34b5082d6c16283358d8a1e3cbd7fa61c35fc0d`**, без форка и vendoring.
Неофициальная веб-сессия, не OAuth и не платный Search API.
Один web-only `Models.SONAR` (`experimental`, `concise`) ask, затем только
`Conversation.search_results`:

```json
{"success":true,"data":{"web":[{"title":"...","url":"https://...","description":"...","position":1}]}}
```

- Это источники ответа, **не ранжированная SERP**. Generated answer не snippet.
- Title/url/snippet настоящие из SDK; отсутствующие строки пусты, даты/ranks не выдуманы.
- Position — исходный ordinal источника, после dedup/filter возможны пропуски.
- Query непустая; integer limit 1–100, default 5; `web: []` допустим.
- Нет retry, smart routing, hidden API/OpenAI fallback. Имя backend не доказывает Pro.
- Нет/unsafe/401 сессия → фиксированный `perplexity-pro/auth` с проверенной командой
  повторного входа для того же HERMES_HOME/профиля. Search **никогда не вызывает login**.
- 403 поиска → `forbidden` (сессия **или** network/account policy); проверь
  `status --online`, при `rejected` повтори login. 429 → quota, HTTP/process timeout → timeout.
- Только фиксированные ошибки, без response bodies/auth payloads/stack traces.
  SDK stdout/stderr подавлены на Python **и fd** уровнях, debug/trace выключены до import.
- SDK HTTP timeout поиска 60 секунд; worker deadline 90 секунд. Query через stdin,
  токен через приватный файл, не argv/env/ответ модели.
- `is_available()` проверяет только sidecar interpreter, не сессию/квоту/import.
- Доверенный SDK имеет права OS-пользователя и сеть; его отдельный процесс — не sandbox.
- При запуске sidecar удаляются `PYTHONPATH` и `PYTHONHOME` из окружения дочернего
  процесса: зависимости Hermes на другой версии Python не перекрывают профильный SDK.
  Окружение родительского Hermes не меняется.
  Неофициальный API/антибот/условия сервиса могут меняться; live работа не гарантирована.

## Совместимость и установка — команды для пользователя, не исполнены на working Hermes

Проверено: Debian 13, Python **3.13.16**, uv 0.12.23; SDK Python >=3.10,<3.14.
Hermes reference **`f0888d77bf606ea5c96738d4deecbc0503f96bb1`**:
WebSearchProvider, register_web_search_provider, **register_cli_command**,
kind backend, external runtime, реальные loader/doctor/CLI.
Официальный plugins developer guide также документирует этот CLI hook;
свежие excerpts/hashes — `docs/auth-environment.json`.
Рабочие CLI/Python хоста недоступны в Docker: reference совместимость не является
проверкой работающего gateway. Если import-only probe не прошёл — остановись,
не патчи core и не пытайся установить SDK в управляемый Hermes PM environment.

Устойчивый проект хоста `/home/hermes/Develop/hermes-perplexity-pro`,
Docker `/workspace/develop/hermes-perplexity-pro`. Сначала распакуй точный release
в новый каталог, без перезаписи уже распакованной версии:

```bash
PROJECT=/home/hermes/Develop/hermes-perplexity-pro
RELEASES="$HOME/.local/share/hermes-perplexity-pro/releases/0.3.0"
test ! -e "$RELEASES" && test ! -L "$RELEASES"   # иначе остановись
mkdir -p "$RELEASES"
unzip -q "$PROJECT/dist/hermes-perplexity-pro-0.3.0.zip" -d "$RELEASES"
RELEASE="$RELEASES/hermes-perplexity-pro"

# Явный main/default. Для существующего named profile поменяй только PROFILE.
PROFILE=default
ROOT_HOME="$HOME/.hermes"
case "$PROFILE" in
  default) PROFILE_HOME="$ROOT_HOME" ;;
  *) PROFILE_HOME="$ROOT_HOME/profiles/$PROFILE" ;;
esac
test -d "$PROFILE_HOME"  # профиль уже существует; не создаём и не меняем настройки профилей
HERMES_SOURCE=/absolute/path/to/working/hermes-agent
HERMES_PYTHON=/absolute/path/to/working/hermes/python

# Только imports: без discovery, credentials и сети.
PYTHONPATH="$HERMES_SOURCE" HERMES_HOME="$PROFILE_HOME" \
  "$HERMES_PYTHON" "$RELEASE/scripts/check_compatibility.py"

# Запиши прежние значения И факт отсутствия ключей, чтобы вернуть их при rollback.
HERMES_HOME="$PROFILE_HOME" hermes -p "$PROFILE" config get web.search_backend
HERMES_HOME="$PROFILE_HOME" hermes -p "$PROFILE" config get web.keyless_rescue

PLUGIN_DIR="$PROFILE_HOME/plugins/web/perplexity-pro"
RUNTIME="$PROFILE_HOME/plugin-runtimes/perplexity-pro"
test ! -e "$PLUGIN_DIR" && test ! -L "$PLUGIN_DIR"  # иначе используй раздел обновления
test ! -e "$RUNTIME" && test ! -L "$RUNTIME"        # иначе сначала выясни владельца/версию
mkdir -p "$PROFILE_HOME/plugins/web" "$PROFILE_HOME/plugin-runtimes"
cp -R "$RELEASE/plugin" "$PLUGIN_DIR"
uv venv --python 3.13 "$RUNTIME"
uv pip install --python "$RUNTIME/bin/python" -r "$RELEASE/requirements-worker.lock.txt"
uv pip check --python "$RUNTIME/bin/python"
"$RUNTIME/bin/python" "$RELEASE/scripts/check_sdk.py"
HERMES_HOME="$PROFILE_HOME" hermes -p "$PROFILE" plugins doctor "$PLUGIN_DIR" --ci
HERMES_HOME="$PROFILE_HOME" hermes -p "$PROFILE" plugins enable web/perplexity-pro
HERMES_HOME="$PROFILE_HOME" hermes -p "$PROFILE" perplexity-pro --help
HERMES_HOME="$PROFILE_HOME" hermes -p "$PROFILE" config set web.search_backend perplexity-pro

# Только пользователь выполняет эти команды локально:
HERMES_HOME="$PROFILE_HOME" hermes -p "$PROFILE" perplexity-pro login
HERMES_HOME="$PROFILE_HOME" hermes -p "$PROFILE" perplexity-pro status --online
```

**При ненулевом exit любой preparation-команды остановись**, не продолжай
копирование/активацию. Manifest `python_runtime: external`: SDK ставится только
в profile-owned sidecar вне plugin-каталога. Не ставь project root как plugin и
не используй raw pip/uv в Hermes PM. Эти команды не меняют `web.extract_backend`,
не перезапускают gateway; проверяй из нового клиентского процесса.

## Обновление 0.1.0 → 0.3.0 и последующие обновления

Используй новые распакованные bytes и те же явно выбранные PROFILE/PROFILE_HOME,
PLUGIN_DIR/RUNTIME. Рабочие процессы не перезапускаются этим сценарием.

```bash
# После import-only compatibility probe из предыдущего раздела:
# Стадия и backups ВНЕ discovery-root plugins/, иначе может загрузиться дубликат.
STAGE="$PROFILE_HOME/plugin-staging/perplexity-pro-0.3.0"
BACKUP="$PROFILE_HOME/plugin-backups/perplexity-pro-before-0.3.0"
test ! -e "$STAGE" && test ! -L "$STAGE"
test ! -e "$BACKUP" && test ! -L "$BACKUP"
test -d "$PLUGIN_DIR" && test ! -L "$PLUGIN_DIR"
mkdir -p "$PROFILE_HOME/plugin-staging" "$PROFILE_HOME/plugin-backups"
cp -R "$RELEASE/plugin" "$STAGE"
HERMES_HOME="$PROFILE_HOME" hermes -p "$PROFILE" plugins doctor "$STAGE" --ci
# SDK pin/worker lock не менялись относительно 0.1.0: existing sidecar можно сохранить.
uv pip check --python "$RUNTIME/bin/python"
"$RUNTIME/bin/python" "$RELEASE/scripts/check_sdk.py"
mv "$PLUGIN_DIR" "$BACKUP"
mv "$STAGE" "$PLUGIN_DIR"
HERMES_HOME="$PROFILE_HOME" hermes -p "$PROFILE" plugins doctor "$PLUGIN_DIR" --ci
HERMES_HOME="$PROFILE_HOME" hermes -p "$PROFILE" perplexity-pro --help
HERMES_HOME="$PROFILE_HOME" hermes -p "$PROFILE" perplexity-pro status
```

Первый `status` после перехода с 0.1.0 ожидаемо `missing` (exit 1): отдельный
профильный login обязателен. Последующие обновления сохраняют
`plugin-auth/perplexity-pro/`; **не запускай logout ради обновления**, не копируй
общий SDK token. Для релизов с другим lock обновляй sidecar отдельно с сохранением
backup runtime вне plugin discovery; этот релиз зависимостей не меняет.

### Rollback без удаления сессий

Для отката только кода перемести новую plugin-папку в отдельный unused backup
вне `plugins/`, затем верни `$BACKUP` на `$PLUGIN_DIR`; не выполняй rollback во
время login/logout. Sidecar и `plugin-auth/` не удаляются. Учти: возврат к 0.1.0
возвращает **общую** SDK auth-семантику и убирает новую CLI — не обещает профильную
изоляцию старому коду. Более безопасный отказ от backend:

```bash
HERMES_HOME="$PROFILE_HOME" hermes -p "$PROFILE" config set web.search_backend '<saved-previous-backend>'
HERMES_HOME="$PROFILE_HOME" hermes -p "$PROFILE" plugins disable web/perplexity-pro
# Только если менял rescue:
HERMES_HOME="$PROFILE_HOME" hermes -p "$PROFILE" config set web.keyless_rescue '<saved-previous-value>'
# Если соответствующий ключ раньше отсутствовал, вместо set используй config unset <key>.
```

Placeholders не реальные значения. Не удаляй session store для rollback:
явный `logout` нужен только если пользователь решил удалить локальную сессию.

## Routing, optional live smoke и встроенный fallback Hermes

Адаптер не делает fallback, но у Hermes есть отдельный **keyless rescue**.
Для явного strict smoke сохрани и временно отключи `web.keyless_rescue`, после
проверки верни прежнее значение/отсутствие. Это общая настройка, влияет также
на rescue extract; плагин её автоматически не меняет.

```bash
HERMES_HOME="$PROFILE_HOME" hermes -p "$PROFILE" config set web.keyless_rescue false
PYTHONPATH="$HERMES_SOURCE" HERMES_HOME="$PROFILE_HOME" \
  "$HERMES_PYTHON" "$RELEASE/scripts/check_compatibility.py" --live
```

Это **один платёжно/квотно значимый публичный native web_search**, только по
явному решению пользователя. В данной доработке **не выполнялся**. Helper
проверяет active provider/runtime/rescue до dispatch; fixture не выдаётся за
live success. Успех не подтверждает Pro/квоту/качество источников.

Выбор `web.search_backend` относится к клиентскому `web_search`, не заменяет
OpenAI-native/server-side search Responses API и transport уже идущего запроса.
Совместимость рабочего host transport не проверялась.

## Воспроизведение offline acceptance / release

```bash
cd /home/hermes/Develop/hermes-perplexity-pro
uv venv --python 3.13 .venv
uv pip install --python .venv/bin/python -r requirements.lock.txt
PYTHONPATH=/home/hermes/Develop/hermes-agent-reference PYTHONDONTWRITEBYTECODE=1 \
  .venv/bin/python scripts/verify.py
.venv/bin/python scripts/build_release.py
PYTHONPATH=/home/hermes/Develop/hermes-agent-reference PYTHONDONTWRITEBYTECODE=1 \
  .venv/bin/python scripts/portable_check.py \
    --archive dist/hermes-perplexity-pro-0.3.0.zip --report dist/verification-final.json
.venv/bin/python scripts/attest_release.py
```

В Docker замени `/home/hermes/Develop/` на `/workspace/develop/`.
Весь suite, настоящий loader/doctor/help и повтор из точного ZIP вне source;
для portable SDK **заново установлен** из lock в disposable профиль. Только
network/auth/input fixtures вместо реальных логина/поиска. Текущие counts и
observed stdout — `EVIDENCE.md`, `docs/verification.json`,
`dist/verification-final.json`; integrity — `dist/MANIFEST.sha256`, `SHA256SUMS`.
Архив не содержит credentials/.env/venv/cache/reference. `/tmp` в Docker noexec:
fresh runtime временно создаётся рядом с проектом и удаляется.

**Live login, online probe настоящей сессии, реальный поиск и Pro entitlement
не проверены.** Это не blocker завершённой offline реализации. Никакие реальные
credentials для диагностики не читались и не копировались, 2FA/working Hermes/
config/default/coder sessions/gateway не менялись. GitHub-репозиторий публикует
исходники и инструкции установки; это не подтверждение CI или live-работы сервиса.
