# План: отдельный инструмент deep_research

Статус: исторический исходный план. Пользователь затем согласовал минимальный async start/status/result; актуальный контракт — ASYNC_RESEARCH.md, результаты — EVIDENCE.md и REVIEW.md. Синхронный интерфейс ниже не является контрактом 0.3.0.
Предлагаемая версия: 0.3.0 поверх существующей 0.2.0.

## Цель и согласованная часть

Агент должен по явному исследовательскому запросу вызвать **deep_research**, получить полный отчёт Perplexity с источниками и передать его пользователю, не ухудшая обычный web_search. Это и есть целевой результат, а не просто наличие нового имени в списке tools.

Подтверждено пользователем: точное имя `deep_research`, самостоятельный инструмент.
Отклонено: имя `perplexity_research`, подмена обычного поиска исследованием.
Не согласовано: отдельный Telegram-бот/профиль researcher, автозапуск работ, production-изменения, live-вызовы с расходом квоты.

## Исходный материал и границы

- Проект в текущем backend: `/workspace/develop/hermes-perplexity-pro`.
- Ранее подтверждённый host mapping: `/home/hermes/Develop/hermes-perplexity-pro`; перед передачей и любыми host-действиями перепроверить runtime mapping.
- Manifest прочитан: версия 0.2.0, `python_runtime: external`, provider perplexity-pro.
- Исходный архив 0.2.0 существует; фактический SHA-256: `7a9799812366fb478f5d0b197e028ace06d7d12c2623e4f3c37bc2e616f88e27`.
- Изучены реальные `plugin/{__init__,provider,worker,protocol}.py`, tests, build/verify scripts и установленный pinned SDK.
- SDK pin: e34b5082d6c16283358d8a1e3cbd7fa61c35fc0d. Есть `Models.DEEP_RESEARCH`, `ResearchClarifyingQuestionsError`, загрузка отдельного Markdown-отчёта.
- Важная исходная особенность SDK: `_fetch_research_report()` может скрыть ошибку скачивания и оставить intro. Нельзя выдавать такое вступление за полный готовый отчёт.
- В текущем backend отсутствует `/workspace/develop/hermes-agent-reference`. Восстановление тестового reference — prerequisite, а не доказанный доступ к рабочему Hermes.
- Предыдущие 91 offline-тест — baseline из отчёта 0.2.0, не evidence новой реализации. Набор нужно запускать заново.

## Предлагаемый контракт первой версии

`deep_research(query, timeout_seconds=900)` — пример проектируемого интерфейса, пока не существующая команда.

- query: непустая строка, ограничение длины до 16000 символов.
- timeout_seconds: целое число 60..1800, default 900; bool/строки не принимаются. Проверить совместимость с host tool/deadline до реализации. Эти значения — предложения плана, не измеренная длительность Perplexity.
- Успех: `status=completed`, полный Markdown, источники, идентификатор/путь локального отчёта, явный признак получения полного отчёта.
- Для длинного ответа: сохранить полный приватный `.md` в профильном каталоге результатов; в tool-response вернуть ограниченный preview, путь и признак truncation. Не подменять полный текст сокращённым без маркировки. Принимать путь от модели не требуется.
- Уточняющие вопросы: `status=needs_clarification`, список вопросов. В первой версии не обещать продолжение той же удалённой research-сессии: это отдельная функция после проверки протокола SDK. Не перезапускать исследование автоматически.
- Ошибки: недоступная сессия, 403, квота, timeout, неполный отчёт, ошибка runtime/протокола/сохранения — структурированный отказ без raw exception/auth payload.
- Один явный вызов — одна попытка исследования. Нет скрытого retry, платного API/OpenAI fallback или запуска другого backend.

## Этапы и зависимости

Работы выполнять последовательно одним владельцем проекта. Независимому reviewer разрешено чтение; параллельные writer в тех же файлах запрещены.

### DR-01. Восстановить тестовую базу и зафиксировать API — P0

Владелец: coder. Зависимости: разрешение на реализацию.

