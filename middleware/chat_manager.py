import logging
from typing import Dict, Optional
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, MessageHandler, filters, CallbackQueryHandler
from sqlalchemy.orm import Session

from database.models import Ride, RideStatus, ChatMessage, User
from database.database import db_manager

logger = logging.getLogger(__name__)

class ChatManager:
    """مدير الدردشة الوسيطة بين الراكب والسائق"""
    
    def __init__(self):
        self.session = db_manager.get_session_direct()
        self.active_chats: Dict[int, Dict] = {}  # ride_id -> chat_data
    
    def get_active_chat(self, user_id: int) -> Optional[Dict]:
        """الحصول على الدردشة النشطة للمستخدم"""
        for ride_id, chat_data in self.active_chats.items():
            if user_id in [chat_data.get('passenger_id'), chat_data.get('driver_id')]:
                return chat_data
        return None
    
    async def start_chat(self, ride_id: int, context: ContextTypes.DEFAULT_TYPE):
        """بدء دردشة جديدة لرحلة"""
        try:
            ride = self.session.query(Ride).get(ride_id)
            if not ride or ride.status != RideStatus.IN_PROGRESS:
                return False
            
            # إنشاء بيانات الدردشة
            chat_data = {
                'ride_id': ride_id,
                'passenger_id': ride.passenger.telegram_id,
                'driver_id': ride.driver.telegram_id,
                'started_at': datetime.utcnow(),
                'message_count': 0
            }
            
            self.active_chats[ride_id] = chat_data
            
            # إرسال رسالة بدء الدردشة للطرفين
            start_message = (
                "💬 **تم فتح قناة التواصل**\n\n"
                "يمكنك الآن التواصل مع الطرف الآخر بشكل آمن.\n"
                "جميع الرسائل تمر عبر النظام للحفاظ على خصوصية الأرقام.\n\n"
                "✍️ اكتب رسالتك وأرسلها كما العادة."
            )
            
            # للراكب
            await context.bot.send_message(
                chat_id=ride.passenger.telegram_id,
                text=start_message
            )
            
            # للسائق
            await context.bot.send_message(
                chat_id=ride.driver.telegram_id,
                text=start_message
            )
            
            logger.info(f"بدأت دردشة للرحلة {ride_id}")
            return True
            
        except Exception as e:
            logger.error(f"خطأ في بدء الدردشة: {e}")
            return False
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة الرسائل في الدردشة الوسيطة"""
        try:
            user_id = update.effective_user.id
            
            # البحث عن الدردشة النشطة
            chat_data = self.get_active_chat(user_id)
            if not chat_data:
                return  # ليس في دردشة نشطة
            
            # تحديد المستقبل
            if user_id == chat_data['passenger_id']:
                sender_role = "الراكب"
                recipient_id = chat_data['driver_id']
            else:
                sender_role = "السائق"
                recipient_id = chat_data['passenger_id']
            
            message_content = update.message.text or update.message.caption
            
            if not message_content:
                await update.message.reply_text("يجب إرسال نص في الرسالة.")
                return
            
            # حفظ الرسالة في قاعدة البيانات
            chat_message = ChatMessage(
                ride_id=chat_data['ride_id'],
                sender_id=user_id,
                content=message_content,
                message_type="text",
                extra_data={
                    'has_media': bool(update.message.photo or update.message.video or update.message.document),
                    'media_type': 'photo' if update.message.photo else 
                                 'video' if update.message.video else 
                                 'document' if update.message.document else None
                }
            )
            
            self.session.add(chat_message)
            self.session.commit()
            
            # زيادة عداد الرسائل
            chat_data['message_count'] += 1
            
            # إعادة توجيه الرسالة للمستقبل
            try:
                forwarded_message = (
                    f"💬 **رسالة من {sender_role}:**\n\n"
                    f"{message_content}\n\n"
                    f"───\n"
                    f"📨 يمكنك الرد مباشرة على هذه الرسالة."
                )
                
                await context.bot.send_message(
                    chat_id=recipient_id,
                    text=forwarded_message
                )
                
                # تحديث حالة الرسالة
                chat_message.is_delivered = True
                chat_message.delivered_at = datetime.utcnow()
                self.session.commit()
                
                # تأكيد الإرسال للمرسل
                await update.message.reply_text("✅ تم إرسال رسالتك.")
                
            except Exception as e:
                logger.error(f"خطأ في إعادة توجيه الرسالة: {e}")
                await update.message.reply_text("❌ فشل في إرسال الرسالة.")
            
        except Exception as e:
            logger.error(f"خطأ في معالجة رسالة الدردشة: {e}")
    
    async def end_chat(self, ride_id: int, context: ContextTypes.DEFAULT_TYPE):
        """إنهاء دردشة الرحلة"""
        try:
            chat_data = self.active_chats.get(ride_id)
            if not chat_data:
                return
            
            # إرسال رسالة إنهاء للطرفين
            end_message = (
                "🔒 **تم إغلاق قناة التواصل**\n\n"
                "انتهت الرحلة وأغلقت قناة التواصل.\n"
                f"عدد الرسائل المتبادلة: {chat_data['message_count']}\n\n"
                "شكراً لاستخدامكم خدمتنا! 🚕"
            )
            
            await context.bot.send_message(
                chat_id=chat_data['passenger_id'],
                text=end_message
            )
            
            await context.bot.send_message(
                chat_id=chat_data['driver_id'],
                text=end_message
            )
            
            # حذف الدردشة من الذاكرة
            del self.active_chats[ride_id]
            
            logger.info(f"أغلقت دردشة الرحلة {ride_id}")
            
        except Exception as e:
            logger.error(f"خطأ في إنهاء الدردشة: {e}")
    
    async def chat_commands(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """أوامر الدردشة"""
        try:
            user_id = update.effective_user.id
            
            # التحقق من وجود دردشة نشطة
            chat_data = self.get_active_chat(user_id)
            if not chat_data:
                await update.message.reply_text(
                    "ليس لديك أي دردشة نشطة.\n"
                    "يتم فتح الدردشة تلقائياً عند بدء الرحلة."
                )
                return
            
            # عرض معلومات الدردشة
            ride = self.session.query(Ride).get(chat_data['ride_id'])
            
            if user_id == chat_data['passenger_id']:
                other_party = ride.driver.first_name if ride.driver else "السائق"
            else:
                other_party = ride.passenger.first_name
            
            chat_info = (
                f"💬 **الدردشة النشطة**\n\n"
                f"مع: {other_party}\n"
                f"رقم الرحلة: {ride.ride_code}\n"
                f"الرسائل المتبادلة: {chat_data['message_count']}\n"
                f"بدأت منذ: {self._format_duration(chat_data['started_at'])}\n\n"
                f"يمكنك:\n"
                f"• إرسال الرسائل مباشرة\n"
                f"• إرسال الموقع: /send_location\n"
                f"• إنهاء الرحلة: /end_ride"
            )
            
            await update.message.reply_text(chat_info)
            
        except Exception as e:
            logger.error(f"خطأ في عرض أوامر الدردشة: {e}")
    
    def _format_duration(self, start_time: datetime) -> str:
        """تنسيق المدة الزمنية"""
        duration = datetime.utcnow() - start_time
        minutes = int(duration.total_seconds() / 60)
        
        if minutes < 60:
            return f"{minutes} دقيقة"
        else:
            hours = minutes // 60
            remaining = minutes % 60
            return f"{hours} ساعة و{remaining} دقيقة"
    
    def get_handlers(self):
        """الحصول على معالجات الدردشة"""
        return [
            CommandHandler("chat", self.chat_commands),
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message)
        ]
