from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.exc import SQLAlchemyError
from contextlib import contextmanager
import logging

from config import config
from database.models import Base

logger = logging.getLogger(__name__)

class DatabaseManager:
    """مدير قاعدة البيانات"""
    
    def __init__(self):
        self.engine = None
        self.session_factory = None
        self.Session = None
        
    def init_database(self):
        """تهيئة اتصال قاعدة البيانات"""
        try:
            # إنشاء المحرك
            connection_string = config.database.connection_string
            echo = not config.bot.is_production
            
            self.engine = create_engine(
                connection_string,
                echo=echo,
                pool_size=20,
                max_overflow=30,
                pool_pre_ping=True,
                pool_recycle=3600
            )
            
            if config.database.DB_TYPE == "sqlite":
                # تمكين المفاتيح الأجنبية لـ SQLite
                @event.listens_for(self.engine, "connect")
                def set_sqlite_pragma(dbapi_connection, connection_record):
                    cursor = dbapi_connection.cursor()
                    cursor.execute("PRAGMA foreign_keys=ON")
                    cursor.close()
            
            # إنشاء جداول قاعدة البيانات
            self._create_tables()
            
            # إنشاء جلسة العمل
            self.session_factory = sessionmaker(
                bind=self.engine,
                autocommit=False,
                autoflush=False
            )
            self.Session = scoped_session(self.session_factory)
            
            logger.info(f"تم تهيئة قاعدة البيانات: {config.database.DB_TYPE}")
            return True
            
        except Exception as e:
            logger.error(f"فشل في تهيئة قاعدة البيانات: {e}")
            raise
    
    def _create_tables(self):
        """إنشاء جداول قاعدة البيانات"""
        try:
            Base.metadata.create_all(bind=self.engine)
            logger.info("تم إنشاء/تحميل جداول قاعدة البيانات")
        except Exception as e:
            logger.error(f"فشل في إنشاء الجداول: {e}")
            raise
    
    @contextmanager
    def get_session(self):
        """الحصول على جلسة عمل مع إدارة السياق"""
        session = self.Session()
        try:
            yield session
            session.commit()
        except SQLAlchemyError as e:
            session.rollback()
            logger.error(f"خطأ في جلسة قاعدة البيانات: {e}")
            raise
        finally:
            session.close()
    
    def get_session_direct(self):
        """الحصول على جلسة عمل مباشرة (للاستخدام في الـ handlers)"""
        return self.Session()
    
    def close_session(self):
        """إغلاق جلسة العمل الحالية"""
        if self.Session:
            self.Session.remove()

# إنشاء كائن مدير قاعدة البيانات العام
db_manager = DatabaseManager()

# دالة مساعدة للحصول على الجلسة
def get_db():
    """دالة للحصول على جلسة قاعدة البيانات (للاستخدام مع Depends في FastAPI لاحقًا)"""
    session = db_manager.get_session_direct()
    try:
        yield session
    finally:
        session.close()
