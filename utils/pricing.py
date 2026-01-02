import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime, time

from config import config
from utils.location import Location, LocationService

logger = logging.getLogger(__name__)

@dataclass
class PricingFactors:
    """عوامل التسعير"""
    base_fare: float
    rate_per_km: float
    time_multiplier: float = 1.0
    demand_multiplier: float = 1.0
    vehicle_multiplier: float = 1.0

class PricingService:
    """خدمة حساب التكاليف"""
    
    @staticmethod
    def calculate_ride_fare(
        start_location: Location,
        end_location: Location,
        vehicle_type: str = "standard",
        ride_time: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        حساب تكلفة الرحلة
        
        Args:
            start_location: موقع البداية
            end_location: موقع النهاية
            vehicle_type: نوع المركبة
            ride_time: وقت الرحلة (لاحتساب الوقت الذروة)
        
        Returns:
            تفاصيل التكلفة
        """
        try:
            # حساب المسافة
            distance_km = LocationService.calculate_distance(
                start_location, end_location
            )
            
            # الحصول على عوامل التسعير
            factors = PricingService._get_pricing_factors(
                ride_time, vehicle_type
            )
            
            # حساب التكلفة الأساسية
            base_fare = factors.base_fare
            distance_fare = distance_km * factors.rate_per_km
            
            # تطبيق المضاعفات
            total_fare = base_fare + distance_fare
            total_fare *= factors.time_multiplier
            total_fare *= factors.demand_multiplier
            total_fare *= factors.vehicle_multiplier
            
            # التأكد من الحد الأدنى
            if total_fare < config.pricing.MINIMUM_FARE:
                total_fare = config.pricing.MINIMUM_FARE
            
            # حساب العمولة ودخل السائق
            commission = total_fare * config.pricing.COMMISSION_RATE
            driver_earning = total_fare - commission
            
            # تقريب القيم
            total_fare = round(total_fare, 2)
            commission = round(commission, 2)
            driver_earning = round(driver_earning, 2)
            
            return {
                'distance_km': round(distance_km, 2),
                'base_fare': round(base_fare, 2),
                'distance_fare': round(distance_fare, 2),
                'total_fare': total_fare,
                'commission_rate': config.pricing.COMMISSION_RATE,
                'commission_amount': commission,
                'driver_earning': driver_earning,
                'factors': {
                    'time_multiplier': factors.time_multiplier,
                    'demand_multiplier': factors.demand_multiplier,
                    'vehicle_multiplier': factors.vehicle_multiplier
                },
                'vehicle_type': vehicle_type
            }
            
        except Exception as e:
            logger.error(f"خطأ في حساب تكلفة الرحلة: {e}")
            raise
    
    @staticmethod
    def _get_pricing_factors(
        ride_time: Optional[datetime],
        vehicle_type: str
    ) -> PricingFactors:
        """الحصول على عوامل التسعير بناءً على الوقت ونوع المركبة"""
        
        # المضاعفات الافتراضية
        time_multiplier = 1.0
        demand_multiplier = 1.0
        vehicle_multiplier = 1.0
        
        # مضاعفات الوقت (الذروة)
        if ride_time:
            hour = ride_time.hour
            
            # وقت الذروة الصباحية (7-9 صباحًا)
            if 7 <= hour < 9:
                time_multiplier = 1.3
            
            # وقت الذروة المسائية (4-7 مساءً)
            elif 16 <= hour < 19:
                time_multiplier = 1.4
            
            # وقت الليل (10 مساءً - 5 صباحًا)
            elif 22 <= hour <= 23 or 0 <= hour < 5:
                time_multiplier = 1.2
        
        # مضاعفات الطلب (يمكن جلبها من قاعدة البيانات لاحقًا)
        # حالياً: ثابت
        demand_multiplier = 1.0
        
        # مضاعفات نوع المركبة
        vehicle_multipliers = {
            "standard": 1.0,
            "premium": 1.5,
            "luxury": 2.0,
            "van": 1.3,
            "motorcycle": 0.8
        }
        
        vehicle_multiplier = vehicle_multipliers.get(
            vehicle_type.lower(), 1.0
        )
        
        return PricingFactors(
            base_fare=config.pricing.BASE_FARE,
            rate_per_km=config.pricing.RATE_PER_KM,
            time_multiplier=time_multiplier,
            demand_multiplier=demand_multiplier,
            vehicle_multiplier=vehicle_multiplier
        )
    
    @staticmethod
    def calculate_driver_commission(ride_fare: float) -> Dict[str, float]:
        """حساب عمولة السائق"""
        commission_rate = config.pricing.COMMISSION_RATE
        commission = ride_fare * commission_rate
        driver_earning = ride_fare - commission
        
        return {
            'ride_fare': round(ride_fare, 2),
            'commission_rate': commission_rate,
            'commission_amount': round(commission, 2),
            'driver_earning': round(driver_earning, 2)
        }
