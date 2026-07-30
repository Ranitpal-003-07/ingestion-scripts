import logging
import random
import time

from django.http import HttpResponse, JsonResponse

logger = logging.getLogger(__name__)


def health(request):
    logger.info("health check")
    return HttpResponse("ok\n", content_type="text/plain")


def roll(request):
    value = random.randint(1, 6)
    logger.info("dice.roll value=%s", value)
    return HttpResponse(str(value), content_type="text/plain")


def work(request):
    logger.info("work.request started")
    for _min_ms, _max_ms in ((20, 80), (50, 200), (30, 120)):
        time.sleep(random.randint(_min_ms, _max_ms) / 1000)
    logger.info("work.request done")
    return JsonResponse({"status": "done"})
