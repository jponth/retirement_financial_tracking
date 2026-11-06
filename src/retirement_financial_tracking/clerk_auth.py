from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import base64
import html
import os
import secrets
import time
from urllib.parse import quote

from fastapi import Request


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class ClerkSettings:
    enabled: bool
    publishable_key: str | None
    jwks_url: str | None
    jwt_issuer: str | None
    jwt_audience: str | None
    after_sign_in_url: str
    cookie_name: str
    app_session_ttl_seconds: int

    @classmethod
    def from_env(cls) -> "ClerkSettings":
        return cls(
            enabled=_env_flag("CLERK_ENABLED", default=False),
            publishable_key=os.getenv("CLERK_PUBLISHABLE_KEY")
            or os.getenv("NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY"),
            jwks_url=os.getenv("CLERK_JWKS_URL"),
            jwt_issuer=os.getenv("CLERK_JWT_ISSUER"),
            jwt_audience=os.getenv("CLERK_JWT_AUDIENCE"),
            after_sign_in_url=os.getenv("CLERK_AFTER_SIGN_IN_URL", "/workspace/"),
            cookie_name=os.getenv("CLERK_SESSION_COOKIE", "rft_clerk_session"),
            app_session_ttl_seconds=int(os.getenv("CLERK_APP_SESSION_TTL_SECONDS", "28800")),
        )

    def validate(self) -> None:
        if not self.enabled:
            return
        missing: list[str] = []
        if not self.publishable_key:
            missing.append("CLERK_PUBLISHABLE_KEY")
        if not self.jwks_url:
            missing.append("CLERK_JWKS_URL")
        if missing:
            joined = ", ".join(missing)
            raise RuntimeError(f"Clerk auth is enabled but missing required env vars: {joined}")


@lru_cache(maxsize=4)
def _jwks_client(jwks_url: str):
    try:
        import jwt
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Clerk auth requires PyJWT[crypto]. Install project dependencies again "
            "so the new auth dependency is available."
        ) from exc
    return jwt.PyJWKClient(jwks_url)


def protected_ui_path(path: str) -> bool:
    return path == "/" or path == "/workspace" or path.startswith("/workspace/") or path == "/simple" or path.startswith("/simple/")


def extract_session_token(request: Request, *, cookie_name: str) -> str | None:
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
        if token:
            return token

    cookie_token = request.cookies.get(cookie_name)
    if cookie_token:
        return cookie_token
    return None


@dataclass
class AppSession:
    claims: dict[str, object]
    expires_at: float


def new_app_session_id() -> str:
    return secrets.token_urlsafe(32)


def new_app_session(claims: dict[str, object], ttl_seconds: int) -> AppSession:
    return AppSession(claims=claims, expires_at=time.time() + ttl_seconds)


def current_app_session(
    sessions: dict[str, AppSession],
    request: Request,
    *,
    cookie_name: str,
) -> dict[str, object] | None:
    session_id = request.cookies.get(cookie_name)
    if not session_id:
        return None
    app_session = sessions.get(session_id)
    if app_session is None:
        return None
    if app_session.expires_at <= time.time():
        sessions.pop(session_id, None)
        return None
    return app_session.claims


def verify_session_token(token: str, settings: ClerkSettings) -> dict[str, object]:
    assert settings.jwks_url
    try:
        import jwt
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Clerk auth requires PyJWT[crypto]. Install project dependencies again "
            "so the new auth dependency is available."
        ) from exc
    signing_key = _jwks_client(settings.jwks_url).get_signing_key_from_jwt(token)
    options = {
        "verify_signature": True,
        "verify_exp": True,
        "verify_aud": bool(settings.jwt_audience),
        "verify_iss": bool(settings.jwt_issuer),
    }
    return jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        audience=settings.jwt_audience,
        issuer=settings.jwt_issuer,
        options=options,
    )


def authenticate_request(request: Request, settings: ClerkSettings) -> dict[str, object] | None:
    token = extract_session_token(request, cookie_name=settings.cookie_name)
    if not token:
        return None
    try:
        return verify_session_token(token, settings)
    except Exception:
        return None


def sign_in_redirect_target(path: str) -> str:
    return f"/sign-in?return_url={quote(path or '/', safe='')}"


def auth_complete_target(path: str) -> str:
    return f"/auth/complete?return_url={quote(path or '/', safe='')}"


def frontend_api_domain_from_publishable_key(publishable_key: str) -> str:
    parts = publishable_key.split("_")
    if len(parts) < 3:
        raise ValueError("Invalid Clerk publishable key format.")

    encoded_domain = parts[2]
    padding = "=" * (-len(encoded_domain) % 4)
    decoded = base64.urlsafe_b64decode(encoded_domain + padding).decode("utf-8")
    return decoded[:-1] if decoded.endswith("$") else decoded


