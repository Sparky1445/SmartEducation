from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User

from .models import Profile


class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False
    fields = ("role", "grade", "school", "language", "bio")


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "grade", "language", "school")
    list_filter = ("role", "grade", "language")
    search_fields = ("user__username", "user__first_name", "user__email", "school")


admin.site.unregister(User)


@admin.register(User)
class UserWithProfileAdmin(UserAdmin):
    inlines = [ProfileInline]
    list_display = ("username", "first_name", "email", "role", "is_staff", "date_joined")
    list_filter = UserAdmin.list_filter + ("profile__role",)

    @admin.display(description="Role", ordering="profile__role")
    def role(self, obj):
        return obj.profile.get_role_display() if hasattr(obj, "profile") else "—"
