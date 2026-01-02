import os
from dataclasses import dataclass
from typing import List
from dotenv import load_dotenv

load_dotenv()

@dataclass
class BotConfig:
    """إعدادات البوت الأساسية"""
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    ADMIN_IDS: List[int] = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x]
    WEBHOOK_URL: str = os.getenv("WEBHOOK_URL", "")
    
    @property
    def is_production(self) -> bool:
        return bool(self.WEBHOOK_URL)

@dataclass
class DatabaseConfig:
    """إعدادات قاعدة البيانات"""
    # خيارات: sqlite, postgres
    DB_TYPE: str = os.getenv("DB_TYPE", "sqlite")
    DB_HOST: str = os.getenv("DB_HOST", "")
    DB_PORT: str = os.getenv("DB_PORT", "")
    DB_NAME: str = os.getenv("DB_NAME", "delivery_bot")
    DB_USER: str = os.getenv("DB_USER", "")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "")
    
    @property
    def connection_string(self) -> str:
        if self.DB_TYPE == "postgres":
            return f"postgresql://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        else:
            return f"sqlite:///{self.DB_NAME}.db"

@dataclass
class PricingConfig:
    """إعدادات التسعير"""
    BASE_FARE: float = float(os.getenv("BASE_FARE", "5.0"))
    RATE_PER_KM: float = float(os.getenv("RATE_PER_KM", "2.0"))
    COMMISSION_RATE: float = float(os.getenv("COMMISSION_RATE", "0.2"))  # 20%
    MINIMUM_FARE: float = float(os.getenv("MINIMUM_FARE", "10.0"))

@dataclass
class DebtConfig:
    """إعدادات نظام المديونية"""
    MAX_DEBT_LIMIT: float = float(os.getenv("MAX_DEBT_LIMIT", "100.0"))
    DEBT_WARNING_THRESHOLD: float = float(os.getenv("DEBT_WARNING_THRESHOLD", "70.0"))
    AUTO_SUSPEND: bool = os.getenv("AUTO_SUSPEND", "true").lower() == "true"

@dataclass
class LocationConfig:
    """إعدادات الموقع الجغرافي"""
    SEARCH_RADIUS_KM: float = float(os.getenv("SEARCH_RADIUS_KM", "10.0"))
    LOCATION_UPDATE_INTERVAL: int = int(os.getenv("LOCATION_UPDATE_INTERVAL", "30"))
    EARTH_RADIUS_KM: float = 6371.0  # نصف قطر الأرض بالكيلومترات

@dataclass
class Config:
    """التكوين الرئيسي الذي يجمع جميع الإعدادات"""
    bot: BotConfig = BotConfig()
    database: DatabaseConfig = DatabaseConfig()
    pricing: PricingConfig = PricingConfig()
    debt: DebtConfig = DebtConfig()
    location: LocationConfig = LocationConfig()
    
    def validate(self):
        """التحقق من صحة الإعدادات"""
        if not self.bot.BOT_TOKEN:
            raise ValueError("يجب تعيين BOT_TOKEN في ملف .env")
        return True

# إنشاء كائن التكوين العام
config = Config()
