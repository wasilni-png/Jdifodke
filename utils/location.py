import math
from typing import Tuple, List, Optional, Dict, Any
from dataclasses import dataclass
import logging
from geopy.distance import geodesic

from config import config
from database.models import User, DriverProfile

logger = logging.getLogger(__name__)

@dataclass
class Location:
    """تمثيل للموقع الجغرافي"""
    latitude: float
    longitude: float
    
    def to_tuple(self) -> Tuple[float, float]:
        return (self.latitude, self.longitude)

class LocationService:
    """خدمة معالجة المواقع الجغرافية"""
    
    @staticmethod
    def calculate_distance(
        loc1: Location,
        loc2: Location,
        method: str = "haversine"
    ) -> float:
        """
        حساب المسافة بين موقعين
        
        Args:
            loc1: الموقع الأول
            loc2: الموقع الثاني
            method: طريقة الحساب (haversine, vincenty, euclidean)
        
        Returns:
            المسافة بالكيلومترات
        """
        try:
            if method == "vincenty":
                # استخدام مكتبة geopy (أكثر دقة)
                return geodesic(loc1.to_tuple(), loc2.to_tuple()).kilometers
            else:
                # صيغة Haversine (أسرع)
                return LocationService._haversine_distance(loc1, loc2)
        except Exception as e:
            logger.error(f"خطأ في حساب المسافة: {e}")
            raise
    
    @staticmethod
    def _haversine_distance(loc1: Location, loc2: Location) -> float:
        """صيغة Haversine لحساب المسافة بين نقطتين على الكرة الأرضية"""
        # تحويل الدرجات إلى راديان
        lat1_rad = math.radians(loc1.latitude)
        lon1_rad = math.radians(loc1.longitude)
        lat2_rad = math.radians(loc2.latitude)
        lon2_rad = math.radians(loc2.longitude)
        
        # الفرق في الإحداثيات
        dlat = lat2_rad - lat1_rad
        dlon = lon2_rad - lon1_rad
        
        # صيغة Haversine
        a = math.sin(dlat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon/2)**2
        c = 2 * math.asin(math.sqrt(a))
        
        # المسافة بالكيلومترات
        distance = config.location.EARTH_RADIUS_KM * c
        return distance
    
    @staticmethod
    def find_nearby_drivers(
        passenger_location: Location,
        max_distance_km: Optional[float] = None,
        limit: int = 10,
        session = None
    ) -> List[Dict[str, Any]]:
        """
        البحث عن السائقين القريبين
        
        Args:
            passenger_location: موقع الراكب
            max_distance_km: أقصى مسافة (إذا لم يتم تحديد، يستخدم الإعدادات)
            limit: أقصى عدد من السائقين
            session: جلسة قاعدة البيانات
        
        Returns:
            قائمة بالسائقين القريبين مع معلومات المسافة
        """
        if max_distance_km is None:
            max_distance_km = config.location.SEARCH_RADIUS_KM
        
        try:
            # جلب جميع السائقين المتاحين
            drivers = session.query(User, DriverProfile).join(
                DriverProfile, User.id == DriverProfile.user_id
            ).filter(
                User.role == "driver",
                User.status == "active",
                DriverProfile.is_online == True,
                DriverProfile.is_available == True,
                User.latitude.isnot(None),
                User.longitude.isnot(None)
            ).all()
            
            nearby_drivers = []
            
            for user, profile in drivers:
                driver_location = Location(
                    latitude=user.latitude,
                    longitude=user.longitude
                )
                
                # حساب المسافة
                distance = LocationService.calculate_distance(
                    passenger_location,
                    driver_location
                )
                
                # إذا كانت المسافة ضمن النطاق المحدد
                if distance <= max_distance_km:
                    nearby_drivers.append({
                        'driver_id': user.id,
                        'telegram_id': user.telegram_id,
                        'first_name': user.first_name,
                        'vehicle_type': profile.vehicle_type,
                        'rating': user.rating,
                        'distance_km': round(distance, 2),
                        'latitude': user.latitude,
                        'longitude': user.longitude
                    })
            
            # ترتيب حسب المسافة
            nearby_drivers.sort(key=lambda x: x['distance_km'])
            
            # تحديد العدد المطلوب
            return nearby_drivers[:limit]
            
        except Exception as e:
            logger.error(f"خطأ في البحث عن سائقين: {e}")
            return []
    
    @staticmethod
    def estimate_travel_time(distance_km: float, traffic_factor: float = 1.2) -> Dict[str, float]:
        """
        تقدير وقت الرحلة
        
        Args:
            distance_km: المسافة بالكيلومترات
            traffic_factor: عامل الازدحام (1.0 = بدون ازدحام)
        
        Returns:
            وقت الرحلة بالدقائق مع تفاصيل
        """
        avg_speed_kmh = 40  # سرعة متوسطة 40 كم/ساعة
        
        # حساب الوقت الأساسي
        base_time_minutes = (distance_km / avg_speed_kmh) * 60
        
        # تطبيق عامل الازدحام
        estimated_time = base_time_minutes * traffic_factor
        
        # إضافة وقت التوقف والتقاط الراكب
        pickup_time = 5  # دقائق
        total_time = estimated_time + pickup_time
        
        return {
            'distance_km': distance_km,
            'base_time_minutes': round(base_time_minutes, 1),
            'traffic_factor': traffic_factor,
            'estimated_time_minutes': round(estimated_time, 1),
            'pickup_time_minutes': pickup_time,
            'total_time_minutes': round(total_time, 1)
        }
    
    @staticmethod
    def validate_coordinates(latitude: float, longitude: float) -> bool:
        """التحقق من صحة الإحداثيات الجغرافية"""
        return (-90 <= latitude <= 90) and (-180 <= longitude <= 180)
