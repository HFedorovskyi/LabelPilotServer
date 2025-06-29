
FROM python:3.12-slim

# Установите необходимые пакеты и зависимости
RUN pip install --no-cache-dir flower

# Установите рабочую директорию
WORKDIR /app

# Откройте порт для Flower
EXPOSE 5555

# Установите переменные окружения (опционально)
ENV FLOWER_PORT=5555
ENV FLOWER_BROKER_URL=redis://:1234@redis:6379/0


# Команда по умолчанию для запуска Flower
CMD ["python", "-m", "flower", "--broker=redis://:1234@redis:6379/0"]