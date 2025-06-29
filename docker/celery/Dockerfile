# docker/celery/Dockerfile

FROM python:3.12-slim

WORKDIR /code

# Копирование и установка зависимостей Python
COPY requirements.txt /code/
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# Копирование проекта
COPY . /code/
# Создание пользователя для безопасности и изменение владельца файлов
RUN adduser --disabled-password --gecos "" myuser && \
    chown -R myuser:myuser /code

# Переключение на нового пользователя
USER myuser

# Открытие порта для приложения
EXPOSE 8000

# Команда по умолчанию (будет переопределена в docker-compose.yml)
CMD ["celery", "-A", "LabelPilotServer", "worker", "-l", "info", "-P", "eventlet"]
