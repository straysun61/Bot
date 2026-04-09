from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer, APIKeyHeader
from jose import JWTError, jwt
from core.config import settings
from pydantic import BaseModel

# 这通常用于前端登录界面 (如果他们通过表单登录)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/v1/auth/token", auto_error=False)

# 用于 API Key 验证 (来自 Header，例如提供给 B端客户或内部系统使用)
api_key_header = APIKeyHeader(name=settings.API_KEY_NAME, auto_error=False)

class TokenData(BaseModel):
    username: str | None = None

def get_current_user_or_api_key(
    token: str = Depends(oauth2_scheme), 
    api_key: str = Depends(api_key_header)
):
    """
    双层鉴权拦截器：同时支持 Access Token 和 API Key。
    如果有合法的 API Key，放行（主要用于服务器间的调用）。
    如果有合法的 Access Token (JWT)，放行并返回用户信息。
    如果都没有或非法，拦截请求。
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    # 1. 检查是否存在有效的 API Key
    if api_key:
        if api_key in settings.VALID_API_KEYS:
            return {"user": "api_client", "type": "api_key"}
        else:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, 
                detail="Invalid API Key"
            )

    # 2. 如果没有 API Key，检查 Token
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated. Provide Bearer token or API key.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except JWTError:
        raise credentials_exception
        
    # 在真实系统中，你还应该去数据库查一下这个 user 在不在
    # user = get_user(db, username=token_data.username) ...
    return {"user": token_data.username, "type": "access_token"}

def get_current_active_user(current_user: dict = Depends(get_current_user_or_api_key)):
    # 可用于检查用户状态（如是否被禁用/封禁）
    return current_user
