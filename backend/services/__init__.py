"""Service layer — business logic lives here, NOT in views/serializers.

Flow for every request:
REQUEST -> VALIDATION -> AUTHORIZATION -> SERVICE -> DB TRANSACTION -> AUDIT
        -> SECONDARY NOTIFICATION -> API RESPONSE
"""
