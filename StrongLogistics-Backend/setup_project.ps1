# setup_project.ps1
# Automates the creation of the StrongLogistics-Backend environment

Write-Host "--- Initializing StrongLogistics-Backend ---" -ForegroundColor Cyan

# 1. Create Virtual Environment
if (-not (Test-Path "venv")) {
    Write-Host "Creating virtual environment..." -ForegroundColor Green
    python -m venv venv
}

# 2. Install Dependencies
Write-Host "Installing dependencies..." -ForegroundColor Green
.\venv\Scripts\pip install -r requirements.txt

# 3. Create Django Project & App
if (-not (Test-Path "core")) {
    Write-Host "Initializing Django project 'core'..." -ForegroundColor Green
    .\venv\Scripts\django-admin startproject core .
    .\venv\Scripts\python manage.py startapp logistics
}

# 4. Final Instructions
Write-Host "`nProject initialized successfully!" -ForegroundColor Yellow
Write-Host "To start development:" -ForegroundColor White
Write-Host "1. Activate venv: .\venv\Scripts\Activate.ps1" -ForegroundColor Cyan
Write-Host "2. Run migrations: python manage.py migrate" -ForegroundColor Cyan
Write-Host "3. Start server: python manage.py runserver" -ForegroundColor Cyan
