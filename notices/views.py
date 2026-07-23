from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from core.permissions import cap_required

from .forms import NoticeForm
from .models import Notice


@login_required
def notice_list(request):
    notices = Notice.objects.filter(organization=request.organization)
    return render(request, "notices/list.html", {"notices": notices})


@login_required
def notice_detail(request, pk):
    notice = get_object_or_404(Notice, pk=pk, organization=request.organization)
    return render(request, "notices/detail.html", {"notice": notice})


@login_required
@cap_required("manage_notices")
def notice_add(request):
    if request.method == "POST":
        form = NoticeForm(request.POST)
        if form.is_valid():
            notice = form.save(commit=False)
            notice.organization = request.organization
            notice.author = request.user
            notice.save()
            messages.success(request, "Notice posted.")
            return redirect("notices:detail", pk=notice.pk)
    else:
        form = NoticeForm()
    return render(request, "notices/form.html", {"form": form, "mode": "add"})


@login_required
@cap_required("manage_notices")
def notice_edit(request, pk):
    notice = get_object_or_404(Notice, pk=pk, organization=request.organization)
    if request.method == "POST":
        form = NoticeForm(request.POST, instance=notice)
        if form.is_valid():
            form.save()
            messages.success(request, "Changes saved.")
            return redirect("notices:detail", pk=notice.pk)
    else:
        form = NoticeForm(instance=notice)
    return render(request, "notices/form.html", {"form": form, "mode": "edit", "notice": notice})


@login_required
@cap_required("manage_notices")
def notice_delete(request, pk):
    notice = get_object_or_404(Notice, pk=pk, organization=request.organization)
    if request.method == "POST":
        notice.delete()
        messages.success(request, "Notice removed.")
        return redirect("notices:list")
    return render(request, "notices/confirm_delete.html", {"notice": notice})
