import os
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader, HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext

from core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

api_key_header = APIKeyHeader(name=settings.API_KEY_NAME, auto_error=False)
http_bearer = HTTPBearer(auto_error=False)


def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


async def verify_api_key(
    x_api_key: Optional[str] = Depends(api_key_header),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(http_bearer),
) -> str:
    """
    验证 API Key 或 Bearer Token。
    支持两种认证方式：
      1. Header: X-API-Key: <api_key>
      2. Header: Authorization: Bearer <token>
    返回通过验证的 key/token 字符串。
    """
    # 尝试 API Key
    if x_api_key and x_api_key in settings.VALID_API_KEYS:
        return x_api_key

    # 尝试 Bearer Token
    if credentials and credentials.credentials:
        token = credentials.credentials
        # 先检查是否是静态 API Key
        if token in settings.VALID_API_KEYS:
            return token
        # 再尝试 JWT 解码
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            return payload.get("sub", token)
        except JWTError:
            if token in settings.VALID_API_KEYS:
                return token

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing API key / Bearer token",
        headers={"WWW-Authenticate": "Bearer"},
    )
