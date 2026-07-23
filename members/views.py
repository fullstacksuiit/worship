from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from core.permissions import cap_required

from .forms import MemberForm
from .models import Member


@login_required
def member_list(request):
    q = request.GET.get("q", "").strip()
    members = Member.objects.filter(organization=request.organization)
    if q:
        members = members.filter(
            Q(name__icontains=q) | Q(phone__icontains=q) | Q(household__icontains=q)
        )
    return render(request, "members/list.html", {"members": members, "q": q})


@login_required
@cap_required("manage_people")
def member_add(request):
    if request.method == "POST":
        form = MemberForm(request.POST)
        if form.is_valid():
            member = form.save(commit=False)
            member.organization = request.organization
            member.save()
            messages.success(request, f"{member.name} added.")
            return redirect("members:detail", pk=member.pk)
    else:
        form = MemberForm()
    return render(request, "members/form.html", {"form": form, "mode": "add"})


@login_required
def member_detail(request, pk):
    member = get_object_or_404(Member, pk=pk, organization=request.organization)
    return render(request, "members/detail.html", {"member": member})


@login_required
@cap_required("manage_people")
def member_edit(request, pk):
    member = get_object_or_404(Member, pk=pk, organization=request.organization)
    if request.method == "POST":
        form = MemberForm(request.POST, instance=member)
        if form.is_valid():
            form.save()
            messages.success(request, "Changes saved.")
            return redirect("members:detail", pk=member.pk)
    else:
        form = MemberForm(instance=member)
    return render(request, "members/form.html", {"form": form, "mode": "edit", "member": member})


@login_required
@cap_required("manage_people")
def member_delete(request, pk):
    member = get_object_or_404(Member, pk=pk, organization=request.organization)
    if request.method == "POST":
        name = member.name
        member.delete()
        messages.success(request, f"{name} removed.")
        return redirect("members:list")
    return render(request, "members/confirm_delete.html", {"member": member})
