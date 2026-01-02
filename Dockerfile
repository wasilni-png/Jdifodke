# استخدام نسخة بايثون خفيفة ومستقرة
FROM python:3.11-slim

# تثبيت الأدوات الأساسية للنظام ومترجم Rust
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# تثبيت Rust لحل مشكلة Maturin و Pydantic
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"

# إعداد مجلد العمل
WORKDIR /app

# نسخ ملف المتطلبات وتثبيته
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# نسخ باقي ملفات المشروع
COPY . .

# أمر تشغيل البوت
CMD ["python", "bot.py"]