def render_sign_in_html(settings: ClerkSettings, *, return_url: str | None = None) -> str:
    settings.validate()
    destination = return_url or settings.after_sign_in_url
    complete_url = auth_complete_target(destination)
    escaped_complete_url = html.escape(complete_url, quote=True)
    escaped_destination = html.escape(destination, quote=True)
    escaped_key = html.escape(settings.publishable_key or "", quote=True)
    frontend_domain = frontend_api_domain_from_publishable_key(settings.publishable_key or "")
    escaped_frontend_domain = html.escape(frontend_domain, quote=True)

    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Sign in</title>
    <style>
      body {{
        margin: 0;
        min-height: 100vh;
        display: grid;
        place-items: center;
        background: #EAE4D6;
        color: #332F22;
        font-family: Georgia, "Times New Roman", serif;
      }}
      .shell {{
        width: min(100%, 460px);
        margin: 2rem;
        padding: 1.5rem;
        border: 1px solid #D8D1BB;
        border-radius: 18px;
        background: #F7F2E8;
        box-shadow: 0 14px 30px rgba(70, 65, 47, 0.08);
      }}
      h1 {{
        margin-top: 0;
      }}
      p {{
        line-height: 1.55;
      }}
      #clerk-error {{
        margin-top: 0.9rem;
        color: #8A4A14;
        font-size: 0.95rem;
        line-height: 1.45;
      }}
    </style>
    <script
      defer
      crossorigin="anonymous"
      src="https://{escaped_frontend_domain}/npm/@clerk/ui@1/dist/ui.browser.js"
      type="text/javascript"></script>
    <script
      defer
      crossorigin="anonymous"
      data-clerk-publishable-key="{escaped_key}"
      src="https://{escaped_frontend_domain}/npm/@clerk/clerk-js@6/dist/clerk.browser.js"
      type="text/javascript"></script>
  </head>
  <body>
    <div class="shell">
      <h1>Sign in</h1>
      <p>Sign in to access Retirement Financial Tracking.</p>
      <div id="clerk-sign-in"></div>
      <div id="clerk-error"></div>
    </div>
    <script>
      async function mountClerkSignIn() {{
        const errorNode = document.getElementById("clerk-error");
        try {{
          if (!window.Clerk) {{
            throw new Error("Clerk browser SDK did not load.");
          }}

          await window.Clerk.load({{
            ui: {{
              ClerkUI: window.__internal_ClerkUICtor,
            }},
          }});

          if (window.Clerk.isSignedIn) {{
            window.location.assign("{escaped_complete_url}");
            return;
          }}

          window.Clerk.mountSignIn(document.getElementById("clerk-sign-in"), {{
            afterSignInUrl: "{escaped_complete_url}",
            afterSignUpUrl: "{escaped_complete_url}"
          }});
        }} catch (error) {{
          console.error("Clerk sign-in failed to mount.", error);
          if (errorNode) {{
            errorNode.textContent = error && error.message
              ? `Clerk sign-in failed to load: ${{error.message}}`
              : "Clerk sign-in failed to load. Check the browser console and Clerk app configuration.";
          }}
        }}
      }}

      window.addEventListener("load", mountClerkSignIn, {{ once: true }});
    </script>
  </body>
