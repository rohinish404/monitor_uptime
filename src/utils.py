

class URLValidationError(Exception):
    """Raised when a URL is invalid or malformed"""
    pass

class WebhookDeliveryError(Exception):
    """Raised when a Discord webhook notification fails"""
    pass

class NetworkTimeoutError(Exception):
    """Raised when a website check times out"""
    pass

