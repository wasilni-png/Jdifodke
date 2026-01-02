import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler
from sqlalchemy.orm import Session

from database.models import User, UserRole, DriverProfile
from database.database import db_manager
from utils.debt_system import DebtManager

logger = logging.getLogger(__name__)

class DriverHandlers:
    """معالجات السائقين"""
    
    def __init__(self):
        self.session = db_manager.get_session_direct()
        self.debt_manager = DebtManager(self.session)
    
    async def toggle_driver_mode(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """تفعيل/تعطيل وضع السائق"""
        try:
            user_id = update.effective_user.id
            
            user = self.session.query(User).filter_by(
                telegram_id=user_id,
                role=UserRole.DRIVER
            ).first()
            
            if not user:
                await update.message.reply_text("أنت لست مسجلاً كسائق.")
                return
            
            driver_profile = user.driver_profile
            if not driver_profile:
                await update.message.reply_text("يجب إكمال ملف السائق أولاً.")
                return
            
            # التحقق من المديونية
            debt_summary = self.debt_manager.get_driver_debt_summary(user.id)
            if not debt_summary.get('can_work', False):
                await update.message.reply_text(
                    f"لا يمكنك العمل بسبب المديونية.\n"
                    f"المديونية الحالية: {debt_summary['current_debt']:.2f} ريال\n"
                    f"الحد الأقصى المسموح: {debt_summary['debt_limit']} ريال\n\n"
                    f"الرجاء السداد أولاً."
                )
                return
            
            # تبديل الحالة
            driver_profile.is_online = not driver_profile.is_online
            status = "🟢 مفعل" if driver_profile.is_online else "🔴 معطل"
            
            self.session.commit()
            
            await update.message.reply_text(
                f"✅ تم {status} وضع السائق\n\n"
                f"الحالة الآن: {'متاح للرحلات' if driver_profile.is_online else 'غير متاح'}"
            )
            
        except Exception as e:
            logger.error(f"خطأ في تبديل وضع السائق: {e}")
            await update.message.reply_text("حدث خطأ.")
    
    async def accept_ride(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """قبول رحلة"""
        try:
            if not context.args:
                await update.message.reply_text("الرجاء تحديد رقم الرحلة: /accept_ride <رقم_الرحلة>")
                return
            
            ride_id = context.args[0]
            user_id = update.effective_user.id
            
            # التحقق من هوية السائق
            driver = self.session.query(User).filter_by(
                telegram_id=user_id,
                role=UserRole.DRIVER
            ).first()
            
            if not driver or not driver.driver_profile:
                await update.message.reply_text("أنت لست مسجلاً كسائق.")
                return
            
            if not driver.driver_profile.is_online:
                await update.message.reply_text("يجب تفعيل وضع السائق أولاً.")
                return
            
            # البحث عن الرحلة
            from database.models import Ride, RideStatus
            ride = self.session.query(Ride).filter_by(
                id=ride_id,
                status=RideStatus.PENDING
            ).first()
            
            if not ride:
                await update.message.reply_text("الرحلة غير موجودة أو تم قبولها مسبقاً.")
                return
            
            # قبول الرحلة
            ride.driver_id = driver.id
            ride.status = RideStatus.ACCEPTED
            ride.accepted_at = datetime.utcnow()
            
            driver.driver_profile.current_ride_id = ride.id
            driver.driver_profile.is_available = False
            
            self.session.commit()
            
            # إرسال إشعار للراكب
            await context.bot.send_message(
                chat_id=ride.passenger.telegram_id,
                text=f"✅ تم قبول رحلتك!\n\n"
                     f"السائق: {driver.first_name}\n"
                     f"رقم الرحلة: {ride.ride_code}\n"
                     f"سيتم التواصل معك قريباً."
            )
            
            await update.message.reply_text(
                f"✅ تم قبول الرحلة رقم {ride.ride_code}\n\n"
                f"تفاصيل الرحلة:\n"
                f"الراكب: {ride.passenger.first_name}\n"
                f"التكلفة التقديرية: {ride.estimated_fare:.2f} ريال\n"
                f"المسافة: {ride.distance_km:.2f} كم\n\n"
                f"يمكنك التواصل مع الراكب عبر: /chat"
            )
            
        except Exception as e:
            logger.error(f"خطأ في قبول الرحلة: {e}")
            await update.message.reply_text("حدث خطأ في قبول الرحلة.")
    
    async def complete_ride(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """إكمال الرحلة"""
        try:
            user_id = update.effective_user.id
            
            driver = self.session.query(User).filter_by(
                telegram_id=user_id,
                role=UserRole.DRIVER
            ).first()
            
            if not driver or not driver.driver_profile:
                await update.message.reply_text("أنت لست مسجلاً كسائق.")
                return
            
            ride_id = driver.driver_profile.current_ride_id
            if not ride_id:
                await update.message.reply_text("ليس لديك أي رحلة نشطة.")
                return
            
            ride = self.session.query(Ride).get(ride_id)
            if not ride:
                await update.message.reply_text("الرحلة غير موجودة.")
                return
            
            # تحديث حالة الرحلة
            from database.models import RideStatus
            ride.status = RideStatus.COMPLETED
            ride.completed_at = datetime.utcnow()
            ride.final_fare = ride.estimated_fare  # يمكن تعديله لاحقاً
            
            # تحديث إحصائيات السائق
            driver.driver_profile.current_ride_id = None
            driver.driver_profile.is_available = True
            driver.driver_profile.total_earnings += ride.driver_earning
            driver.total_rides += 1
            
            # إضافة العمولة إلى المديونية
            self.debt_manager.add_commission_to_debt(
                driver_id=driver.id,
                ride_id=ride.id,
                commission_amount=ride.commission_amount,
                description=f"عمولة رحلة #{ride.ride_code}"
            )
            
            # تحديث إحصائيات الراكب
            ride.passenger.total_rides += 1
            
            self.session.commit()
            
            # إرسال تقييم للراكب
            keyboard = [
                [InlineKeyboardButton(str(i), callback_data=f"rate_passenger_{i}") for i in range(1, 6)]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                f"✅ تم إكمال الرحلة رقم {ride.ride_code}\n\n"
                f"تفاصيل الدفع:\n"
                f"إجمالي الرحلة: {ride.final_fare:.2f} ريال\n"
                f"دخل السائق: {ride.driver_earning:.2f} ريال\n"
                f"العمولة: {ride.commission_amount:.2f} ريال\n\n"
                f"قم بتقييم الراكب:",
                reply_markup=reply_markup
            )
            
            # إرسال طلب تقييم للراكب
            await context.bot.send_message(
                chat_id=ride.passenger.telegram_id,
                text=f"تم إكمال رحلتك رقم {ride.ride_code}\n"
                     f"قم بتقييم السائق:",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(str(i), callback_data=f"rate_driver_{i}") for i in range(1, 6)]
                ])
            )
            
        except Exception as e:
            logger.error(f"خطأ في إكمال الرحلة: {e}")
            await update.message.reply_text("حدث خطأ في إكمال الرحلة.")
    
    async def driver_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """عرض إحصائيات السائق"""
        try:
            user_id = update.effective_user.id
            
            driver = self.session.query(User).filter_by(
                telegram_id=user_id,
                role=UserRole.DRIVER
            ).first()
            
            if not driver or not driver.driver_profile:
                await update.message.reply_text("أنت لست مسجلاً كسائق.")
                return
            
            stats_text = (
                f"📊 **إحصائيات السائق**\n\n"
                f"🆔 المعرف: {driver.id}\n"
                f"👤 الاسم: {driver.first_name}\n"
                f"🚗 نوع المركبة: {driver.driver_profile.vehicle_type or 'غير محدد'}\n"
                f"📅 تاريخ التسجيل: {driver.created_at.strftime('%Y-%m-%d')}\n\n"
                f"📈 **الإحصائيات:**\n"
                f"• إجمالي الرحلات: {driver.total_rides}\n"
                f"• التقييم العام: {'⭐' * int(driver.rating)}\n"
                f"• إجمالي الدخل: {driver.driver_profile.total_earnings:.2f} ريال\n"
                f"• المديونية الحالية: {driver.driver_profile.current_debt:.2f} ريال\n"
                f"• الرصيد الحالي: {driver.driver_profile.wallet_balance:.2f} ريال\n"
                f"• حالة العمل: {'🟢 نشط' if driver.driver_profile.is_online else '🔴 غير نشط'}\n\n"
                f"⏰ **اليوم:**\n"
                f"• الرحلات المكتملة: 0\n"  # يمكن حسابها لاحقاً
                f"• الدخل اليومي: 0.00 ريال\n"  # يمكن حسابها لاحقاً
            )
            
            await update.message.reply_text(stats_text)
            
        except Exception as e:
            logger.error(f"خطأ في عرض إحصائيات السائق: {e}")
    
    def get_handlers(self):
        """الحصول على جميع معالجات السائقين"""
        return [
            CommandHandler("driver_on", self.toggle_driver_mode),
            CommandHandler("driver_off", self.toggle_driver_mode),
            CommandHandler("accept", self.accept_ride),
            CommandHandler("complete", self.complete_ride),
            CommandHandler("stats", self.driver_stats),
            CommandHandler("earnings", self.driver_stats),
        ]