</html>
"""


def render_auth_complete_html(settings: ClerkSettings, *, return_url: str | None = None) -> str:
    settings.validate()
    destination = return_url or settings.after_sign_in_url
    escaped_destination = html.escape(destination, quote=True)
    escaped_key = html.escape(settings.publishable_key or "", quote=True)
    frontend_domain = frontend_api_domain_from_publishable_key(settings.publishable_key or "")
    escaped_frontend_domain = html.escape(frontend_domain, quote=True)

    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Completing sign in</title>
    <style>
      body {{
        margin: 0;
        min-height: 100vh;
        display: grid;
        place-items: center;
        background: #EAE4D6;
        color: #332F22;
        font-family: Georgia, "Times New Roman", serif;
      }}
      .shell {{
        width: min(100%, 460px);
        margin: 2rem;
        padding: 1.5rem;
        border: 1px solid #D8D1BB;
        border-radius: 18px;
        background: #F7F2E8;
        box-shadow: 0 14px 30px rgba(70, 65, 47, 0.08);
      }}
      #clerk-error {{
        margin-top: 0.9rem;
        color: #8A4A14;
        font-size: 0.95rem;
        line-height: 1.45;
      }}
    </style>
    <script
      defer
      crossorigin="anonymous"
      src="https://{escaped_frontend_domain}/npm/@clerk/ui@1/dist/ui.browser.js"
      type="text/javascript"></script>
    <script
      defer
      crossorigin="anonymous"
      data-clerk-publishable-key="{escaped_key}"
      src="https://{escaped_frontend_domain}/npm/@clerk/clerk-js@6/dist/clerk.browser.js"
      type="text/javascript"></script>
  </head>
  <body>
    <div class="shell">
      <h1>Completing sign in</h1>
      <p>Please wait while your session is prepared.</p>
      <div id="clerk-error"></div>
    </div>
    <script>
      async function finalizeClerkSignIn() {{
        const errorNode = document.getElementById("clerk-error");
        try {{
          if (!window.Clerk) {{
            throw new Error("Clerk browser SDK did not load.");
          }}

          await window.Clerk.load({{
            ui: {{
              ClerkUI: window.__internal_ClerkUICtor,
            }},
          }});

          if (!window.Clerk.session) {{
            throw new Error("No active Clerk session was found after sign-in.");
          }}

          const token = await window.Clerk.session.getToken();
          if (!token) {{
            throw new Error("Clerk did not return a session token.");
          }}

          const response = await fetch("/auth/session", {{
            method: "POST",
            headers: {{
              "Content-Type": "application/json",
            }},
            credentials: "same-origin",
            body: JSON.stringify({{
              token: token,
            }}),
          }});

          if (!response.ok) {{
            const payload = await response.json().catch(() => ({{ detail: "Unable to finalize sign-in." }}));
            throw new Error(payload.detail || "Unable to finalize sign-in.");
          }}

          window.location.assign("{escaped_destination}");
        }} catch (error) {{
          console.error("Clerk sign-in finalization failed.", error);
          if (errorNode) {{
            errorNode.textContent = error && error.message
              ? `Unable to complete sign-in: ${{error.message}}`
              : "Unable to complete sign-in.";
          }}
        }}
      }}

      window.addEventListener("load", finalizeClerkSignIn, {{ once: true }});
    </script>
  </body>
</html>
"""


def render_sign_out_html(settings: ClerkSettings) -> str:
    settings.validate()
    escaped_key = html.escape(settings.publishable_key or "", quote=True)
    frontend_domain = frontend_api_domain_from_publishable_key(settings.publishable_key or "")
    escaped_frontend_domain = html.escape(frontend_domain, quote=True)
    sign_in_target = html.escape(sign_in_redirect_target(settings.after_sign_in_url), quote=True)

    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Signing out</title>
    <style>
      body {{
        margin: 0;
        min-height: 100vh;
        display: grid;
        place-items: center;
        background: #EAE4D6;
        color: #332F22;
        font-family: Georgia, "Times New Roman", serif;
      }}
      .shell {{
        width: min(100%, 460px);
        margin: 2rem;
        padding: 1.5rem;
        border: 1px solid #D8D1BB;
        border-radius: 18px;
        background: #F7F2E8;
        box-shadow: 0 14px 30px rgba(70, 65, 47, 0.08);
      }}
      #clerk-error {{
        margin-top: 0.9rem;
        color: #8A4A14;
        font-size: 0.95rem;
        line-height: 1.45;
      }}
      a {{
        color: #5C5E46;
      }}
    </style>
    <script
      defer
      crossorigin="anonymous"
      src="https://{escaped_frontend_domain}/npm/@clerk/ui@1/dist/ui.browser.js"
      type="text/javascript"></script>
    <script
      defer
      crossorigin="anonymous"
      data-clerk-publishable-key="{escaped_key}"
      src="https://{escaped_frontend_domain}/npm/@clerk/clerk-js@6/dist/clerk.browser.js"
      type="text/javascript"></script>
  </head>
  <body>
    <div class="shell">
      <h1>Signing out</h1>
      <p>Please wait while your session is closed.</p>
      <div id="clerk-error"></div>
      <p><a href="{sign_in_target}">Return to sign in</a></p>
    </div>
    <script>
      async function completeSignOut() {{
        const errorNode = document.getElementById("clerk-error");
        try {{
          if (window.Clerk) {{
            await window.Clerk.load({{
              ui: {{
                ClerkUI: window.__internal_ClerkUICtor,
              }},
            }});
            await window.Clerk.signOut();
          }}
        }} catch (error) {{
          console.error("Clerk sign-out failed.", error);
          if (errorNode) {{
            errorNode.textContent = error && error.message
              ? `Clerk sign-out had an issue: ${{error.message}}`
              : "Clerk sign-out had an issue.";
          }}
        }} finally {{
          window.location.assign("{sign_in_target}");
        }}
      }}

      window.addEventListener("load", completeSignOut, {{ once: true }});
    </script>
  </body>
</html>
"""
