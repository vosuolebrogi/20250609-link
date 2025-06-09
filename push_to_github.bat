@echo off
echo ===========================================
echo  Pushing Telegram Bot to GitHub
echo ===========================================
echo.

REM Проверяем наличие Git
where git >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Git не найден! Пожалуйста, установите Git:
    echo https://git-scm.com/download/win
    echo.
    pause
    exit /b 1
)

echo [INFO] Git найден, продолжаем...
echo.

REM Инициализируем репозиторий
echo [STEP 1] Инициализация Git репозитория...
git init

REM Добавляем remote origin
echo [STEP 2] Добавление remote репозитория...
git remote add origin https://github.com/vosuolebrogi/20250609-link.git

REM Добавляем все файлы
echo [STEP 3] Добавление файлов...
git add .

REM Проверяем статус
echo [STEP 4] Статус репозитория:
git status

REM Создаем коммит
echo [STEP 5] Создание коммита...
git commit -m "Initial commit: Telegram bot for Yandex Go links"

REM Создаем и переключаемся на main ветку
echo [STEP 6] Переключение на main ветку...
git branch -M main

REM Push в репозиторий
echo [STEP 7] Отправка в GitHub...
git push -u origin main

echo.
echo ===========================================
echo  Готово! Код загружен на GitHub
echo ===========================================
echo.
pause 