from sqlalchemy import (
    Column, Integer, String, Float, Boolean, 
    DateTime, Text, ForeignKey, Enum, JSON, Index
)
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.sql import func
from datetime import datetime
import enum

Base = declarative_base()

class UserRole(enum.Enum):
    """أدوار المستخدمين في النظام"""
    PASSENGER = "passenger"
    DRIVER = "driver"
    ADMIN = "admin"

class UserStatus(enum.Enum):
    """حالة المستخدم"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    BANNED = "banned"

class RideStatus(enum.Enum):
    """حالة الرحلة"""
    PENDING = "pending"           # في انتظار السائق
    ACCEPTED = "accepted"         # قبلها سائق
    IN_PROGRESS = "in_progress"   # الرحلة جارية
    COMPLETED = "completed"       # اكتملت
    CANCELLED = "cancelled"       # ألغيت
    NO_DRIVERS = "no_drivers"     # لا يوجد سائقين

class User(Base):
    """جدول المستخدمين"""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(Integer, unique=True, index=True, nullable=False)
    username = Column(String(100))
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100))
    phone = Column(String(20))
    role = Column(Enum(UserRole), nullable=False)
    status = Column(Enum(UserStatus), default=UserStatus.ACTIVE)
    
    # الموقع الجغرافي
    latitude = Column(Float)
    longitude = Column(Float)
    location_updated_at = Column(DateTime)
    
    # إحصائيات
    total_rides = Column(Integer, default=0)
    rating = Column(Float, default=5.0)
    
    # الطابع الزمني
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # العلاقات
    driver_profile = relationship("DriverProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    passenger_rides = relationship("Ride", foreign_keys="[Ride.passenger_id]", back_populates="passenger")
    driver_rides = relationship("Ride", foreign_keys="[Ride.driver_id]", back_populates="driver")
    
    # فهارس
    __table_args__ = (
        Index('idx_user_location', 'latitude', 'longitude'),
        Index('idx_user_role_status', 'role', 'status'),
    )

class DriverProfile(Base):
    """جدول ملفات السائقين"""
    __tablename__ = "driver_profiles"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    
    # معلومات المركبة
    vehicle_type = Column(String(50))
    vehicle_model = Column(String(50))
    vehicle_color = Column(String(30))
    license_plate = Column(String(20), unique=True)
    
    # حالة العمل
    is_online = Column(Boolean, default=False)
    is_available = Column(Boolean, default=True)
    current_ride_id = Column(Integer, ForeignKey("rides.id"), nullable=True)
    
    # المالية
    wallet_balance = Column(Float, default=0.0)
    total_earnings = Column(Float, default=0.0)
    current_debt = Column(Float, default=0.0)
    
    # وثائق
    license_number = Column(String(50), unique=True)
    license_image = Column(String(255))  # مسار الصورة
    vehicle_insurance = Column(String(255))
    
    # العلاقات
    user = relationship("User", back_populates="driver_profile")
    current_ride = relationship("Ride", foreign_keys=[current_ride_id])
    debt_transactions = relationship("DebtTransaction", back_populates="driver")
    
    __table_args__ = (
        Index('idx_driver_availability', 'is_online', 'is_available'),
    )

class Ride(Base):
    """جدول الرحلات"""
    __tablename__ = "rides"
    
    id = Column(Integer, primary_key=True, index=True)
    ride_code = Column(String(20), unique=True, index=True)  # كود الرحلة: RIDE-001
    
    # المستخدمين
    passenger_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    driver_id = Column(Integer, ForeignKey("users.id"))
    
    # الموقع
    pickup_latitude = Column(Float, nullable=False)
    pickup_longitude = Column(Float, nullable=False)
    pickup_address = Column(String(255))
    
    destination_latitude = Column(Float, nullable=False)
    destination_longitude = Column(Float, nullable=False)
    destination_address = Column(String(255))
    
    # التكلفة
    distance_km = Column(Float)
    estimated_fare = Column(Float)
    final_fare = Column(Float)
    commission_amount = Column(Float)
    driver_earning = Column(Float)
    
    # الحالة
    status = Column(Enum(RideStatus), default=RideStatus.PENDING)
    cancellation_reason = Column(String(255))
    
    # التوقيت
    requested_at = Column(DateTime, default=datetime.utcnow)
    accepted_at = Column(DateTime)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    
    # تقييم
    passenger_rating = Column(Integer)  # 1-5
    driver_rating = Column(Integer)     # 1-5
    passenger_comment = Column(Text)
    driver_comment = Column(Text)
    
    # العلاقات
    passenger = relationship("User", foreign_keys=[passenger_id], back_populates="passenger_rides")
    driver = relationship("User", foreign_keys=[driver_id], back_populates="driver_rides")
    chat_messages = relationship("ChatMessage", back_populates="ride")
    
    # فهارس
    __table_args__ = (
        Index('idx_ride_status', 'status'),
        Index('idx_ride_passenger', 'passenger_id', 'status'),
        Index('idx_ride_driver', 'driver_id', 'status'),
        Index('idx_ride_timestamp', 'requested_at'),
    )

class ChatMessage(Base):
    """جدول رسائل الدردشة الوسيطة"""
    __tablename__ = "chat_messages"
    
    id = Column(Integer, primary_key=True, index=True)
    ride_id = Column(Integer, ForeignKey("rides.id", ondelete="CASCADE"), nullable=False)
    sender_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # المحتوى
    message_type = Column(String(20), default="text")  # text, location, image, etc.
    content = Column(Text, nullable=False)
    extra_data = Column(JSON)  # لحفظ معلومات إضافية
    
    # الحالة
    is_delivered = Column(Boolean, default=False)
    is_read = Column(Boolean, default=False)
    
    # التوقيت
    sent_at = Column(DateTime, default=datetime.utcnow)
    delivered_at = Column(DateTime)
    read_at = Column(DateTime)
    
    # العلاقات
    ride = relationship("Ride", back_populates="chat_messages")
    sender = relationship("User")
    
    __table_args__ = (
        Index('idx_chat_ride', 'ride_id', 'sent_at'),
        Index('idx_chat_sender', 'sender_id'),
    )

class DebtTransaction(Base):
    """جدول معاملات المديونية"""
    __tablename__ = "debt_transactions"
    
    id = Column(Integer, primary_key=True, index=True)
    driver_id = Column(Integer, ForeignKey("driver_profiles.id"), nullable=False)
    ride_id = Column(Integer, ForeignKey("rides.id"))
    
    # المبلغ
    amount = Column(Float, nullable=False)
    transaction_type = Column(String(30))  # commission, payment, adjustment, penalty
    description = Column(String(255))
    
    # الرصيد قبل وبعد
    balance_before = Column(Float)
    balance_after = Column(Float)
    
    # التوقيت
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # العلاقات
    driver = relationship("DriverProfile", back_populates="debt_transactions")
    ride = relationship("Ride")
    
    __table_args__ = (
        Index('idx_debt_driver', 'driver_id', 'created_at'),
    )

class AdminLog(Base):
    """جدول سجلات الأدمن"""
    __tablename__ = "admin_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    admin_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # الإجراء
    action = Column(String(50), nullable=False)  # ban_user, unban_user, view_report, etc.
    target_type = Column(String(30))  # user, ride, driver, etc.
    target_id = Column(Integer)
    
    # التفاصيل
    details = Column(JSON)
    ip_address = Column(String(45))
    
    # التوقيت
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # العلاقات
    admin = relationship("User")
