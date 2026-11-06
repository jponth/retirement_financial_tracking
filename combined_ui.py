from __future__ import annotations

from fastapi import FastAPI
from fastapi import HTTPException
from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
import gradio as gr
import uvicorn
from pydantic import BaseModel

import app as workspace_app
import simple_spa_app
from retirement_financial_tracking.clerk_auth import (
    AppSession,
    ClerkSettings,
    current_app_session,
    new_app_session,
    new_app_session_id,
    protected_ui_path,
    render_auth_complete_html,
    render_sign_in_html,
    render_sign_out_html,
    sign_in_redirect_target,
    verify_session_token,
)
from retirement_financial_tracking import load_app_metadata
from retirement_financial_tracking.ui_theme import mojave_sage_theme


WORKSPACE_PATH = "/workspace"
SIMPLE_PATH = "/simple"


class SessionTokenPayload(BaseModel):
    token: str


def build_combined_app() -> FastAPI:
    metadata = load_app_metadata()
    clerk_settings = ClerkSettings.from_env()
    clerk_settings.validate()
    shell = FastAPI(title=f"{metadata.product_display_name} Combined UI")
    app_sessions: dict[str, AppSession] = {}

    workspace_blocks = workspace_app.build_ui(show_combined_nav=True)
    simple_blocks = simple_spa_app.build_ui(show_combined_nav=True)

    @shell.middleware("http")
    async def require_clerk_for_ui(request: Request, call_next):
        if clerk_settings.enabled and protected_ui_path(request.url.path):
            claims = current_app_session(
                app_sessions,
                request,
                cookie_name=clerk_settings.cookie_name,
            )
            if claims is None:
                if request.method in {"GET", "HEAD"}:
                    return RedirectResponse(url=sign_in_redirect_target(request.url.path))
                return JSONResponse({"detail": "Authentication required."}, status_code=401)
            request.state.clerk_claims = claims
        return await call_next(request)

    @shell.get("/", include_in_schema=False)
    def index() -> RedirectResponse:
        return RedirectResponse(url=f"{WORKSPACE_PATH}/")

    @shell.get("/sign-in", include_in_schema=False, response_class=HTMLResponse)
    def sign_in(request: Request, return_url: str | None = None):
        if not clerk_settings.enabled:
            return RedirectResponse(url=f"{WORKSPACE_PATH}/")
        if current_app_session(app_sessions, request, cookie_name=clerk_settings.cookie_name):
            return RedirectResponse(url=return_url or clerk_settings.after_sign_in_url)
        return HTMLResponse(render_sign_in_html(clerk_settings, return_url=return_url))

    @shell.get("/auth/complete", include_in_schema=False, response_class=HTMLResponse)
    def auth_complete(request: Request, return_url: str | None = None):
        if not clerk_settings.enabled:
            return RedirectResponse(url=f"{WORKSPACE_PATH}/")
        if current_app_session(app_sessions, request, cookie_name=clerk_settings.cookie_name):
            return RedirectResponse(url=return_url or clerk_settings.after_sign_in_url)
        return HTMLResponse(render_auth_complete_html(clerk_settings, return_url=return_url))

    @shell.post("/auth/session", include_in_schema=False)
    def create_auth_session(payload: SessionTokenPayload):
        try:
            claims = verify_session_token(payload.token, clerk_settings)
        except Exception as exc:
            raise HTTPException(
                status_code=401,
                detail=f"Unable to verify Clerk session token: {exc}",
            ) from exc

        session_id = new_app_session_id()
        app_sessions[session_id] = new_app_session(claims, clerk_settings.app_session_ttl_seconds)

        response = JSONResponse({"ok": True})
        response.set_cookie(
            clerk_settings.cookie_name,
            session_id,
            max_age=clerk_settings.app_session_ttl_seconds,
            httponly=True,
            samesite="lax",
            secure=False,
            path="/",
        )
        return response

    @shell.get("/sign-out", include_in_schema=False, response_class=HTMLResponse)
    def sign_out(request: Request):
        session_id = request.cookies.get(clerk_settings.cookie_name)
        if session_id:
            app_sessions.pop(session_id, None)

        if not clerk_settings.enabled:
            response = RedirectResponse(url=f"{WORKSPACE_PATH}/")
            response.delete_cookie(clerk_settings.cookie_name, path="/")
            return response

        response = HTMLResponse(render_sign_out_html(clerk_settings))
        response.delete_cookie(clerk_settings.cookie_name, path="/")
        return response

    @shell.get("/workspace", include_in_schema=False)
    def workspace_redirect() -> RedirectResponse:
        return RedirectResponse(url=f"{WORKSPACE_PATH}/")

    @shell.get("/simple", include_in_schema=False)
    def simple_redirect() -> RedirectResponse:
        return RedirectResponse(url=f"{SIMPLE_PATH}/")

    gr.mount_gradio_app(
        shell,
        workspace_blocks,
        path=WORKSPACE_PATH,
        theme=mojave_sage_theme(),
        css=workspace_app.CSS,
    )
    gr.mount_gradio_app(
        shell,
        simple_blocks,
        path=SIMPLE_PATH,
        theme=mojave_sage_theme(),
        css=simple_spa_app.CSS,
    )
    return shell


def main() -> None:
    uvicorn.run(
        build_combined_app(),
        host="127.0.0.1",
        port=7860,
        timeout_graceful_shutdown=0,
    )


if __name__ == "__main__":
    main()
