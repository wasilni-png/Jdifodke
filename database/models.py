from sqlalchemy import (
    Column, Integer, String, Float, Boolean, 
    DateTime, Text, ForeignKey, Enum, JSON, Index
)
from sqlalchemy.orm import relationship, declarative_base
from datetime import datetime
import enum

Base = declarative_base()

# --- التعدادات (Enums) ---
class UserRole(enum.Enum):
    PASSENGER = "passenger"
    DRIVER = "driver"
    ADMIN = "admin"

class UserStatus(enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    BANNED = "banned"

class RideStatus(enum.Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    NO_DRIVERS = "no_drivers"

# --- الجداول ---

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(Integer, unique=True, index=True, nullable=False)
    username = Column(String(100))
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100))
    phone = Column(String(20))
    role = Column(Enum(UserRole), nullable=False)
    status = Column(Enum(UserStatus), default=UserStatus.ACTIVE)
    latitude = Column(Float); longitude = Column(Float)
    location_updated_at = Column(DateTime)
    total_rides = Column(Integer, default=0)
    rating = Column(Float, default=5.0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    driver_profile = relationship("DriverProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    # تم تصحيح طريقة كتابة الـ foreign_keys هنا لتجنب أخطاء AttributeError
    passenger_rides = relationship("Ride", foreign_keys="Ride.passenger_id", back_populates="passenger")
    driver_rides = relationship("Ride", foreign_keys="Ride.driver_id", back_populates="driver")

    __table_args__ = (
        Index('idx_user_location', 'latitude', 'longitude'),
        Index('idx_user_role_status', 'role', 'status'),
    )

class DriverProfile(Base):
    __tablename__ = "driver_profiles"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    vehicle_type = Column(String(50)); vehicle_model = Column(String(50))
    vehicle_color = Column(String(30)); license_plate = Column(String(20), unique=True)
    is_online = Column(Boolean, default=False); is_available = Column(Boolean, default=True)
    current_ride_id = Column(Integer, ForeignKey("rides.id"), nullable=True)
    wallet_balance = Column(Float, default=0.0); total_earnings = Column(Float, default=0.0); current_debt = Column(Float, default=0.0)
    license_number = Column(String(50), unique=True); license_image = Column(String(255)); vehicle_insurance = Column(String(255))

    user = relationship("User", back_populates="driver_profile")
    current_ride = relationship("Ride", foreign_keys=[current_ride_id])
    debt_transactions = relationship("DebtTransaction", back_populates="driver")

    __table_args__ = (Index('idx_driver_availability', 'is_online', 'is_available'),)

class Ride(Base):
    __tablename__ = "rides"
    id = Column(Integer, primary_key=True, index=True)
    ride_code = Column(String(20), unique=True, index=True)
    passenger_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    driver_id = Column(Integer, ForeignKey("users.id"))
    pickup_latitude = Column(Float, nullable=False); pickup_longitude = Column(Float, nullable=False)
    pickup_address = Column(String(255))
    destination_latitude = Column(Float, nullable=False); destination_longitude = Column(Float, nullable=False)
    destination_address = Column(String(255))
    distance_km = Column(Float); estimated_fare = Column(Float); final_fare = Column(Float)
    commission_amount = Column(Float); driver_earning = Column(Float)
    status = Column(Enum(RideStatus), default=RideStatus.PENDING)
    cancellation_reason = Column(String(255))
    requested_at = Column(DateTime, default=datetime.utcnow); accepted_at = Column(DateTime)
    started_at = Column(DateTime); completed_at = Column(DateTime)
    passenger_rating = Column(Integer); driver_rating = Column(Integer)
    passenger_comment = Column(Text); driver_comment = Column(Text)

    passenger = relationship("User", foreign_keys=[passenger_id], back_populates="passenger_rides")
    driver = relationship("User", foreign_keys=[driver_id], back_populates="driver_rides")
    chat_messages = relationship("ChatMessage", back_populates="ride")

    __table_args__ = (
        Index('idx_ride_status', 'status'),
        Index('idx_ride_passenger', 'passenger_id', 'status'),
        Index('idx_ride_driver', 'driver_id', 'status'),
        Index('idx_ride_timestamp', 'requested_at'),
    )

class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id = Column(Integer, primary_key=True, index=True)
    ride_id = Column(Integer, ForeignKey("rides.id", ondelete="CASCADE"), nullable=False)
    sender_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    message_type = Column(String(20), default="text"); content = Column(Text, nullable=False)
    extra_data = Column(JSON) # الاسم الجديد صحيح هنا
    is_delivered = Column(Boolean, default=False); is_read = Column(Boolean, default=False)
    sent_at = Column(DateTime, default=datetime.utcnow); delivered_at = Column(DateTime); read_at = Column(DateTime)

    ride = relationship("Ride", back_populates="chat_messages")
    sender = relationship("User")

    __table_args__ = (
        Index('idx_chat_ride', 'ride_id', 'sent_at'),
        Index('idx_chat_sender', 'sender_id'),
    )

class DebtTransaction(Base):
    __tablename__ = "debt_transactions"
    id = Column(Integer, primary_key=True, index=True)
    driver_id = Column(Integer, ForeignKey("driver_profiles.id"), nullable=False)
    ride_id = Column(Integer, ForeignKey("rides.id"))
    amount = Column(Float, nullable=False); transaction_type = Column(String(30)); description = Column(String(255))
    balance_before = Column(Float); balance_after = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)
    driver = relationship("DriverProfile", back_populates="debt_transactions")
    ride = relationship("Ride")

class AdminLog(Base):
    __tablename__ = "admin_logs"
    id = Column(Integer, primary_key=True, index=True)
    admin_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    action = Column(String(50), nullable=False); target_type = Column(String(30)); target_id = Column(Integer)
    details = Column(JSON); ip_address = Column(String(45))
    created_at = Column(DateTime, default=datetime.utcnow)
    admin = relationship("User")
