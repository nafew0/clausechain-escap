from django.conf import settings


class ContentSecurityPolicyMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        policy = getattr(settings, "CONTENT_SECURITY_POLICY", "").strip()
        if policy and "Content-Security-Policy" not in response:
            response["Content-Security-Policy"] = policy
        return response

