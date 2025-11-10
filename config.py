# Medium automation configuration (Selenium variant)

# Driver choice: "playwright" or "selenium"
MEDIUM_DRIVER = "selenium"

# Chrome profile paths (edit to match your machine)
CHROME_USER_DATA_DIR = r"D:\TOOL\Autopost social\profile medium"
CHROME_PROFILE_DIR = "Default"  # e.g., "Default" or a custom profile folder name

# Timing and behavior
WAIT_SHORT = 3
WAIT_MED = 12
CLICK_JITTER_PX = 4
TYPE_DELAY_MIN_S = 0.006
TYPE_DELAY_MAX_S = 0.018

# Selectors (scoped and stable for Medium editor)
SEL_MEDIUM = {
    "container": "div.postArticle-content[g_editable='true']",
    "title": (
        "div.postArticle-content [data-testid='editorTitleParagraph']",
        "[data-testid='editorTitleParagraph']",
        "div.postArticle-content [data-testid='editorTitle']",
    ),
    "body_p": (
        "div.postArticle-content span.defaultValue--root",
        "span.defaultValue--root",
        "div.postArticle-content p[data-testid='editorParagraphText']",
        "div.postArticle-content div[data-testid='editorParagraphText']",
        "div.postArticle-content p.graf--p",
        "div.postArticle-content [contenteditable='true'] p",
        "[data-testid='editorParagraphText']",
    ),
    "publish_btn": "button.js-publishButton:not(.button--disabled):not([aria-disabled='true']), button[data-action='publish']:not(.button--disabled):not([aria-disabled='true'])",
    "tags_input": (
        "div[data-testid='publishTopicsInput'][contenteditable='true']",
        "body > div.overlay.overlay--white > div > div > div > div:nth-child(3) > div.u-width100pct.u-marginBottom24 > div",
        "div.js-tagInput[contenteditable='true']",
        "div[data-testid='publishTopicsInput']",
        "input[data-testid='publishTopicsInput']",
        "input[placeholder*='Add a topic' i]",
    ),
}

# Retry policy for Selenium Medium flow
MEDIUM_SELENIUM_RETRIES = 1          # number of re-attempts on failure
MEDIUM_RETRY_DELAY_S = 1.2           # delay between attempts

# Schedule runner defaults
SCHEDULE_TABLE_PATH = "schedule_template.csv"
SCHEDULE_CONCURRENCY = 1
SCHEDULE_SHOW_CONSOLE = True
