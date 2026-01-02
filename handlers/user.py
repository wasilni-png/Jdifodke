import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, filters, CallbackQueryHandler
from sqlalchemy.orm import Session

from config import config
from database.models import User, UserRole, UserStatus
from database.database import db_manager

logger = logging.getLogger(__name__)

class UserHandlers:
    """معالجات المستخدمين (التسجيل والتحكم الأساسي)"""
    
    def __init__(self):
        self.session = db_manager.get_session_direct()
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة أمر /start"""
        try:
            user_id = update.effective_user.id
            
            # التحقق إذا كان المستخدم مسجلاً مسبقاً
            existing_user = self.session.query(User).filter_by(
                telegram_id=user_id
            ).first()
            
            if existing_user:
                # ترحيب بالمستخدم المسجل
                await self._show_main_menu(update, context, existing_user)
                return
            
            # عرض خيارات التسجيل للمستخدم الجديد
            keyboard = [
                [
                    InlineKeyboardButton("🚖 سائق", callback_data="register_driver"),
                    InlineKeyboardButton("👤 راكب", callback_data="register_passenger")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            welcome_message = (
                "مرحباً بك في خدمة التوصيل! 🚕\n\n"
                "اختر نوع الحساب المناسب لك:\n"
                "• 🚖 سائق: لتقديم خدمات التوصيل\n"
                "• 👤 راكب: لطلب الرحلات\n\n"
                "ملاحظة: يمكنك تغيير نوع الحساب لاحقاً."
            )
            
            await update.message.reply_text(
                welcome_message,
                reply_markup=reply_markup
            )
            
        except Exception as e:
            logger.error(f"خطأ في معالجة start: {e}")
            await update.message.reply_text("حدث خطأ، يرجى المحاولة لاحقاً.")
    
    async def register_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة اختيار نوع المستخدم"""
        try:
            query = update.callback_query
            await query.answer()
            
            user_data = query.from_user
            role = query.data.replace("register_", "")
            
            # التحقق من الصلاحية
            if role not in ["driver", "passenger"]:
                await query.edit_message_text("اختيار غير صالح.")
                return
            
            # التحقق من عدم التسجيل مسبقاً
            existing_user = self.session.query(User).filter_by(
                telegram_id=user_data.id
            ).first()
            
            if existing_user:
                await query.edit_message_text(
                    f"أنت مسجل بالفعل كـ {existing_user.role.value}"
                )
                return
            
            # إنشاء مستخدم جديد
            new_user = User(
                telegram_id=user_data.id,
                username=user_data.username,
                first_name=user_data.first_name or "",
                last_name=user_data.last_name or "",
                role=UserRole(role),
                status=UserStatus.ACTIVE
            )
            
            self.session.add(new_user)
            self.session.commit()
            
            # رسالة الترحيب حسب الدور
            if role == "driver":
                message = (
                    "🎉 تم تسجيلك كسائق بنجاح!\n\n"
                    "الآن يمكنك:\n"
                    "• تفعيل وضع السائق: /driver_on\n"
                    "• تحديث ملفك الشخصي: /profile\n"
                    "• الاطلاع على الدخل: /earnings\n\n"
                    "ملاحظة: يجب إكمال ملفك الشخصي قبل البدء بالعمل."
                )
            else:
                message = (
                    "🎉 تم تسجيلك كراكب بنجاح!\n\n"
                    "الآن يمكنك:\n"
                    "• طلب رحلة: /request_ride\n"
                    "• تعيين موقعك: /set_location\n"
                    "• مشاهدة الرحلات السابقة: /my_rides\n\n"
                    "مرحباً بك في خدمتنا!"
                )
            
            await query.edit_message_text(message)
            
        except Exception as e:
            logger.error(f"خطأ في تسجيل المستخدم: {e}")
            self.session.rollback()
            await query.edit_message_text("حدث خطأ في التسجيل.")
    
    async def _show_main_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE, user: User):
        """عرض القائمة الرئيسية حسب دور المستخدم"""
        if user.role == UserRole.DRIVER:
            keyboard = [
                [InlineKeyboardButton("🚖 تفعيل/تعطيل العمل", callback_data="toggle_work")],
                [InlineKeyboardButton("📊 إحصائياتي", callback_data="driver_stats")],
                [InlineKeyboardButton("💰 رصيدي ومديونيتي", callback_data="driver_finance")],
                [InlineKeyboardButton("📝 تحديث الملف الشخصي", callback_data="update_profile")]
            ]
            message = f"مرحباً بك مجدداً يا {user.first_name}!\n\nأنت مسجل كسائق."
        
        elif user.role == UserRole.PASSENGER:
            keyboard = [
                [InlineKeyboardButton("📍 طلب رحلة", callback_data="request_ride")],
                [InlineKeyboardButton("🗺️ تعيين موقعي", callback_data="set_location")],
                [InlineKeyboardButton("📋 رحلاتي", callback_data="my_rides")],
                [InlineKeyboardButton("⭐ تقييماتي", callback_data="my_ratings")]
            ]
            message = f"مرحباً بك مجدداً يا {user.first_name}!\n\nأنت مسجل كراكب."
        
        else:  # ADMIN
            keyboard = [
                [InlineKeyboardButton("👨‍💼 لوحة التحكم", callback_data="admin_panel")],
                [InlineKeyboardButton("📊 إحصائيات النظام", callback_data="system_stats")]
            ]
            message = f"مرحباً بالأدمن {user.first_name}!"
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if update.callback_query:
            await update.callback_query.edit_message_text(
                message,
                reply_markup=reply_markup
            )
        else:
            await update.message.reply_text(
                message,
                reply_markup=reply_markup
            )
    
    async def set_location(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """طلب تحديد الموقع من المستخدم"""
        keyboard = [
            [InlineKeyboardButton("📍 إرسال موقعي الحالي", request_location=True)]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "رجاءً أرسل موقعك الحالي لتحديد أقرب السائقين لك:",
            reply_markup=reply_markup
        )
    
    async def handle_location(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة الموقع المرسل من المستخدم"""
        try:
            location = update.message.location
            user_id = update.effective_user.id
            
            user = self.session.query(User).filter_by(telegram_id=user_id).first()
            if not user:
                await update.message.reply_text("لم يتم العثور على حسابك.")
                return
            
            # تحديث الموقع
            user.latitude = location.latitude
            user.longitude = location.longitude
            user.location_updated_at = datetime.utcnow()
            
            self.session.commit()
            
            await update.message.reply_text(
                "✅ تم تحديث موقعك بنجاح!\n\n"
                f"الإحداثيات: {location.latitude}, {location.longitude}"
            )
            
        except Exception as e:
            logger.error(f"خطأ في تحديث الموقع: {e}")
            await update.message.reply_text("حدث خطأ في تحديث الموقع.")
    
    async def my_profile(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """عرض الملف الشخصي"""
        try:
            user_id = update.effective_user.id
            user = self.session.query(User).filter_by(telegram_id=user_id).first()
            
            if not user:
                await update.message.reply_text("لم يتم العثور على حسابك.")
                return
            
            profile_text = (
                f"👤 **الملف الشخصي**\n\n"
                f"الاسم: {user.first_name} {user.last_name or ''}\n"
                f"اسم المستخدم: @{user.username or 'غير محدد'}\n"
                f"الدور: {user.role.value}\n"
                f"الحالة: {user.status.value}\n"
                f"رقم الهاتف: {user.phone or 'غير محدد'}\n"
                f"إجمالي الرحلات: {user.total_rides}\n"
                f"التقييم: {'⭐' * int(user.rating)}\n"
                f"تاريخ التسجيل: {user.created_at.strftime('%Y-%m-%d')}\n"
            )
            
            if user.role == UserRole.DRIVER and user.driver_profile:
                profile_text += (
                    f"\n🚖 **معلومات السائق:**\n"
                    f"نوع المركبة: {user.driver_profile.vehicle_type or 'غير محدد'}\n"
                    f"حالة العمل: {'🟢 متاح' if user.driver_profile.is_available else '🔴 غير متاح'}\n"
                    f"المديونية: {user.driver_profile.current_debt:.2f} ريال\n"
                    f"إجمالي الدخل: {user.driver_profile.total_earnings:.2f} ريال"
                )
            
            await update.message.reply_text(profile_text)
            
        except Exception as e:
            logger.error(f"خطأ في عرض الملف الشخصي: {e}")
    
    def get_handlers(self):
        """الحصول على جميع معالجات المستخدمين"""
        return [
            CommandHandler("start", self.start),
            CommandHandler("profile", self.my_profile),
            CommandHandler("set_location", self.set_location),
            CallbackQueryHandler(self.register_user, pattern="^register_"),
            MessageHandler(filters.LOCATION, self.handle_location)
        ]
