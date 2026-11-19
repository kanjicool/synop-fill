# synop-fill (โหมดเสริม): image เล็ก ๆ ไม่ต้องมี Node/Tailwind เพราะ web/app.css คอมไพล์ไว้แล้วใน repo
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Asia/Bangkok

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY web/index.html web/app.js web/app.css ./web/
COPY templates ./templates

# ไม่รันด้วย root
RUN useradd --system --uid 10001 --no-create-home synop
USER synop

# port ภายใน container คงที่ 8000 ส่วน port ที่เปิดบนเครื่องตั้งที่ docker-compose.yml (SYNOP_PORT)
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
