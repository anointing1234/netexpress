from django.shortcuts import render
# from accounts.models import
from .models import Courier


# home pages

def home_view(request):
    return render(request,'index.html')

def about_us(request):
    return render(request,'about-us-2.html')

def services(request):
    return render(request,'services-2.html')

def contact(request):
    return render(request,'contact-us.html')




def tracking(request):
    tracking_number = request.GET.get("tracking_number", '').strip()

    if tracking_number:
        try:
            courier = Courier.objects.get(tracking_number=tracking_number)
            return render(request, "tracking_page.html", {"courier": courier})
        except Courier.DoesNotExist:
            return render(request, "tracking_page.html", {
                "error": f"Tracking number '{tracking_number}' was not found."
            })

    return render(request, "tracking_page.html")





