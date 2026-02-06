import pusher
from django.conf import settings

pusher_client = None

if settings.PUSHER_APP_ID:
    try:
        pusher_client = pusher.Pusher(
            app_id=settings.PUSHER_APP_ID,
            key=settings.PUSHER_KEY,
            secret=settings.PUSHER_SECRET,
            cluster=settings.PUSHER_CLUSTER,
            ssl=True
        )
    except Exception as e:
        print(f"Failed to initialize Pusher: {e}")

def send_notification(message):
    if pusher_client:
        try:
            pusher_client.trigger('notifications', 'new-notification', {'message': message})
        except Exception as e:
            print(f"Failed to send notification: {e}")