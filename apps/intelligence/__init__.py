# apps/intelligence/__init__.py

def __getattr__(name):
    if name == 'MarketAIChatbot':
        from .chatbot_service import MarketAIChatbot
        return MarketAIChatbot
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ['MarketAIChatbot']
