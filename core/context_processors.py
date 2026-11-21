def preferences(request):
    """Theme and language chosen by the visitor, read from cookies on every page (Unit VI)."""
    theme = request.COOKIES.get("se_theme", "light")
    lang = request.COOKIES.get("se_lang", "en")
    return {
        "pref_theme": theme if theme in {"light", "dark"} else "light",
        "pref_lang": lang if lang in {"en", "hi", "mr", "kok"} else "en",
    }
