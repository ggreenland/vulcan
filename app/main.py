from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app.config import config
from app import database, auth
from app.controller import FireplaceController, get_controller


@asynccontextmanager
async def lifespan(app: FastAPI):
    await database.init_db()
    yield


app = FastAPI(
    title="Vulcan",
    description="Control your Valor fireplace via REST API",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="app/templates")


# ---------- Web UI ----------


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    user = await auth.get_current_user(request)
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "user": user,
            "google_client_id": config.GOOGLE_CLIENT_ID,
            "enable_api_keys": config.ENABLE_API_KEYS,
        },
    )


# ---------- Auth Routes ----------


@app.get("/auth/login")
async def login():
    state = auth.create_oauth_state()
    url = auth.get_google_auth_url(state)
    response = RedirectResponse(url=url)
    response.set_cookie(key="oauth_state", value=state, httponly=True, max_age=600)
    return response


@app.get("/auth/callback")
async def auth_callback(request: Request, code: str = None, state: str = None, error: str = None):
    if error:
        return RedirectResponse(url="/?error=" + error)

    if not code or not state:
        return RedirectResponse(url="/?error=missing_params")

    # Verify state
    stored_state = request.cookies.get("oauth_state")
    if not stored_state or stored_state != state or not auth.verify_oauth_state(state):
        return RedirectResponse(url="/?error=invalid_state")

    try:
        # Exchange code for token
        token_data = await auth.exchange_code_for_token(code)
        access_token = token_data.get("access_token")

        if not access_token:
            return RedirectResponse(url="/?error=no_token")

        # Get user info
        user_info = await auth.get_google_user_info(access_token)
        email = user_info.get("email")
        name = user_info.get("name", "")
        picture = user_info.get("picture", "")

        # Check allowlist
        if config.ALLOWED_EMAILS and email not in config.ALLOWED_EMAILS:
            return RedirectResponse(url="/?error=not_allowed")

        # Create or update user
        user = await database.get_or_create_user(email, name, picture)

        # Create session
        session_id = await database.create_session(user["id"])

        # Redirect with session cookie
        response = RedirectResponse(url="/")
        auth.set_session_cookie(response, session_id)
        response.delete_cookie("oauth_state")
        return response

    except Exception as e:
        print(f"Auth error: {e}")
        return RedirectResponse(url="/?error=auth_failed")


@app.post("/auth/logout")
async def logout(request: Request):
    session_id = auth.get_session_id_from_cookie(request)
    if session_id:
        await database.delete_session(session_id)

    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie("session")
    return response


# ---------- Health ----------


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "controller": config.FIREPLACE_CONTROLLER,
    }


# ---------- Test Endpoints (DEV_MODE only) ----------

if config.DEV_MODE:
    from app.fireplace import fireplace

    @app.get("/test/status")
    async def test_status():
        """Test endpoint - no auth, direct fireplace access. DEV_MODE only."""
        try:
            status = await fireplace.get_status()
            return {
                "power": status.power,
                "flame_level": status.flame_level,
                "burner2": status.burner2,
                "pilot": status.pilot,
                "raw": status.raw_response,
            }
        except ConnectionError as e:
            raise HTTPException(status_code=503, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/test/flame/{level}")
    async def test_flame(level: int):
        """Test endpoint - no auth, direct fireplace access. DEV_MODE only."""
        if not 0 <= level <= 100:
            raise HTTPException(status_code=400, detail="Level must be 0-100")
        success = await fireplace.set_flame_level(level)
        if success:
            return {"status": "ok", "flame_level": level}
        raise HTTPException(status_code=500, detail="Failed to set flame level")

    @app.post("/test/burner2/{state}")
    async def test_burner2(state: str):
        """Test endpoint - no auth, direct fireplace access. DEV_MODE only."""
        if state == "on":
            success = await fireplace.burner2_on()
        elif state == "off":
            success = await fireplace.burner2_off()
        else:
            raise HTTPException(status_code=400, detail="State must be 'on' or 'off'")
        if success:
            return {"status": "ok", "burner2": state}
        raise HTTPException(status_code=500, detail="Failed to control burner2")


# ---------- API Status ----------


@app.get("/api/status")
async def get_status(
    user: dict = Depends(auth.require_auth),
    controller: FireplaceController = Depends(get_controller),
):
    try:
        status = await controller.get_status()
        return {
            "power": status.power,
            "flame_level": status.flame_level,
            "burner2": status.burner2,
            "pilot": status.pilot,
        }
    except ConnectionError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------- Power Control ----------


@app.post("/api/power/on")
async def power_on(
    user: dict = Depends(auth.require_auth),
    controller: FireplaceController = Depends(get_controller),
):
    success = await controller.power_on()
    if success:
        return {"status": "ok", "message": "Fireplace turning on"}
    raise HTTPException(status_code=500, detail="Failed to turn on fireplace")


@app.post("/api/power/off")
async def power_off(
    user: dict = Depends(auth.require_auth),
    controller: FireplaceController = Depends(get_controller),
):
    success = await controller.power_off()
    if success:
        return {"status": "ok", "message": "Fireplace turning off"}
    raise HTTPException(status_code=500, detail="Failed to turn off fireplace")


# ---------- Flame Control ----------


@app.post("/api/flame/{level}")
async def set_flame(
    level: int,
    user: dict = Depends(auth.require_auth),
    controller: FireplaceController = Depends(get_controller),
):
    if not 0 <= level <= 100:
        raise HTTPException(status_code=400, detail="Level must be 0-100")

    success = await controller.set_flame_level(level)
    if success:
        return {"status": "ok", "flame_level": level}
    raise HTTPException(status_code=500, detail="Failed to set flame level")


# ---------- Burner2 Control ----------


@app.post("/api/burner2/on")
async def burner2_on(
    user: dict = Depends(auth.require_auth),
    controller: FireplaceController = Depends(get_controller),
):
    success = await controller.burner2_on()
    if success:
        return {"status": "ok", "burner2": True}
    raise HTTPException(status_code=500, detail="Failed to enable burner2")


@app.post("/api/burner2/off")
async def burner2_off(
    user: dict = Depends(auth.require_auth),
    controller: FireplaceController = Depends(get_controller),
):
    success = await controller.burner2_off()
    if success:
        return {"status": "ok", "burner2": False}
    raise HTTPException(status_code=500, detail="Failed to disable burner2")


# ---------- API Key Management (ENABLE_API_KEYS only) ----------


if config.ENABLE_API_KEYS:
    class CreateApiKeyRequest(BaseModel):
        name: str

    @app.get("/api/keys")
    async def list_api_keys(user: dict = Depends(auth.require_session)):
        keys = await database.get_user_api_keys(user["user_id"])
        return {"keys": keys}

    @app.post("/api/keys")
    async def create_api_key(body: CreateApiKeyRequest, user: dict = Depends(auth.require_session)):
        key_id, raw_key = await database.create_api_key(user["user_id"], body.name)
        return {
            "id": key_id,
            "name": body.name,
            "key": raw_key,
            "message": "Save this key - it won't be shown again!",
        }

    @app.delete("/api/keys/{key_id}")
    async def delete_api_key(key_id: int, user: dict = Depends(auth.require_session)):
        deleted = await database.delete_api_key(key_id, user["user_id"])
        if deleted:
            return {"status": "ok", "message": "API key deleted"}
        raise HTTPException(status_code=404, detail="API key not found")