1. Проверить реальный backend, текущие файлы и отсутствие другого writer; сохранить hashes и исходный ZIP 0.2.0.
2. Подготовить read-only pinned Hermes reference отдельно от рабочей установки; проверить официальный `PluginContext.register_tool`, toolset exposure, handler return/cancellation/deadline contracts, collision с существующим `deep_research`.
3. Запустить baseline suite. Проверить реальный вызов SDK Deep Research и способ доказать загрузку полного отчёта без опоры на длину текста.

Приёмка: baseline проходит; записаны точные Python/reference paths, фактический tool contract и ограничения длительности. Если host обрывает синхронный вызов раньше research deadline, остановить решение о sync и согласовать асинхронный контракт, не маскировать проблему увеличением одного SDK timeout.
Проверяющий: pytest, исходник registry/loader и настоящий doctor, а не текст этого плана.

### DR-02. Реализовать research worker и проверку полного результата — P0

Владелец: coder. Зависимость: DR-01.

- Вынести исследование в отдельный модуль/worker, переиспользуя profile-owned SDK runtime, SessionStore и безопасное подавление dependency-output.
- Не менять `PerplexityProProvider.search(query, limit)` и Sonar-режим обычного поиска.
- Выбрать Deep Research явно; передать токен только из активного профильного store. Никаких shared/env fallback или интерактивного login из инструмента.
- Применить согласованные HTTP/process deadlines. Отмена/timeout должны завершать локальное ожидание и worker; это не обещание отмены уже принятого задания на стороне Perplexity или возврата квоты.
- Явно различать полный отчёт и intro-only. При необходимости — узкий проверяемый адаптер к pinned SDK, не форк всего клиента и не эвристика «длинный текст значит готово».
- Вернуть уточняющие вопросы, безопасные ошибки и реальные источники; исключить auth поля и подписанные служебные download URLs из метаданных ответа.

Тесты RED→GREEN: `test_research_uses_deep_model`, `test_research_uses_only_profile_session`, `test_intro_only_is_not_completed`, `test_report_download_failure_is_explicit`, `test_research_clarification_is_returned`, `test_research_quota_timeout_errors_are_sanitized`, `test_research_has_no_retry_or_fallback`.
Проверяющий: pytest с настоящими типами SDK и подменой только сетевой границы. Live-работоспособность этими тестами не доказывается.

### DR-03. Зарегистрировать deep_research и выдавать артефакт — P0

Владелец: coder. Зависимость: DR-02.

- Зарегистрировать точное model-facing имя `deep_research`, schema, description, availability check и handler через поддержанный plugin API.
- Обеспечить exposure в нужном toolset. Не заменять одноимённый чужой/core tool при конфликте: явный отказ загрузки и отдельное решение пользователя.
- Сохранять полный Markdown атомарно под profile-owned results root, с приватными правами и генерируемым именем. Защита от symlink/path traversal и перезаписи чужого файла.
- Ограничивать preview с явной маркировкой. Ошибка записи не должна возвращаться как полноценный успех с несуществующим файлом.
- Проверить реальную регистрацию и native invocation через настоящий loader/registry; по возможности model tool-dispatch. Это не новая MCP-команда и не только локальный CLI.

Тесты: `test_deep_research_exact_tool_registration`, `test_tool_exposure_and_collision_refusal`, `test_invalid_research_input_never_starts_worker`, `test_report_saved_in_active_profile`, `test_preview_does_not_lose_full_report`, `test_report_path_refuses_symlink_escape`, `test_report_write_failure_is_not_success`.
Регрессии: все прежние search/auth/isolation tests, обычный `web_search` и `web_extract` не меняют контракт/маршрутизацию.
Проверяющий: реальный loader/doctor/registry плюс файлы, считанные с диска, и pytest assertions.

### DR-04. Review, portable release и инструкция — P0

Владелец интеграции: coder. Зависимость: DR-03. Reviewer: отдельный read-only проход; при недоступности явно отметить отсутствие независимой проверки.

