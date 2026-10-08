"""Default platform settings. Stored in the settings table on first run; edited by Super Admin."""

AI = {
    "provider": "ollama",  # ollama | anthropic | openai
    "providers": {
        "ollama": {"base_url": "http://localhost:11434", "model": "qwen3.5:4b", "api_key": ""},
        "anthropic": {"base_url": "https://api.anthropic.com", "model": "claude-sonnet-4-6", "api_key": ""},
        "openai": {"base_url": "https://api.openai.com/v1", "model": "gpt-4.1-mini", "api_key": ""},
    },
    "m1_model": "qwen3.5:4b",
    "m1_credits_per_page": 1,
    "temperature": 0.3,
    "max_tokens": 800,
    "daily_explanations_per_student": 100,
    "monthly_token_budget": 50000000,
    "depth_rules": {
        "exam": "Short, exam focused, key points and one example.",
        "concept_clarity": "Plain explanation, one analogy, one worked example.",
        "curiosity": "Explain the why and real world uses.",
        "research": "First principles, history and links to higher classes.",
    },
}

BRANDING = {
    "product_name": "EduVerse",
    "company_name": "zPROx.AI",
    "tagline": "Automate everything effortlessly",
    "accent": "#E0212F",
    "font": "Arial",
    "support_email": "",
}

FEATURES = {
    "student_store": True,
    "upcoming_books": True,
    "explain_panel": True,
    "notebook": True,
    "practice_questions": False,
    "knowledge_graph": False,
    "school_bulk_upload": True,
    "dark_mode": True,
}

PERMISSIONS = {
    "manage_admins": ["super_admin"],
    "manage_pricing": ["super_admin"],
    "manage_schools": ["super_admin"],
    # The factory: books in, books out. Platform Admin's job.
    "manage_catalogue": ["super_admin", "platform_admin"],
    "run_processing": ["super_admin", "platform_admin"],
    "manage_reviewers": ["super_admin", "platform_admin"],
    "manage_keys": ["super_admin", "platform_admin"],
    "review_books": ["super_admin", "reviewer"],
    "manage_students": ["super_admin", "admin"],
    "assign_books": ["super_admin", "admin"],
    "view_school_analytics": ["super_admin", "admin"],
    "view_platform_analytics": ["super_admin"],
    "read_books": ["student"],
}

M2 = {
    "enabled": True,          # run M2 after conversion, before the reviewer
    "provider": "openai",     # openai | gemini | local
    "providers": {
        "openai": {"base_url": "https://api.openai.com/v1", "model": "gpt-image-1", "api_key": "", "quality": "medium"},
        "gemini": {"base_url": "https://generativelanguage.googleapis.com/v1beta", "model": "imagen-4.0-generate-001", "api_key": ""},
        "local": {"base_url": "http://localhost:7860", "model": "", "api_key": "", "steps": 25},
    },
    "svg_redraw": True,       # diagrams, charts and maps M1 read as a structure are redrawn as SVG, no model
    "svg_kinds": ["diagram", "chart", "map"],
    "generate_kinds": ["photo", "diagram", "chart", "map"],
    "style_prompt": ("Clean, accurate illustration for a school science textbook. Plain white background, "
                     "flat colours, clear outlines, nothing decorative, no watermark, no border. "
                     "Draw only what the description says; do not add objects, people or text that are not in it."),
    "size": "auto",           # auto follows the original's shape, or e.g. 1024x1024
    "max_images_per_book": 100,
    "timeout_s": 180,
}

ALL = {"ai": AI, "branding": BRANDING, "features": FEATURES, "permissions": PERMISSIONS}
