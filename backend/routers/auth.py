from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt

# ---------------------------------------------------------------------------
# passlib + bcrypt version compatibility shim
# ---------------------------------------------------------------------------
# passlib 1.7.4 inspects ``bcrypt.__about__.__version__`` to decide which
# bcrypt rounds format to use. In bcrypt 4.x the attribute is exposed at the
# package level instead, so the lookup raises an AttributeError. We shim
# ``bcrypt.__about__`` BEFORE importing passlib so the version check succeeds
# silently. This prevents the noisy "(trapped) error reading bcrypt version"
# warning from cluttering the startup logs.
import bcrypt as _bcrypt
if not hasattr(_bcrypt, "__about__"):
    import types as _types

    _bcrypt.__about__ = _types.SimpleNamespace(__version__=_bcrypt.__version__)

from passlib.context import CryptContext
from datetime import datetime, timedelta

from config import settings
from models.schemas import LoginRequest, TokenResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])
security = HTTPBearer()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def verify_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )


async def get_current_admin(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    token = credentials.credentials
    payload = verify_token(token)
    username = payload.get("sub")
    if username != settings.ADMIN_USERNAME:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    return {"username": username}


@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest):
    if request.username != settings.ADMIN_USERNAME:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    if not pwd_context.verify(request.password, settings.ADMIN_PASSWORD_HASH):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    access_token = create_access_token(data={"sub": request.username})
    return TokenResponse(access_token=access_token)


@router.get("/verify")
async def verify(admin: dict = Depends(get_current_admin)):
    return {"status": "valid", "username": admin["username"]}
