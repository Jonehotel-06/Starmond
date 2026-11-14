from rest_framework.throttling import AnonRateThrottle, ScopedRateThrottle, UserRateThrottle


class BurstAnonThrottle(AnonRateThrottle):
    scope = "anon_burst"


class StandardUserThrottle(UserRateThrottle):
    scope = "user_standard"


class AuthActionThrottle(ScopedRateThrottle):
    scope = "auth_action"


class WebhookThrottle(AnonRateThrottle):
    scope = "webhook"
