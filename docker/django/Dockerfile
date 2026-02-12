# docker/django/Dockerfile

FROM python:3.12-slim


RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        ghostscript && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Установка рабочей директории
WORKDIR /code

# Копирование и установка зависимостей Python
COPY requirements.txt /code/
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# Копирование проекта
COPY . /code/
RUN python manage.py collectstatic --noinput
# Создание пользователя для безопасности и изменение владельца файлов
RUN adduser --disabled-password --gecos "" myuser && \
    chown -R myuser:myuser /code

# Переключение на нового пользователя
USER myuser

# Открытие порта для приложения
EXPOSE 8000

# Команда по умолчанию
CMD ["gunicorn", "LabelPilotServer.wsgi:application", "--bind", "0.0.0.0:8000", "--reload"]
