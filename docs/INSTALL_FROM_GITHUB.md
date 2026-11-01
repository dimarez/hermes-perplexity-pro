# Установка из GitHub

Репозиторий `dimarez/hermes-perplexity-pro` — источник установки плагина.
Native plugin находится в подкаталоге **plugin/**, а не в корне репозитория.
Поэтому identifier для Hermes: **dimarez/hermes-perplexity-pro/plugin**.
Имя установленного плагина из manifest: **web-perplexity-pro**.

## Требования и границы

- Linux, Git, uv и Python 3.13; Hermes с API из указанного в README reference.
- Существующий целевой профиль Hermes. Выбирай его явно во всех командах.
- SDK ставится только в отдельный профильный runtime, не в Python самого Hermes.
- Не устанавливай второй экземпляр, если уже используешь ручную установку
  `web/perplexity-pro`: сначала согласуй перенос кода, сохранив session store.
- Установка и включение не выполняют login и не подтверждают работу Perplexity.
  Они могут скачивать открытые Git/Python-зависимости, но не расходуют research-квоту.

## Первичная установка

Выбери новый каталог checkout; не перезаписывай существующий проект.
Задай PROFILE как default или имя уже существующего профиля.
Пример предполагает стандартный root `$HOME/.hermes`; custom HERMES_HOME
нужно подставить явно, не смешивая его с другим профилем.

```bash
set -e
PROFILE=default
ROOT_HOME="$HOME/.hermes"
case "$PROFILE" in
  default) PROFILE_HOME="$ROOT_HOME" ;;
  *) PROFILE_HOME="$ROOT_HOME/profiles/$PROFILE" ;;
esac
test -d "$PROFILE_HOME"

CHECKOUT="$HOME/Develop/hermes-perplexity-pro"
test ! -e "$CHECKOUT" && test ! -L "$CHECKOUT"
git clone https://github.com/dimarez/hermes-perplexity-pro.git "$CHECKOUT"
cd "$CHECKOUT"
REV="$(git rev-parse HEAD)"

# Отдельная проверка совместимости — см. README, до установки на working host.
# Сначала скачиваем native plugin без активации; устанавливается именно этот commit.
HERMES_HOME="$PROFILE_HOME" hermes -p "$PROFILE" plugins install \
  dimarez/hermes-perplexity-pro/plugin --ref "$REV" --no-enable

RUNTIME="$PROFILE_HOME/plugin-runtimes/perplexity-pro"
test ! -e "$RUNTIME" && test ! -L "$RUNTIME"
mkdir -p "$PROFILE_HOME/plugin-runtimes"
uv venv --python 3.13 "$RUNTIME"
uv pip install --python "$RUNTIME/bin/python" -r "$CHECKOUT/requirements-worker.lock.txt"
uv pip check --python "$RUNTIME/bin/python"
"$RUNTIME/bin/python" "$CHECKOUT/scripts/check_sdk.py"

HERMES_HOME="$PROFILE_HOME" hermes -p "$PROFILE" plugins doctor \
  "$PROFILE_HOME/plugins/web-perplexity-pro" --ci
HERMES_HOME="$PROFILE_HOME" hermes -p "$PROFILE" plugins enable web-perplexity-pro
HERMES_HOME="$PROFILE_HOME" hermes -p "$PROFILE" perplexity-pro --help
```

Если native security/dependency gate отказывает — остановись и разберись
с сообщением. Не добавляй `--force` и не отключай проверки автоматически.
При ошибке любой команды не выполняй последующие шаги.
При существующем runtime/плагине используй проверенный сценарий обновления,
а не удаление каталогов и повторный login.

## Подключение поиска и авторизация

Сначала сохрани прежние значения и факт отсутствия настроек для rollback.
Выбор backend — отдельное намеренное изменение профиля:

```bash
HERMES_HOME="$PROFILE_HOME" hermes -p "$PROFILE" config get web.search_backend
HERMES_HOME="$PROFILE_HOME" hermes -p "$PROFILE" config set web.search_backend perplexity-pro

# Только сам пользователь в локальном интерактивном терминале:
HERMES_HOME="$PROFILE_HOME" hermes -p "$PROFILE" perplexity-pro login
HERMES_HOME="$PROFILE_HOME" hermes -p "$PROFILE" perplexity-pro status --online
```

Для `deep_research` включи toolset `perplexity-pro-research` через
`hermes -p "$PROFILE" tools`, если он не входит в используемый набор.
Новый login не нужен при обновлении с 0.2.0, если профильная сессия ещё валидна.
Не вводи токены/OTP/email через чат. Не перезапускай gateway автоматически.
Полная семантика, rollback и ограничения — в README и ASYNC_RESEARCH.md.

## Что не публикуется в Git

В Git включены исходники, тесты, фиксированные зависимости и Markdown-документация.
Окружения, `.env`, credentials/session stores, приватные research-результаты,
архивы dist и машинные JSON/log/HTML-диагностики исключены через .gitignore.
`docs/verification.json` и отчёты dist — локально генерируемые доказательства;
их отсутствие в checkout не означает наличие результатов live-проверки.
