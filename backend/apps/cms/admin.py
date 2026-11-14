from django.contrib import admin
from .models import Banner, BusinessSetting, HomepageSection, Page
admin.site.register(BusinessSetting)
admin.site.register(Page)
admin.site.register(HomepageSection)
admin.site.register(Banner)
