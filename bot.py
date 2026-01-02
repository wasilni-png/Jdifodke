#!/usr/bin/env python3
"""
نقطة الدخول الرئيسية لتطبيق بوت التوصيل
"""

import logging
import asyncio
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler
from telegram.error import TelegramError

from config import config
from database.database import db_manager

# استيراد المعالجات
from handlers.user import UserHandlers
from handlers.driver import DriverHandlers
from handlers.ride import RideHandlers
from handlers.admin import AdminHandlers
from middleware.chat_manager import ChatManager

# إعداد التسجيل
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class DeliveryBot:
    """الفئة الرئيسية للبوت"""
    
    def __init__(self):
        self.application = None
        self.user_handlers = None
        self.driver_handlers = None
        self.ride_handlers = None
        self.admin_handlers = None
        self.chat_manager = None
    
    def init_app(self):
        """تهيئة تطبيق البوت"""
        try:
            # التحقق من التكوين
            config.validate()
            
            # تهيئة قاعدة البيانات
            db_manager.init_database()
            
            # إنشاء تطبيق البوت
            self.application = Application.builder().token(config.bot.BOT_TOKEN).build()
            
            # إنشاء المعالجات
            self.user_handlers = UserHandlers()
            self.driver_handlers = DriverHandlers()
            self.ride_handlers = RideHandlers()
            self.admin_handlers = AdminHandlers()
            self.chat_manager = ChatManager()
            
            # تسجيل المعالجات
            self._register_handlers()
            
            logger.info("تم تهيئة البوت بنجاح")
            return True
            
        except Exception as e:
            logger.error(f"فشل في تهيئة البوت: {e}")
            return False
    
    def _register_handlers(self):
        """تسجيل جميع معالجات البوت"""
        
        # معالجات المستخدمين
        user_handlers = self.user_handlers.get_handlers()
        for handler in user_handlers:
            self.application.add_handler(handler)
        
        # معالجات السائقين
        driver_handlers = self.driver_handlers.get_handlers()
        for handler in driver_handlers:
            self.application.add_handler(handler)
        
        # معالجات الرحلات
        ride_handlers = self.ride_handlers.get_handlers()
        for handler in ride_handlers:
            self.application.add_handler(handler)
        
        # معالجات الأدمن
        admin_handlers = self.admin_handlers.get_handlers()
        for handler in admin_handlers:
            self.application.add_handler(handler)
        
        # معالجات الدردشة
        chat_handlers = self.chat_manager.get_handlers()
        for handler in chat_handlers:
            self.application.add_handler(handler)
        
        # معالجة الأخطاء
        self.application.add_error_handler(self.error_handler)
        
        # معالجة الرسائل العامة
        self.application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            self.handle_unknown_message
        ))
    
    async def error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE):
        """معالجة الأخطاء العامة"""
        try:
            raise context.error
        except TelegramError as e:
            logger.error(f"خطأ في التيليجرام: {e}")
        except Exception as e:
            logger.error(f"خطأ غير متوقع: {e}", exc_info=True)
            
            # إرسال رسالة خطأ للمستخدم إذا كان هناك تحديث
            if update and hasattr(update, 'effective_chat'):
                try:
                    await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text="حدث خطأ غير متوقع. يرجى المحاولة لاحقاً."
                    )
                except:
                    pass
    
    async def handle_unknown_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة الرسائل غير المعروفة"""
        await update.message.reply_text(
            "لم أفهم رسالتك. 🤔\n\n"
            "يمكنك استخدام الأوامر التالية:\n"
            "/start - بدء البوت\n"
            "/help - المساعدة\n"
            "/menu - القائمة الرئيسية"
        )
    
    async def on_startup(self, application: Application):
        """الإجراءات عند بدء التشغيل"""
        logger.info("بدء تشغيل البوت...")
        
        # إرسال إشعار للأدمن
        for admin_id in config.bot.ADMIN_IDS:
            try:
                await application.bot.send_message(
                    chat_id=admin_id,
                    text="🟢 تم بدء تشغيل بوت التوصيل بنجاح!"
                )
            except Exception as e:
                logger.error(f"فشل في إرسال إشعار للأدمن {admin_id}: {e}")
    
    async def on_shutdown(self, application: Application):
        """الإجراءات عند إيقاف التشغيل"""
        logger.info("إيقاف تشغيل البوت...")
        
        # إغلاق جلسات قاعدة البيانات
        db_manager.close_session()
        
        # إرسال إشعار للأدمن
        for admin_id in config.bot.ADMIN_IDS:
            try:
                await application.bot.send_message(
                    chat_id=admin_id,
                    text="🔴 تم إيقاف بوت التوصيل."
                )
            except Exception as e:
                logger.error(f"فشل في إرسال إشعار للأدمن {admin_id}: {e}")
    
    def run(self):
        """تشغيل البوت"""
        if not self.init_app():
            logger.error("فشل في تهيئة البوت. الخروج...")
            return
        
        try:
            # إضافة معالجات البداية والنهاية
            self.application.run_polling(
                on_startup=self.on_startup,
                on_shutdown=self.on_shutdown,
                allowed_updates=[
                    "message",
                    "callback_query",
                    "inline_query",
                    "chosen_inline_result",
                    "channel_post",
                    "edited_message",
                    "edited_channel_post"
                ],
                drop_pending_updates=True
            )
            
        except KeyboardInterrupt:
            logger.info("تم إيقاف البوت بواسطة المستخدم.")
        except Exception as e:
            logger.error(f"فشل في تشغيل البوت: {e}")
        finally:
            logger.info("إيقاف جميع العمليات...")


def main():
    """الدالة الرئيسية"""
    bot = DeliveryBot()
    bot.run()


if __name__ == "__main__":
    main()
