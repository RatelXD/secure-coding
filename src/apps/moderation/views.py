from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods
from apps.accounts.services import project_account_identity

from apps.catalog.models import Product

from .forms import ReportReasonForm, UserReportForm
from .policies import ReportContext, TargetType
from .services import ReportSubmissionError, submit_report, visible_products


_GENERIC_ERROR = "신고를 처리할 수 없습니다. 입력 내용을 확인해 주세요."


def _render_report_form(
    request: HttpRequest,
    *,
    form,
    target_label: str,
    status: int = 200,
) -> HttpResponse:
    return render(
        request,
        "moderation/report_form.html",
        {"form": form, "target_label": target_label},
        status=status,
    )


@login_required
@require_http_methods(["GET", "POST"])
def report_user(request: HttpRequest, target_id: int) -> HttpResponse:
    target = get_object_or_404(
        get_user_model().objects.only("pk", "username", "withdrawn_at"),
        pk=target_id,
    )
    form = UserReportForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            submit_report(
                reporter=request.user,
                target_type=TargetType.USER,
                target_id=target.pk,
                context=form.cleaned_data["context"],
                reason=form.cleaned_data["reason"],
            )
        except ReportSubmissionError:
            form.add_error(None, _GENERIC_ERROR)
        else:
            return redirect("/")
    status = 400 if request.method == "POST" else 200
    return _render_report_form(
        request,
        form=form,
        target_label=project_account_identity(user=target).display_name,
        status=status,
    )


@login_required
@require_http_methods(["GET", "POST"])
def report_product(request: HttpRequest, target_id: int) -> HttpResponse:
    target = get_object_or_404(
        visible_products(Product.objects.select_related("owner")),
        pk=target_id,
    )
    form = ReportReasonForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            submit_report(
                reporter=request.user,
                target_type=TargetType.PRODUCT,
                target_id=target.pk,
                context=ReportContext.PRODUCT,
                reason=form.cleaned_data["reason"],
            )
        except ReportSubmissionError:
            form.add_error(None, _GENERIC_ERROR)
        else:
            return redirect("/")
    status = 400 if request.method == "POST" else 200
    return _render_report_form(
        request,
        form=form,
        target_label=target.title,
        status=status,
    )
