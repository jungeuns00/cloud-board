FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# 의존성 레이어를 먼저 만들어 코드만 바뀔 때 캐시를 재사용한다
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# root가 아닌 사용자로 실행
RUN useradd --uid 10001 --no-create-home appuser
USER 10001

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
