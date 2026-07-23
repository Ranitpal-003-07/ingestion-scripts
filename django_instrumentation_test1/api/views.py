import random
import time

from django.http import HttpResponse, JsonResponse


def health(request):
    return HttpResponse("ok\n", content_type="text/plain")


def roll(request):
    return HttpResponse(str(random.randint(1, 6)), content_type="text/plain")


def work(request):
    for _min_ms, _max_ms in ((20, 80), (50, 200), (30, 120)):
        time.sleep(random.randint(_min_ms, _max_ms) / 1000)
    return JsonResponse({"status": "done"})
