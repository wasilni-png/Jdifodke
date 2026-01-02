import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler
from sqlalchemy.orm import Session
from datetime import datetime

from config import config
from database.models import User, UserRole, Ride, RideStatus
from database.database import db_manager
from utils.location import Location, LocationService
from utils.pricing import PricingService

logger = logging.getLogger(__name__)

class RideHandlers:
    """معالجات الرحلات"""
    
    def __init__(self):
        self.session = db_manager.get_session_direct()
        self.location_service = LocationService()
        self.pricing_service = PricingService()
    
    async def request_ride(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """طلب رحلة جديدة"""
        try:
            user_id = update.effective_user.id
            
            # التحقق من هوية المستخدم
            user = self.session.query(User).filter_by(
                telegram_id=user_id,
                role=UserRole.PASSENGER
            ).first()
            
            if not user:
                await update.message.reply_text("أنت لست مسجلاً كراكب.")
                return
            
            # التحقق من وجود موقع
            if not user.latitude or not user.longitude:
                await update.message.reply_text(
                    "يجب تحديد موقعك أولاً.\n"
                    "استخدم الأمر: /set_location"
                )
                return
            
            # طلب موقع الوجهة
            await update.message.reply_text(
                "📍 **رجاءً أرسل موقع الوجهة:**\n\n"
                "يمكنك:\n"
                "1. إرسال الموقع مباشرة\n"
                "2. كتابة العنوان\n"
                "3. استخدام /cancel للإلغاء"
            )
            
            # حفظ حالة الطلب
            context.user_data['ride_request'] = {
                'passenger_id': user.id,
                'pickup_location': Location(user.latitude, user.longitude),
                'step': 'awaiting_destination'
            }
            
        except Exception as e:
            logger.error(f"خطأ في طلب الرحلة: {e}")
            await update.message.reply_text("حدث خطأ في طلب الرحلة.")
    
    async def handle_destination(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة موقع الوجهة"""
        try:
            if 'ride_request' not in context.user_data:
                return
            
            if context.user_data['ride_request']['step'] != 'awaiting_destination':
                return
            
            if not update.message.location:
                await update.message.reply_text("يجب إرسال موقع صحيح.")
                return
            
            location = update.message.location
            destination = Location(location.latitude, location.longitude)
            
            # تحديث بيانات الطلب
            context.user_data['ride_request'].update({
                'destination_location': destination,
                'step': 'confirming_ride'
            })
            
            # حساب المسافة والتكلفة
            pickup = context.user_data['ride_request']['pickup_location']
            fare_details = self.pricing_service.calculate_ride_fare(pickup, destination)
            
            # البحث عن سائقين قريبين
            nearby_drivers = self.location_service.find_nearby_drivers(
                pickup,
                max_distance_km=config.location.SEARCH_RADIUS_KM,
                session=self.session
            )
            
            if not nearby_drivers:
                await update.message.reply_text(
                    "⚠️ لا يوجد سائقين متاحين بالقرب منك حالياً.\n"
                    "الرجاء المحاولة لاحقاً."
                )
                context.user_data.pop('ride_request', None)
                return
            
            # حفظ معلومات الرحلة
            ride_data = {
                'fare_details': fare_details,
                'nearby_drivers': nearby_drivers,
                'estimated_time': self.location_service.estimate_travel_time(
                    fare_details['distance_km']
                )
            }
            context.user_data['ride_request'].update(ride_data)
            
            # عرض تفاصيل الرحلة للموافقة
            keyboard = [
                [InlineKeyboardButton("✅ تأكيد الطلب", callback_data="confirm_ride")],
                [InlineKeyboardButton("❌ إلغاء", callback_data="cancel_ride")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            ride_summary = (
                f"📋 **تفاصيل الرحلة:**\n\n"
                f"📍 **من:** موقعك الحالي\n"
                f"📍 **إلى:** الموقع المحدد\n\n"
                f"📏 **المسافة:** {fare_details['distance_km']:.2f} كم\n"
                f"⏱️ **الوقت المتوقع:** {ride_data['estimated_time']['total_time_minutes']} دقيقة\n"
                f"💰 **التكلفة التقديرية:** {fare_details['total_fare']:.2f} ريال\n"
                f"🚖 **السائقين المتاحين:** {len(nearby_drivers)} سائق\n\n"
                f"هل تريد تأكيد الطلب؟"
            )
            
            await update.message.reply_text(
                ride_summary,
                reply_markup=reply_markup
            )
            
        except Exception as e:
            logger.error(f"خطأ في معالجة الوجهة: {e}")
            await update.message.reply_text("حدث خطأ في معالجة الوجهة.")
    
    async def confirm_ride_request(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """تأكيد طلب الرحلة"""
        try:
            query = update.callback_query
            await query.answer()
            
            if 'ride_request' not in context.user_data:
                await query.edit_message_text("انتهت صلاحية طلب الرحلة.")
                return
            
            ride_data = context.user_data['ride_request']
            
            # إنشاء رحلة في قاعدة البيانات
            ride = Ride(
                passenger_id=ride_data['passenger_id'],
                pickup_latitude=ride_data['pickup_location'].latitude,
                pickup_longitude=ride_data['pickup_location'].longitude,
                destination_latitude=ride_data['destination_location'].latitude,
                destination_longitude=ride_data['destination_location'].longitude,
                distance_km=ride_data['fare_details']['distance_km'],
                estimated_fare=ride_data['fare_details']['total_fare'],
                commission_amount=ride_data['fare_details']['commission_amount'],
                driver_earning=ride_data['fare_details']['driver_earning'],
                status=RideStatus.PENDING,
                ride_code=f"RIDE-{datetime.now().strftime('%Y%m%d')}-{query.id}",
                requested_at=datetime.utcnow()
            )
            
            self.session.add(ride)
            self.session.commit()
            
            # إرسال طلبات للسائقين القريبين
            drivers_notified = 0
            for driver in ride_data['nearby_drivers'][:5]:  # إرسال لأول 5 سائقين
                try:
                    keyboard = [
                        [
                            InlineKeyboardButton("✅ قبول الرحلة", callback_data=f"accept_ride_{ride.id}"),
                            InlineKeyboardButton("❌ رفض", callback_data="decline_ride")
                        ]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    
                    driver_message = (
                        f"🚖 **طلب رحلة جديد**\n\n"
                        f"📍 **موقع الراكب:** على بعد {driver['distance_km']} كم\n"
                        f"📏 **المسافة:** {ride_data['fare_details']['distance_km']:.2f} كم\n"
                        f"💰 **التكلفة:** {ride_data['fare_details']['total_fare']:.2f} ريال\n"
                        f"💵 **دخل السائق:** {ride_data['fare_details']['driver_earning']:.2f} ريال\n\n"
                        f"هل تقبل الرحلة؟"
                    )
                    
                    await context.bot.send_message(
                        chat_id=driver['telegram_id'],
                        text=driver_message,
                        reply_markup=reply_markup
                    )
                    drivers_notified += 1
                    
                except Exception as e:
                    logger.error(f"خطأ في إرسال طلب للسائق {driver['driver_id']}: {e}")
            
            # إرسال تأكيد للراكب
            await query.edit_message_text(
                f"✅ تم إرسال طلب رحلتك!\n\n"
                f"رقم الرحلة: {ride.ride_code}\n"
                f"تم إرسال الطلب لـ {drivers_notified} سائق\n"
                f"سيتم إعلامك عند قبول الرحلة.\n\n"
                f"يمكنك متابعة حالة الرحلة باستخدام: /ride_status {ride.id}"
            )
            
            # تنظيف البيانات المؤقتة
            context.user_data.pop('ride_request', None)
            
        except Exception as e:
            logger.error(f"خطأ في تأكيد الرحلة: {e}")
            await query.edit_message_text("حدث خطأ في تأكيد الرحلة.")
    
    async def ride_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """عرض حالة الرحلة"""
        try:
            if not context.args:
                await update.message.reply_text("الرجاء تحديد رقم الرحلة: /ride_status <رقم_الرحلة>")
                return
            
            ride_code = context.args[0]
            ride = self.session.query(Ride).filter_by(ride_code=ride_code).first()
            
            if not ride:
                await update.message.reply_text("لم يتم العثور على الرحلة.")
                return
            
            # التحقق من صلاحية المستخدم
            user_id = update.effective_user.id
            user = self.session.query(User).filter_by(telegram_id=user_id).first()
            
            if not user or (user.id != ride.passenger_id and user.id != ride.driver_id):
                await update.message.reply_text("ليس لديك صلاحية لعرض هذه الرحلة.")
                return
            
            # بناء رسالة حالة الرحلة
            status_icons = {
                "pending": "⏳",
                "accepted": "✅",
                "in_progress": "🚗",
                "completed": "🎉",
                "cancelled": "❌",
                "no_drivers": "⚠️"
            }
            
            status_texts = {
                "pending": "في انتظار السائق",
                "accepted": "تم قبولها",
                "in_progress": "جارية",
                "completed": "مكتملة",
                "cancelled": "ملغاة",
                "no_drivers": "لا يوجد سائقين"
            }
            
            status_icon = status_icons.get(ride.status.value, "❓")
            status_text = status_texts.get(ride.status.value, ride.status.value)
            
            ride_info = (
                f"📋 **حالة الرحلة:** {status_icon} {status_text}\n\n"
                f"🆔 **رقم الرحلة:** {ride.ride_code}\n"
                f"👤 **الراكب:** {ride.passenger.first_name}\n"
            )
            
            if ride.driver:
                ride_info += f"🚖 **السائق:** {ride.driver.first_name}\n"
            
            ride_info += (
                f"\n📍 **من:** {ride.pickup_address or 'موقع البداية'}\n"
                f"📍 **إلى:** {ride.destination_address or 'موقع الوجهة'}\n\n"
                f"📏 **المسافة:** {ride.distance_km or 0:.2f} كم\n"
                f"💰 **التكلفة:** {ride.estimated_fare or 0:.2f} ريال\n"
                f"⏰ **وقت الطلب:** {ride.requested_at.strftime('%Y-%m-%d %H:%M')}\n"
            )
            
            if ride.accepted_at:
                ride_info += f"✅ **وقت القبول:** {ride.accepted_at.strftime('%H:%M')}\n"
            if ride.started_at:
                ride_info += f"🚗 **وقت البدء:** {ride.started_at.strftime('%H:%M')}\n"
            if ride.completed_at:
                ride_info += f"🎉 **وقت الإكمال:** {ride.completed_at.strftime('%H:%M')}\n"
            
            await update.message.reply_text(ride_info)
            
        except Exception as e:
            logger.error(f"خطأ في عرض حالة الرحلة: {e}")
    
    def get_handlers(self):
        """الحصول على جميع معالجات الرحلات"""
        return [
            CommandHandler("request_ride", self.request_ride),
            CommandHandler("ride_status", self.ride_status),
            CallbackQueryHandler(self.confirm_ride_request, pattern="^confirm_ride$"),
            CallbackQueryHandler(self.confirm_ride_request, pattern="^accept_ride_"),
            MessageHandler(filters.LOCATION, self.handle_destination)
        ]
