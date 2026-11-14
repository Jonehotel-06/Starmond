import logging

from celery import shared_task
from django.conf import settings

logger = logging.getLogger("starmond.emails")


@shared_task(bind=True, name="apps.emails.tasks.send_email_task",
           max_retries=getattr(settings, "EMAIL_MAX_AUTO_ATTEMPTS", 4),
           default_retry_delay=60, acks_late=True)
def send_email_task(self, email_log_id):
    from .models import EmailLog
    from .services import EmailService
    log = EmailLog.objects.filter(pk=email_log_id).first()
    if not log:
        return "missing"
    if log.status == EmailLog.Status.SENT:
        return "already_sent"
    result = EmailService.deliver(email_log_id)
    if result and result.status == EmailLog.Status.FAILED and result.attempts < settings.EMAIL_MAX_AUTO_ATTEMPTS:
        raise self.retry(countdown=60 * min(2 ** (result.attempts - 1), 16))
    return result.status if result else "unknown"


@shared_task(name="apps.emails.tasks.retry_failed_emails")
def retry_failed_emails():
    """Beat task: requeue failed emails below the attempt ceiling."""
    from .models import EmailLog
    failed = EmailLog.objects.filter(status=EmailLog.Status.FAILED,
                                     attempts__lt=settings.EMAIL_MAX_AUTO_ATTEMPTS)
    count = 0
    for log in failed[:100]:
        send_email_task.delay(log.pk)
        count += 1
    if count:
        logger.info("Requeued %s failed email(s)", count)
    return count
