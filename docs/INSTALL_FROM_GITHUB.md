# Установка 0.3.2 из GitHub

Ветка по умолчанию **plugin** — минимальный готовый native-пакет с manifest в
корне. Ветка **main** — исходники, тесты, диагностика и генератор этого пакета.
Правильный identifier теперь **dimarez/hermes-perplexity-pro**, без `/plugin`.
Имя после установки — **web-perplexity-pro**.

## Перед установкой

Нужны Linux, Git, uv, Python 3.13 и совместимый Hermes. Выбери существующий
целевой профиль явно. Не ставь второй экземпляр рядом со старой ручной
установкой `web/perplexity-pro`: сначала спланируй перенос кода, сохранив
профильные session/results. SDK-runtime остаётся отдельным от Python Hermes.

Ниже пример для стандартного default. Для named profile используй его имя и
соответствующий HERMES_HOME во всех шагах. Custom home задаётся явно.

```bash
hermes -p default plugins install dimarez/hermes-perplexity-pro --no-enable
```

Для воспроизводимости добавь `--ref` с точным 40-символьным SHA установочной
ветки plugin, не SHA исходников main. Флаг принимает commit, а не `v0.3.2`.

## CAUTION не скрывается

В минимальном пакете нет dev-тестов и диагностических скриптов. Однако остаются
необходимые возможности: отдельные worker-процессы, Linux descriptor checks и
скачивание SDK-зависимостей. Сканер вправе запросить доверие; это не обещание
нулевого риска. См. SECURITY.md внутри пакета и исходный код.

Если installer блокирует установку, остановись. Только после осознанного решения
доверять конкретному коммиту можно повторить команду с `--force`. Не отключай
сканирование глобально, не используй этот флаг автоматически или как способ
починить уязвимость. Разрешение на тест во временном профиле не разрешает
рабочую установку, login или live-запросы.

## Отдельный SDK-runtime после успешного скачивания кода

```bash
set -e
PROFILE_HOME="$HOME/.hermes"
PLUGIN="$PROFILE_HOME/plugins/web-perplexity-pro"
RUNTIME="$PROFILE_HOME/plugin-runtimes/perplexity-pro"
test -d "$PROFILE_HOME"
test -f "$PLUGIN/plugin.yaml"
test ! -e "$RUNTIME" && test ! -L "$RUNTIME"
mkdir -p "$PROFILE_HOME/plugin-runtimes"
uv venv --python 3.13 "$RUNTIME"
uv pip install --python "$RUNTIME/bin/python" -r "$PLUGIN/requirements-worker.lock.txt"
uv pip check --python "$RUNTIME/bin/python"
hermes -p default plugins doctor "$PLUGIN" --ci
hermes -p default plugins enable web-perplexity-pro
hermes -p default perplexity-pro --help
```

При ошибке любой команды не продолжай. Если runtime уже существует, проверь
его версию/lock и используй сценарий обновления, не удаление каталогов.
Обновление не должно стирать session store. Не ставь SDK в managed Hermes PM.

## Подключение и login — отдельные действия

Сохрани прежнее значение web.search_backend и факт отсутствия ключа для rollback.
Только затем выбери backend=perplexity-pro. Для deep_research при необходимости
включи toolset perplexity-pro-research через `hermes -p default tools`.
Пользователь сам выполняет `hermes -p default perplexity-pro login` локально в
интерактивном терминале; tokens/email/OTP через чат не передаются.
`status --online` и настоящие исследования требуют отдельного решения.
Автоматического перезапуска gateway, повторного research или уведомлений нет.

Local and online status in 0.3.2 show explicit Russian authorization labels while
retaining the same machine prefixes and exit codes. Email is echoed locally; use
`hermes -p default perplexity-pro login --show-codes` only if you deliberately want
OTP/TOTP echoed as well. Temporary codes are sensitive and terminal recording may
capture them. Default code entry remains hidden; no secret value is accepted in
command-line arguments. A previously saved valid session survives a code update:
login is not automatically required again.

## Разработка и публикация

Чтобы получить тесты и генератор, клонируй репозиторий с `--branch main`.
`python scripts/build_install_tree.py` генерирует dist/install из явного списка
runtime-файлов и безопасных сопроводительных файлов. SHA256SUMS позволяет
проверить байты. В установочной ветке не должно быть tests/scripts/docs/venv,
credentials, частных отчётов или машинной диагностики. Сборка не обфусцирует код
и не меняет guard-политику Hermes. Изменения в plugin делаются через main и
повторную генерацию, не независимыми правками двух веток.
