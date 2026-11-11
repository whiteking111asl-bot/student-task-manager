# Student Task Manager

Планувальник навчальних завдань для студентів. Підтримує реєстрацію, вхід і вихід, особисті списки, створення, редагування, видалення та зміну стану завдань. Можна шукати за назвою, поєднувати фільтри стану, категорії й пріоритету та сортувати за датою або пріоритетом.

Технології — Python, FastAPI, Uvicorn, SQLite, HTML, CSS і JavaScript.

## Запуск

Потрібні Python 3.12 або новіший, Git та браузер. Команди для Windows із кореня проєкту:

```powershell
git clone https://github.com/whiteking111asl-bot/student-task-manager.git
cd student-task-manager
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m uvicorn server.main:app --host 127.0.0.1 --port 8000
```

У Linux або macOS для створення середовища використайте `python3 -m venv .venv`, а в останніх двох командах — `.venv/bin/python`.

Відкрийте http://127.0.0.1:8000/. На першому запуску [SQL-скрипт](server/schema.sql) створить таблиці та категорії у `server/student_tasks.sqlite3`. Для тестової бази можна задати `STM_DATABASE` як шлях до файла в наявній папці. Файл бази виключено з Git.

## Демонстрація

Зареєструйте навчальний обліковий запис і створіть завдання з датою, категорією й пріоритетом. Змініть його статус і перевірте фільтр «Виконані». Створіть другий обліковий запис в іншому профілі браузера й перевірте, що він має власний список.

Категорії наперед визначені. Версія призначена для локального запуску. Відновлення пароля, підтвердження пошти й сповіщення відкладені.

[Результати перевірок](docs/mvp.md) · [Прототип Figma](https://www.figma.com/proto/VGoGwDsLOAimlexmmisqRK/Untitled?page-id=0%3A1&node-id=2-2&starting-point-node-id=2%3A2&scaling=min-zoom&content-scaling=fixed)

## Документація

- [Опис продукту та MVP](docs/product-description.md)
- [Вимоги](docs/requirements.md) і [перевірка вимог](docs/requirements-review.md)
- [Користувацькі історії](docs/user-stories.md)
- [Use-case модель](docs/use-case.md), [activity-діаграма](docs/activity-diagram.md) і [class-діаграма](docs/class-diagram.md)
- [Ескізи екранів](docs/screen-sketches.md) і [опис прототипу](docs/prototype.md)
- [Канбан-дошка](https://github.com/users/whiteking111asl-bot/projects/1/views/2)

**Автор — Руслан Махмадов, група 31 КНС.**
