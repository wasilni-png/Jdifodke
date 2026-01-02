import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler
from sqlalchemy import func, desc, or_
from sqlalchemy.orm import Session

from config import config
from database.database import db_manager
from database.models import User, UserRole, UserStatus, Ride, RideStatus, DriverProfile, DebtTransaction, AdminLog

logger = logging.getLogger(__name__)

class AdminHandlers:
    """معالجات لوحة تحكم الأدمن"""
    
    def __init__(self):
        self.session = db_manager.get_session_direct()
    
    async def admin_panel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """عرض لوحة تحكم الأدمن"""
        try:
            user_id = update.effective_user.id
            
            # التحقق من صلاحيات الأدمن
            if user_id not in config.bot.ADMIN_IDS:
                await update.message.reply_text("⛔ ليس لديك صلاحية الوصول إلى لوحة التحكم.")
                return
            
            # إضافة سجل للأدمن
            self._log_admin_action(
                admin_id=user_id,
                action="access_panel",
                details={"command": "admin_panel"}
            )
            
            keyboard = [
                [InlineKeyboardButton("📊 إحصائيات النظام", callback_data="admin_stats")],
                [InlineKeyboardButton("👥 إدارة المستخدمين", callback_data="admin_users")],
                [InlineKeyboardButton("🚕 إدارة السائقين", callback_data="admin_drivers")],
                [InlineKeyboardButton("🚗 الرحلات النشطة", callback_data="admin_active_rides")],
                [InlineKeyboardButton("💰 نظام المديونية", callback_data="admin_debts")],
                [InlineKeyboardButton("⛔ حظر/فك حظر", callback_data="admin_ban")],
                [InlineKeyboardButton("📈 تقارير اليوم", callback_data="admin_daily_report")],
                [InlineKeyboardButton("⚙️ الإعدادات", callback_data="admin_settings")]
            ]
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                "👨‍💼 **لوحة تحكم الأدمن**\n\n"
                "اختر الخيار المطلوب:",
                reply_markup=reply_markup
            )
            
        except Exception as e:
            logger.error(f"خطأ في عرض لوحة التحكم: {e}")
            await update.message.reply_text("حدث خطأ في عرض لوحة التحكم.")
    
    async def admin_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة اختيارات لوحة التحكم"""
        try:
            query = update.callback_query
            await query.answer()
            
            admin_id = update.effective_user.id
            
            # التحقق من صلاحيات الأدمن
            if admin_id not in config.bot.ADMIN_IDS:
                await query.edit_message_text("⛔ ليس لديك صلاحية الوصول.")
                return
            
            action = query.data
            
            if action == "admin_stats":
                await self._show_system_stats(query)
            elif action == "admin_users":
                await self._show_users_management(query)
            elif action == "admin_drivers":
                await self._show_drivers_management(query)
            elif action == "admin_active_rides":
                await self._show_active_rides(query)
            elif action == "admin_debts":
                await self._show_debt_management(query)
            elif action == "admin_ban":
                await self._show_ban_management(query)
            elif action == "admin_daily_report":
                await self._show_daily_report(query)
            elif action == "admin_settings":
                await self._show_settings(query)
            elif action.startswith("user_detail_"):
                user_id = int(action.split("_")[2])
                await self._show_user_detail(query, user_id)
            elif action.startswith("driver_detail_"):
                driver_id = int(action.split("_")[2])
                await self._show_driver_detail(query, driver_id)
            elif action.startswith("ride_detail_"):
                ride_id = int(action.split("_")[2])
                await self._show_ride_detail(query, ride_id)
            elif action.startswith("ban_user_"):
                user_id = int(action.split("_")[2])
                await self._ban_user(query, user_id)
            elif action.startswith("unban_user_"):
                user_id = int(action.split("_")[2])
                await self._unban_user(query, user_id)
            elif action.startswith("suspend_driver_"):
                driver_id = int(action.split("_")[2])
                await self._suspend_driver(query, driver_id)
            elif action.startswith("activate_driver_"):
                driver_id = int(action.split("_")[2])
                await self._activate_driver(query, driver_id)
            elif action.startswith("clear_debt_"):
                driver_id = int(action.split("_")[2])
                await self._clear_debt(query, driver_id)
            
        except Exception as e:
            logger.error(f"خطأ في معالجة callback الأدمن: {e}")
            await query.edit_message_text("حدث خطأ في المعالجة.")
    
    async def _show_system_stats(self, query):
        """عرض إحصائيات النظام"""
        try:
            # إحصائيات المستخدمين
            total_users = self.session.query(User).count()
            total_passengers = self.session.query(User).filter_by(role=UserRole.PASSENGER).count()
            total_drivers = self.session.query(User).filter_by(role=UserRole.DRIVER).count()
            active_drivers = self.session.query(DriverProfile).filter_by(is_online=True).count()
            banned_users = self.session.query(User).filter_by(status=UserStatus.BANNED).count()
            
            # إحصائيات الرحلات
            today = datetime.utcnow().date()
            start_of_day = datetime.combine(today, datetime.min.time())
            
            total_rides = self.session.query(Ride).count()
            today_rides = self.session.query(Ride).filter(
                Ride.requested_at >= start_of_day
            ).count()
            
            completed_rides = self.session.query(Ride).filter(
                Ride.status == RideStatus.COMPLETED
            ).count()
            
            # إحصائيات مالية
            total_revenue = self.session.query(func.sum(Ride.commission_amount)).scalar() or 0
            total_paid = self.session.query(func.sum(Ride.final_fare)).scalar() or 0
            total_debt = self.session.query(func.sum(DriverProfile.current_debt)).scalar() or 0
            
            # تحليل النمو
            week_ago = datetime.utcnow() - timedelta(days=7)
            new_users_week = self.session.query(User).filter(
                User.created_at >= week_ago
            ).count()
            
            new_rides_week = self.session.query(Ride).filter(
                Ride.requested_at >= week_ago
            ).count()
            
            stats_text = (
                "📊 **إحصائيات النظام**\n\n"
                f"👥 **المستخدمين:**\n"
                f"• إجمالي المستخدمين: {total_users}\n"
                f"• الركاب: {total_passengers}\n"
                f"• السائقين: {total_drivers}\n"
                f"• السائقين النشطين: {active_drivers}\n"
                f"• المحظورين: {banned_users}\n"
                f"• مستخدمين جدد (أسبوع): {new_users_week}\n\n"
                
                f"🚗 **الرحلات:**\n"
                f"• إجمالي الرحلات: {total_rides}\n"
                f"• الرحلات المكتملة: {completed_rides}\n"
                f"• رحلات اليوم: {today_rides}\n"
                f"• رحلات جديدة (أسبوع): {new_rides_week}\n\n"
                
                f"💰 **المالية:**\n"
                f"• إجمالي الإيرادات: {total_revenue:.2f} ريال\n"
                f"• إجمالي المدفوعات: {total_paid:.2f} ريال\n"
                f"• إجمالي المديونية: {total_debt:.2f} ريال\n\n"
                
                f"⏰ **آخر تحديث:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}"
            )
            
            keyboard = [[InlineKeyboardButton("🔄 تحديث", callback_data="admin_stats")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                stats_text,
                reply_markup=reply_markup
            )
            
        except Exception as e:
            logger.error(f"خطأ في عرض إحصائيات النظام: {e}")
            await query.edit_message_text("حدث خطأ في جلب الإحصائيات.")
    
    async def _show_users_management(self, query):
        """عرض إدارة المستخدمين"""
        try:
            # جلب المستخدمين مع الترقيم
            users = self.session.query(User).order_by(
                desc(User.created_at)
            ).limit(20).all()
            
            if not users:
                await query.edit_message_text("❌ لا يوجد مستخدمين حالياً.")
                return
            
            users_list = []
            for user in users:
                status_icon = "🟢" if user.status == UserStatus.ACTIVE else "🔴"
                role_icon = "👤" if user.role == UserRole.PASSENGER else "🚖"
                
                users_list.append(
                    f"{status_icon} {role_icon} {user.first_name} "
                    f"(ID: {user.id}) - {user.created_at.strftime('%Y-%m-%d')}"
                )
            
            users_text = "\n".join(users_list)
            
            keyboard = []
            for user in users:
                keyboard.append([
                    InlineKeyboardButton(
                        f"{user.first_name} ({user.role.value})",
                        callback_data=f"user_detail_{user.id}"
                    )
                ])
            
            keyboard.append([InlineKeyboardButton("◀️ رجوع", callback_data="admin_panel")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                f"👥 **إدارة المستخدمين**\n\n"
                f"إجمالي: {len(users)} مستخدم\n\n"
                f"{users_text}\n\n"
                f"اختر مستخدم للتفاصيل:",
                reply_markup=reply_markup
            )
            
        except Exception as e:
            logger.error(f"خطأ في عرض إدارة المستخدمين: {e}")
            await query.edit_message_text("حدث خطأ في جلب المستخدمين.")
    
    async def _show_user_detail(self, query, user_id: int):
        """عرض تفاصيل المستخدم"""
        try:
            user = self.session.query(User).filter_by(id=user_id).first()
            
            if not user:
                await query.edit_message_text("❌ لم يتم العثور على المستخدم.")
                return
            
            # جمع المعلومات
            user_info = (
                f"👤 **تفاصيل المستخدم**\n\n"
                f"🆔 المعرف: {user.id}\n"
                f"معرف التيليجرام: {user.telegram_id}\n"
                f"الاسم: {user.first_name} {user.last_name or ''}\n"
                f"اسم المستخدم: @{user.username or 'غير محدد'}\n"
                f"رقم الهاتف: {user.phone or 'غير محدد'}\n"
                f"الدور: {user.role.value}\n"
                f"الحالة: {user.status.value}\n"
                f"التقييم: {'⭐' * int(user.rating) if user.rating else 'بدون تقييم'}\n"
                f"إجمالي الرحلات: {user.total_rides}\n"
                f"تاريخ التسجيل: {user.created_at.strftime('%Y-%m-%d %H:%M')}\n"
            )
            
            if user.role == UserRole.DRIVER and user.driver_profile:
                driver = user.driver_profile
                user_info += (
                    f"\n🚖 **معلومات السائق:**\n"
                    f"نوع المركبة: {driver.vehicle_type or 'غير محدد'}\n"
                    f"رقم اللوحة: {driver.license_plate or 'غير محدد'}\n"
                    f"حالة العمل: {'🟢 نشط' if driver.is_online else '🔴 غير نشط'}\n"
                    f"المديونية: {driver.current_debt:.2f} ريال\n"
                    f"إجمالي الدخل: {driver.total_earnings:.2f} ريال\n"
                    f"عدد الرحلات: {driver.user.total_rides}"
                )
            
            # إحصائيات الرحلات
            user_rides = self.session.query(Ride).filter(
                or_(Ride.passenger_id == user.id, Ride.driver_id == user.id)
            ).all()
            
            if user_rides:
                completed = len([r for r in user_rides if r.status == RideStatus.COMPLETED])
                cancelled = len([r for r in user_rides if r.status == RideStatus.CANCELLED])
                
                user_info += (
                    f"\n\n🚗 **إحصائيات الرحلات:**\n"
                    f"إجمالي الرحلات: {len(user_rides)}\n"
                    f"المكتملة: {completed}\n"
                    f"الملغاة: {cancelled}"
                )
            
            # أزرار التحكم
            keyboard = []
            
            if user.status != UserStatus.BANNED:
                keyboard.append([
                    InlineKeyboardButton("⛔ حظر المستخدم", callback_data=f"ban_user_{user.id}")
                ])
            else:
                keyboard.append([
                    InlineKeyboardButton("✅ فك حظر المستخدم", callback_data=f"unban_user_{user.id}")
                ])
            
            if user.role == UserRole.DRIVER and user.driver_profile:
                if user.status == UserStatus.ACTIVE:
                    keyboard.append([
                        InlineKeyboardButton("⏸️ تعليق السائق", callback_data=f"suspend_driver_{user.id}")
                    ])
                else:
                    keyboard.append([
                        InlineKeyboardButton("▶️ تفعيل السائق", callback_data=f"activate_driver_{user.id}")
                    ])
                
                if user.driver_profile.current_debt > 0:
                    keyboard.append([
                        InlineKeyboardButton("💰 تسوية المديونية", callback_data=f"clear_debt_{user.id}")
                    ])
            
            keyboard.append([
                InlineKeyboardButton("◀️ رجوع", callback_data="admin_users")
            ])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                user_info,
                reply_markup=reply_markup
            )
            
        except Exception as e:
            logger.error(f"خطأ في عرض تفاصيل المستخدم: {e}")
            await query.edit_message_text("حدث خطأ في جلب تفاصيل المستخدم.")
    
    async def _ban_user(self, query, user_id: int):
        """حظر المستخدم"""
        try:
            admin_id = query.from_user.id
            
            user = self.session.query(User).filter_by(id=user_id).first()
            if not user:
                await query.answer("المستخدم غير موجود!")
                return
            
            user.status = UserStatus.BANNED
            
            # إضافة سجل للأدمن
            self._log_admin_action(
                admin_id=admin_id,
                action="ban_user",
                target_type="user",
                target_id=user_id,
                details={
                    "user_telegram_id": user.telegram_id,
                    "user_name": user.first_name,
                    "reason": "من خلال لوحة التحكم"
                }
            )
            
            self.session.commit()
            
            # محاولة إرسال إشعار للمستخدم
            try:
                await query.bot.send_message(
                    chat_id=user.telegram_id,
                    text="⛔ **تم حظر حسابك**\n\n"
                         "لقد تم حظر حسابك من قبل الإدارة.\n"
                         "للإستفسار، يرجى التواصل مع الدعم."
                )
            except:
                pass
            
            await query.answer("✅ تم حظر المستخدم بنجاح!")
            
            # تحديث الرسالة
            await self._show_user_detail(query, user_id)
            
        except Exception as e:
            logger.error(f"خطأ في حظر المستخدم: {e}")
            await query.answer("❌ حدث خطأ في حظر المستخدم!")
    
    async def _unban_user(self, query, user_id: int):
        """فك حظر المستخدم"""
        try:
            admin_id = query.from_user.id
            
            user = self.session.query(User).filter_by(id=user_id).first()
            if not user:
                await query.answer("المستخدم غير موجود!")
                return
            
            user.status = UserStatus.ACTIVE
            
            # إضافة سجل للأدمن
            self._log_admin_action(
                admin_id=admin_id,
                action="unban_user",
                target_type="user",
                target_id=user_id,
                details={
                    "user_telegram_id": user.telegram_id,
                    "user_name": user.first_name
                }
            )
            
            self.session.commit()
            
            # محاولة إرسال إشعار للمستخدم
            try:
                await query.bot.send_message(
                    chat_id=user.telegram_id,
                    text="✅ **تم فك حظر حسابك**\n\n"
                         "تم إعادة تفعيل حسابك.\n"
                         "يمكنك الآن استخدام الخدمة مرة أخرى."
                )
            except:
                pass
            
            await query.answer("✅ تم فك حظر المستخدم بنجاح!")
            
            # تحديث الرسالة
            await self._show_user_detail(query, user_id)
            
        except Exception as e:
            logger.error(f"خطأ في فك حظر المستخدم: {e}")
            await query.answer("❌ حدث خطأ في فك حظر المستخدم!")
    
    async def _show_debt_management(self, query):
        """إدارة نظام المديونية"""
        try:
            # جلب السائقين الذين لديهم مديونية
            drivers_with_debt = self.session.query(User, DriverProfile).join(
                DriverProfile, User.id == DriverProfile.user_id
            ).filter(
                DriverProfile.current_debt > 0
            ).order_by(
                desc(DriverProfile.current_debt)
            ).limit(20).all()
            
            if not drivers_with_debt:
                await query.edit_message_text("✅ لا يوجد سائقين لديهم مديونية حالياً.")
                return
            
            debt_summary = "💰 **إدارة المديونية**\n\n"
            total_debt = 0
            
            keyboard = []
            
            for user, driver in drivers_with_debt:
                total_debt += driver.current_debt
                status = "⛔ موقوف" if user.status == UserStatus.SUSPENDED else "🟢 نشط"
                
                debt_summary += (
                    f"👤 {user.first_name}\n"
                    f"   المديونية: {driver.current_debt:.2f} ريال\n"
                    f"   الحالة: {status}\n"
                    f"   الرحلات: {user.total_rides}\n\n"
                )
                
                keyboard.append([
                    InlineKeyboardButton(
                        f"{user.first_name} - {driver.current_debt:.2f} ريال",
                        callback_data=f"driver_detail_{user.id}"
                    )
                ])
            
            debt_summary += f"\n📊 **إجمالي المديونية:** {total_debt:.2f} ريال"
            
            keyboard.append([InlineKeyboardButton("◀️ رجوع", callback_data="admin_panel")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                debt_summary,
                reply_markup=reply_markup
            )
            
        except Exception as e:
            logger.error(f"خطأ في عرض إدارة المديونية: {e}")
            await query.edit_message_text("حدث خطأ في جلب بيانات المديونية.")
    
    async def _clear_debt(self, query, driver_id: int):
        """تسوية مديونية السائق"""
        try:
            admin_id = query.from_user.id
            
            driver = self.session.query(DriverProfile).filter_by(user_id=driver_id).first()
            if not driver:
                await query.answer("السائق غير موجود!")
                return
            
            old_debt = driver.current_debt
            
            # إنشاء معاملة تسوية
            transaction = DebtTransaction(
                driver_id=driver.id,
                amount=-old_debt,  # سالب لأنه تسوية
                transaction_type="adjustment",
                description=f"تسوية مديونية من قبل الأدمن (ID: {admin_id})",
                balance_before=driver.current_debt,
                balance_after=0.0
            )
            
            driver.current_debt = 0.0
            
            # إذا كان موقوفاً بسبب المديونية، نقوم بتفعيله
            if driver.user.status == UserStatus.SUSPENDED:
                driver.user.status = UserStatus.ACTIVE
                driver.is_online = True
            
            self.session.add(transaction)
            
            # إضافة سجل للأدمن
            self._log_admin_action(
                admin_id=admin_id,
                action="clear_debt",
                target_type="driver",
                target_id=driver_id,
                details={
                    "old_debt": old_debt,
                    "new_debt": 0.0,
                    "driver_name": driver.user.first_name
                }
            )
            
            self.session.commit()
            
            await query.answer(f"✅ تم تسوية مديونية بقيمة {old_debt:.2f} ريال")
            
            # تحديث الرسالة
            await self._show_driver_detail(query, driver_id)
            
        except Exception as e:
            logger.error(f"خطأ في تسوية المديونية: {e}")
            await query.answer("❌ حدث خطأ في تسوية المديونية!")
    
    async def _show_daily_report(self, query):
        """عرض تقرير اليوم"""
        try:
            today = datetime.utcnow().date()
            start_of_day = datetime.combine(today, datetime.min.time())
            
            # إحصائيات الرحلات اليومية
            today_rides = self.session.query(Ride).filter(
                Ride.requested_at >= start_of_day
            ).all()
            
            completed_rides = [r for r in today_rides if r.status == RideStatus.COMPLETED]
            cancelled_rides = [r for r in today_rides if r.status == RideStatus.CANCELLED]
            
            # الإيرادات اليومية
            daily_revenue = sum(r.commission_amount or 0 for r in completed_rides)
            daily_earnings = sum(r.final_fare or 0 for r in completed_rides)
            
            # المستخدمين الجدد
            new_users_today = self.session.query(User).filter(
                User.created_at >= start_of_day
            ).count()
            
            # النشاط حسب الساعة
            hourly_stats = {}
            for ride in today_rides:
                hour = ride.requested_at.hour
                hourly_stats[hour] = hourly_stats.get(hour, 0) + 1
            
            # بناء النص
            report_text = (
                f"📈 **تقرير اليوم** ({today.strftime('%Y-%m-%d')})\n\n"
                f"🚗 **الرحلات:**\n"
                f"• إجمالي الرحلات: {len(today_rides)}\n"
                f"• المكتملة: {len(completed_rides)}\n"
                f"• الملغاة: {len(cancelled_rides)}\n"
                f"• نسبة الإلغاء: {(len(cancelled_rides)/len(today_rides)*100 if today_rides else 0):.1f}%\n\n"
                
                f"💰 **المالية:**\n"
                f"• الإيرادات: {daily_revenue:.2f} ريال\n"
                f"• إجمالي المبيعات: {daily_earnings:.2f} ريال\n"
                f"• متوسط الرحلة: {(daily_earnings/len(completed_rides) if completed_rides else 0):.2f} ريال\n\n"
                
                f"👥 **المستخدمين:**\n"
                f"• مستخدمين جدد: {new_users_today}\n\n"
                
                f"⏰ **التوزيع الساعي:**\n"
            )
            
            # إضافة الإحصائيات الساعية
            for hour in sorted(hourly_stats.keys()):
                report_text += f"• {hour:02d}:00 - {hourly_stats[hour]} رحلة\n"
            
            keyboard = [[InlineKeyboardButton("🔄 تحديث", callback_data="admin_daily_report")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                report_text,
                reply_markup=reply_markup
            )
            
        except Exception as e:
            logger.error(f"خطأ في عرض تقرير اليوم: {e}")
            await query.edit_message_text("حدث خطأ في جلب تقرير اليوم.")
    
    async def _show_settings(self, query):
        """عرض إعدادات النظام"""
        try:
            settings_text = (
                "⚙️ **إعدادات النظام**\n\n"
                f"**التسعير:**\n"
                f"• رسوم البداية: {config.pricing.BASE_FARE} ريال\n"
                f"• سعر الكيلومتر: {config.pricing.RATE_PER_KM} ريال\n"
                f"• نسبة العمولة: {config.pricing.COMMISSION_RATE*100}%\n"
                f"• الحد الأدنى: {config.pricing.MINIMUM_FARE} ريال\n\n"
                
                f"**الموقع:**\n"
                f"• نصف قطر البحث: {config.location.SEARCH_RADIUS_KM} كم\n"
                f"• فاصل التحديث: {config.location.LOCATION_UPDATE_INTERVAL} ثانية\n\n"
                
                f"**الديون:**\n"
                f"• حد المديونية: {config.debt.MAX_DEBT_LIMIT} ريال\n"
                f"• عتبة التحذير: {config.debt.DEBT_WARNING_THRESHOLD} ريال\n"
                f"• الإيقاف التلقائي: {'مفعل' if config.debt.AUTO_SUSPEND else 'معطل'}\n\n"
                
                f"**النظام:**\n"
                f"• معرفات الأدمن: {', '.join(map(str, config.bot.ADMIN_IDS))}\n"
                f"• وضع الإنتاج: {'نعم' if config.bot.is_production else 'لا'}"
            )
            
            keyboard = [[InlineKeyboardButton("◀️ رجوع", callback_data="admin_panel")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                settings_text,
                reply_markup=reply_markup
            )
            
        except Exception as e:
            logger.error(f"خطأ في عرض الإعدادات: {e}")
            await query.edit_message_text("حدث خطأ في جلب الإعدادات.")
    
    def _log_admin_action(self, admin_id: int, action: str, target_type: str = None, 
                         target_id: int = None, details: dict = None):
        """تسجيل إجراءات الأدمن"""
        try:
            log = AdminLog(
                admin_id=admin_id,
                action=action,
                target_type=target_type,
                target_id=target_id,
                details=details or {}
            )
            
            self.session.add(log)
            self.session.commit()
            
        except Exception as e:
            logger.error(f"خطأ في تسجيل إجراء الأدمن: {e}")
    
    def get_handlers(self):
        """الحصول على جميع معالجات الأدمن"""
        return [
            CommandHandler("admin", self.admin_panel),
            CallbackQueryHandler(self.admin_callback, pattern="^admin_"),
            CallbackQueryHandler(self.admin_callback, pattern="^user_detail_"),
            CallbackQueryHandler(self.admin_callback, pattern="^driver_detail_"),
            CallbackQueryHandler(self.admin_callback, pattern="^ride_detail_"),
            CallbackQueryHandler(self.admin_callback, pattern="^ban_"),
            CallbackQueryHandler(self.admin_callback, pattern="^unban_"),
            CallbackQueryHandler(self.admin_callback, pattern="^suspend_"),
            CallbackQueryHandler(self.admin_callback, pattern="^activate_"),
            CallbackQueryHandler(self.admin_callback, pattern="^clear_debt_")
        ]