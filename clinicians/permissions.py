from ninja.security import HttpBearer
from jose import JWTError, jwt
from django.contrib.auth.models import User
from .models import ClinicianProfile, VerificationStatus

SECRET_KEY = "your-secret-key-here"  # Use env var in production
ALGORITHM = "HS256"

class ClinicianAuth(HttpBearer):
    """
    JWT-based authentication for clinicians.
    Verifies license and active status.
    """
    
    def authenticate(self, request, token):
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            user_id = payload.get("sub")
            if user_id is None:
                return None
            
            user = User.objects.get(id=user_id)
            profile = getattr(user, 'clinician_profile', None)
            
            if not profile or not profile.is_verified():
                return None
            
            request.auth_user = user
            request.clinician_profile = profile
            return user
            
        except (JWTError, User.DoesNotExist):
            return None

class RoleBasedAccess:
    """
    Permission checks based on clinician role.
    """
    
    @staticmethod
    def can_view_population_data(profile: ClinicianProfile) -> bool:
        return profile.can_view_population_data or profile.role in ["ids", "pho", "moh"]
    
    @staticmethod
    def can_approve_guidance(profile: ClinicianProfile) -> bool:
        return profile.can_approve_guidance or profile.role in ["ids", "moh"]
    
    @staticmethod
    def can_override_threshold(profile: ClinicianProfile) -> bool:
        return profile.can_override_threshold or profile.role == "ids"
    
    @staticmethod
    def is_moh_admin(profile: ClinicianProfile) -> bool:
        return profile.role == "moh"

def require_verified_clinician(request):
    """Dependency to ensure only verified clinicians access endpoints"""
    profile = getattr(request, 'clinician_profile', None)
    if not profile or not profile.is_verified():
        raise Exception("Clinician not verified or license expired")
    return profile