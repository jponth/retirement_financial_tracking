from retirement_financial_tracking.logging_setup import configure_app_logging
from retirement_financial_tracking.ui_theme import mojave_sage_theme
from simple_spa_app import CSS, build_ui


if __name__ == "__main__":
    configure_app_logging()
    build_ui().launch(css=CSS, theme=mojave_sage_theme())
