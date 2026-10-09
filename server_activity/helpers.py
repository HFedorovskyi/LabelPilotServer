from server_activity.models import ServerEvent


def log_event(action: str, description: str) -> ServerEvent:
    """
    Создаёт запись в серверной ленте действий.
    
    Использование:
        from server_activity.helpers import log_event
        log_event('job_created', 'Создано задание #45 для станции #03')
    """
    return ServerEvent.objects.create(action=action, description=description)
