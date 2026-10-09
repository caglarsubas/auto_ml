from django.apps import AppConfig


class AccessControlConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'access_control'

    def ready(self):
        from django.contrib.auth.signals import user_logged_in
        from access_control.session_authority import bind_login_session
        user_logged_in.connect(bind_login_session, dispatch_uid='declarai.bind_session_authority')
