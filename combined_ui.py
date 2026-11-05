from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
import gradio as gr
import uvicorn

import app as workspace_app
import simple_spa_app
from retirement_financial_tracking import load_app_metadata
from retirement_financial_tracking.ui_theme import mojave_sage_theme


WORKSPACE_PATH = "/workspace"
SIMPLE_PATH = "/simple"


def build_combined_app() -> FastAPI:
    metadata = load_app_metadata()
    shell = FastAPI(title=f"{metadata.product_display_name} Combined UI")

    workspace_blocks = workspace_app.build_ui()
    simple_blocks = simple_spa_app.build_ui()

    @shell.get("/", include_in_schema=False)
    def index() -> RedirectResponse:
        return RedirectResponse(url=f"{WORKSPACE_PATH}/")

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
