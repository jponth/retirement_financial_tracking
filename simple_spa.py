from retirement_financial_tracking.ui_theme import mojave_sage_theme
from simple_spa_app import CSS, build_ui


if __name__ == "__main__":
    build_ui().launch(css=CSS, theme=mojave_sage_theme())