- Обновить README: когда использовать инструмент, синхронные ограничения, deadline, уточнения, стоимость/квота без неподтверждённых цифр, приватность отчётов, ручное подключение и rollback.
- Проверить адаптер скачивания отчёта: безопасный HTTP(S)/origin/redirect policy, отсутствие передачи session credentials внешнему CDN, границы доверия к содержимому Markdown.
- Выполнить весь suite, doctor, dependency check, тесты очистки процессов/временных файлов. Не считать успешный exit evidence получения полного отчёта без соответствующих assertions.
- Собрать 0.3.0 без venv, cookies, токенов, настоящих отчётов и env. Переустановить fixed SDK в свежий runtime, распаковать точные финальные ZIP bytes вне исходной папки и повторить acceptance.
- Записать hashes, точные команды, stdout/exit statuses, состояние review, отсутствующие live checks. Сохранить 0.2.0 и инструкцию rollback.

Базовые команды после определения действительного `HERMES_REFERENCE`:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$HERMES_REFERENCE" .venv/bin/python -m pytest -q tests --tb=short
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$HERMES_REFERENCE" .venv/bin/python scripts/verify.py
.venv/bin/python scripts/build_release.py
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$HERMES_REFERENCE" .venv/bin/python scripts/portable_check.py --archive dist/hermes-perplexity-pro-0.3.0.zip --report dist/verification-final.json
.venv/bin/python scripts/attest_release.py
```

Это планируемые команды; ещё не запускались для deep_research. Скрипты обновляются под новый tool, а не используются со старыми ожиданиями `0 tools`.

### DR-05. Отдельно согласованный live smoke — acceptance gate

Владелец: пользователь + coder. Зависимость: DR-04 и отдельное разрешение.

Сам пользователь выполняет вход выбранного профиля в локальном терминале. Затем один небольшой публичный research-запрос с заранее согласованной темой и лимитом времени/попыток. Проверить полный отчёт, источники, файл, расход соответствующей квоты и настоящий tool-routing. Не запрашивать secrets в чате и не менять 2FA.

Если разрешения/сессии нет: локальная реализация может быть передана с честным `live not run`; end-to-end сервисная работоспособность остаётся непроверенной. Не превращать offline fixtures в live evidence.
Проверяющий: фактический ответ Perplexity и файл отчёта; пользователь оценивает содержательность/источники, а не только тесты.

## Следующие независимые решения, не включённые в MVP

1. **Фоновые задания:** start/status/result, durable state и рестарт recovery. Не использовать process-local субагента как обещание durable job. Сначала проверить возможности upstream resume/cancel; после неопределённого обрыва не отправлять запрос повторно автоматически. Это отдельная согласуемая доработка после DR-04; не скрытая часть MVP.
2. **Профиль researcher:** постоянная исследовательская роль с собственным контекстом и инструментами. После выбора пользователем: роль/модель/инструменты/правила источников, отдельная профильная авторизация и тест поручения исследования. Он использует `deep_research`, а не заменяет его.
3. **Telegram researcher bot:** только если выбран отдельный собеседник. Токен, группы, allowlists и разрешения подключаются отдельно с согласием; не создаются автоматически из этого плана.

## Review Focus

- Intro без полного report при поглощённой SDK ошибке → явный incomplete, DR-02 тест.
- Worker убит/соединение потеряно после принятия remote query → ambiguous, без автоматической повторной траты, DR-02 тест.
- Чужая сессия/профиль либо output-path escape → fail closed, DR-02/03 tests.
- Конфликт имени deep_research или tool отсутствует в exposure → явный отказ, DR-01/03 integration test.
- Новый tool ошибочно сертифицирован старыми packaging expectations → DR-04 проверяет реальные registry entries и точный ZIP.

## Разрешения и готовность

В рамках этого запроса созданы только план и карточка планирования. Не разрешены и не выполняются: изменение рабочего Hermes/config/профилей, активация plugin, создание бота/бот-токена, interactive auth, live расход квоты, restart gateway, публикация.

План не является реализацией. Перед началом исполнения нужны явная команда пользователя на запуск и проверка единственного владельца файлов. Одобрение опциональных researcher/background/Telegram этапов не предполагается из одобрения `deep_research`.
