import os
from dataclasses import dataclass, field # تأكد من استيراد field
from typing import List
from dotenv import load_dotenv

load_dotenv()

# --- الفئات الفرعية (لا تغيير هنا) ---

@dataclass
class BotConfig:
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    ADMIN_IDS: List[int] = field(default_factory=lambda: [
        int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()
    ])
    WEBHOOK_URL: str = os.getenv("WEBHOOK_URL", "")
    @property
    def is_production(self) -> bool:
        return bool(self.WEBHOOK_URL)

@dataclass
class DatabaseConfig:
    DB_TYPE: str = os.getenv("DB_TYPE", "sqlite")
    DB_HOST: str = os.getenv("DB_HOST", "")
    DB_PORT: str = os.getenv("DB_PORT", "")
    DB_NAME: str = os.getenv("DB_NAME", "delivery_bot")
    DB_USER: str = os.getenv("DB_USER", "")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "")
    @property
    def connection_string(self) -> str:
        if self.DB_TYPE == "postgres":
            # إضافة psycopg2 لضمان التوافق مع SQLAlchemy في ريندر
            return f"postgresql+psycopg2://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        return f"sqlite:///{self.DB_NAME}.db"

@dataclass
class PricingConfig:
    BASE_FARE: float = float(os.getenv("BASE_FARE", "5.0"))
    RATE_PER_KM: float = float(os.getenv("RATE_PER_KM", "2.0"))
    COMMISSION_RATE: float = float(os.getenv("COMMISSION_RATE", "0.2"))
    MINIMUM_FARE: float = float(os.getenv("MINIMUM_FARE", "10.0"))

@dataclass
class DebtConfig:
    MAX_DEBT_LIMIT: float = float(os.getenv("MAX_DEBT_LIMIT", "100.0"))
    DEBT_WARNING_THRESHOLD: float = float(os.getenv("DEBT_WARNING_THRESHOLD", "70.0"))
    AUTO_SUSPEND: bool = os.getenv("AUTO_SUSPEND", "true").lower() == "true"

@dataclass
class LocationConfig:
    SEARCH_RADIUS_KM: float = float(os.getenv("SEARCH_RADIUS_KM", "10.0"))
    LOCATION_UPDATE_INTERVAL: int = int(os.getenv("LOCATION_UPDATE_INTERVAL", "30"))
    EARTH_RADIUS_KM: float = 6371.0

# --- الفئة الرئيسية (هنا التعديل الجذري) ---



@dataclass
class Config:
    """التكوين الرئيسي المصحح للعمل على السيرفر"""
    # نستخدم default_factory بدلاً من الإسناد المباشر
    bot: BotConfig = field(default_factory=BotConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    pricing: PricingConfig = field(default_factory=PricingConfig)
    debt: DebtConfig = field(default_factory=DebtConfig)
    location: LocationConfig = field(default_factory=LocationConfig)

    def validate(self):
        if not self.bot.BOT_TOKEN:
            raise ValueError("يجب تعيين BOT_TOKEN في متغيرات البيئة")
        return True

# إنشاء الكائن العام
config = Config()
