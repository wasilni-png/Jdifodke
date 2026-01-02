import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum

from config import config
from database.models import DriverProfile, DebtTransaction, Ride

logger = logging.getLogger(__name__)

class DebtAction(Enum):
    """إجراءات نظام المديونية"""
    ADD_COMMISSION = "add_commission"
    ADD_PAYMENT = "add_payment"
    ADD_ADJUSTMENT = "add_adjustment"
    ADD_PENALTY = "add_penalty"

@dataclass
class DebtNotification:
    """إشعار المديونية"""
    driver_id: int
    message: str
    notification_type: str  # warning, limit_reached, suspension
    debt_amount: float
    timestamp: datetime

class DebtManager:
    """مدير نظام المديونية"""
    
    def __init__(self, session):
        self.session = session
    
    def add_commission_to_debt(
        self,
        driver_id: int,
        ride_id: int,
        commission_amount: float,
        description: str = "عمولة رحلة"
    ) -> Dict[str, Any]:
        """
        إضافة عمولة إلى مديونية السائق
        
        Returns:
            معلومات المعاملة الجديدة
        """
        try:
            driver_profile = self.session.query(DriverProfile).filter_by(
                user_id=driver_id
            ).first()
            
            if not driver_profile:
                raise ValueError(f"لم يتم العثور على سائق بالمعرف: {driver_id}")
            
            # حساب الرصيد الجديد
            new_debt = driver_profile.current_debt + commission_amount
            
            # إنشاء معاملة مديونية
            transaction = DebtTransaction(
                driver_id=driver_profile.id,
                ride_id=ride_id,
                amount=commission_amount,
                transaction_type="commission",
                description=description,
                balance_before=driver_profile.current_debt,
                balance_after=new_debt
            )
            
            # تحديث مديونية السائق
            driver_profile.current_debt = new_debt
            
            # حفظ التغييرات
            self.session.add(transaction)
            self.session.commit()
            
            # التحقق من تجاوز الحد
            if new_debt >= config.debt.DEBT_WARNING_THRESHOLD:
                self._check_debt_limits(driver_id, new_debt)
            
            return {
                'transaction_id': transaction.id,
                'driver_id': driver_id,
                'old_debt': driver_profile.current_debt - commission_amount,
                'new_debt': new_debt,
                'commission_amount': commission_amount,
                'transaction_time': transaction.created_at
            }
            
        except Exception as e:
            self.session.rollback()
            logger.error(f"خطأ في إضافة العمولة: {e}")
            raise
    
    def add_payment(
        self,
        driver_id: int,
        amount: float,
        payment_method: str,
        reference: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        إضافة دفعة لتقليل المديونية
        
        Returns:
            معلومات الدفعة
        """
        try:
            driver_profile = self.session.query(DriverProfile).filter_by(
                user_id=driver_id
            ).first()
            
            if not driver_profile:
                raise ValueError(f"لم يتم العثور على سائق بالمعرف: {driver_id}")
            
            # التأكد من أن المبلغ لا يتجاوز المديونية
            if amount > driver_profile.current_debt:
                amount = driver_profile.current_debt
            
            # حساب الرصيد الجديد
            new_debt = driver_profile.current_debt - amount
            
            # إنشاء معاملة دفع
            transaction = DebtTransaction(
                driver_id=driver_profile.id,
                amount=-amount,  # سالب لأنه دفع
                transaction_type="payment",
                description=f"دفع عبر {payment_method} - {reference or 'بدون رقم مرجعي'}",
                balance_before=driver_profile.current_debt,
                balance_after=new_debt
            )
            
            # تحديث مديونية السائق
            driver_profile.current_debt = new_debt
            driver_profile.wallet_balance += amount
            
            # إذا كان الرصيد أصبح أقل من الحد، تفعيل الحساب
            if (driver_profile.current_debt < config.debt.MAX_DEBT_LIMIT and 
                not driver_profile.user.is_active):
                driver_profile.user.status = "active"
                driver_profile.is_online = True
            
            self.session.add(transaction)
            self.session.commit()
            
            return {
                'transaction_id': transaction.id,
                'driver_id': driver_id,
                'payment_amount': amount,
                'old_debt': driver_profile.current_debt + amount,
                'new_debt': new_debt,
                'payment_method': payment_method,
                'payment_time': transaction.created_at
            }
            
        except Exception as e:
            self.session.rollback()
            logger.error(f"خطأ في تسجيل الدفعة: {e}")
            raise
    
    def _check_debt_limits(self, driver_id: int, current_debt: float):
        """التحقق من حدود المديونية واتخاذ الإجراء المناسب"""
        driver_profile = self.session.query(DriverProfile).filter_by(
            user_id=driver_id
        ).first()
        
        if not driver_profile:
            return
        
        notifications = []
        
        # تحذير عند تجاوز عتبة التحذير
        if (current_debt >= config.debt.DEBT_WARNING_THRESHOLD and 
            current_debt < config.debt.MAX_DEBT_LIMIT):
            
            notifications.append(DebtNotification(
                driver_id=driver_id,
                message=f"تحذير: مديونيتك وصلت إلى {current_debt} ريال. الرجاء السداد قريباً.",
                notification_type="warning",
                debt_amount=current_debt,
                timestamp=datetime.utcnow()
            ))
        
        # إيقاف الحساب عند تجاوز الحد الأقصى
        elif (current_debt >= config.debt.MAX_DEBT_LIMIT and 
              config.debt.AUTO_SUSPEND):
            
            driver_profile.is_online = False
            driver_profile.user.status = "suspended"
            
            notifications.append(DebtNotification(
                driver_id=driver_id,
                message=f"تم إيقاف حسابك بسبب تجاوز حد المديونية ({current_debt} ريال). الرجاء السداد.",
                notification_type="suspension",
                debt_amount=current_debt,
                timestamp=datetime.utcnow()
            ))
        
        # حفظ التغييرات
        self.session.commit()
        
        # إرسال الإشعارات (سيتم تنفيذها في المعالجات)
        return notifications
    
    def get_driver_debt_summary(self, driver_id: int) -> Dict[str, Any]:
        """الحصول على ملخص مديونية السائق"""
        try:
            driver_profile = self.session.query(DriverProfile).filter_by(
                user_id=driver_id
            ).first()
            
            if not driver_profile:
                return {}
            
            # حساب إجمالي الدفعات الشهرية
            month_ago = datetime.utcnow() - timedelta(days=30)
            
            monthly_transactions = self.session.query(DebtTransaction).filter(
                DebtTransaction.driver_id == driver_profile.id,
                DebtTransaction.created_at >= month_ago
            ).all()
            
            monthly_commission = sum(
                t.amount for t in monthly_transactions 
                if t.transaction_type == "commission" and t.amount > 0
            )
            
            monthly_payments = abs(sum(
                t.amount for t in monthly_transactions 
                if t.transaction_type == "payment" and t.amount < 0
            ))
            
            return {
                'driver_id': driver_id,
                'current_debt': driver_profile.current_debt,
                'debt_limit': config.debt.MAX_DEBT_LIMIT,
                'warning_threshold': config.debt.DEBT_WARNING_THRESHOLD,
                'is_suspended': driver_profile.user.status == "suspended",
                'monthly_stats': {
                    'total_commission': monthly_commission,
                    'total_payments': monthly_payments,
                    'transaction_count': len(monthly_transactions)
                },
                'can_work': (
                    driver_profile.current_debt < config.debt.MAX_DEBT_LIMIT and
                    driver_profile.user.status == "active"
                )
            }
            
        except Exception as e:
            logger.error(f"خطأ في جلب ملخص المديونية: {e}")
            return {}
