"""
Custom middleware for JWT cookie authentication.
"""


class JWTCookieMiddleware:
    """
    Middleware to extract JWT tokens from HttpOnly cookies
    and add them to the Authorization header.
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        # Check if Authorization header already exists
        if not request.META.get('HTTP_AUTHORIZATION'):
            # Try to get access token from cookie
            access_token = request.COOKIES.get('access_token')
            
            if access_token:
                # Add Bearer token to Authorization header
                request.META['HTTP_AUTHORIZATION'] = f'Bearer {access_token}'
        
        response = self.get_response(request)
        return response
