from django.contrib import admin
from .models import Enquiry, NewsletterSubscriber, Notification
admin.site.register(Notification)
admin.site.register(NewsletterSubscriber)
admin.site.register(Enquiry)
