from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from apps.accounts.models import RevocationTask
from apps.accounts.withdrawal import process_revocation_task


class Command(BaseCommand):
    help = "대기·재시도 상태의 회원 탈퇴 세션/소켓/presence 폐기 작업을 처리합니다."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)

    def handle(self, *args, **options):
        limit = options["limit"]
        if not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")
        task_ids = list(
            RevocationTask.objects.filter(
                Q(
                    status__in=(RevocationTask.Status.PENDING, RevocationTask.Status.RETRY),
                    available_at__lte=timezone.now(),
                )
                | Q(
                    status=RevocationTask.Status.PROCESSING,
                    lease_expires_at__lt=timezone.now(),
                )
            )
            .order_by("available_at", "pk")
            .values_list("pk", flat=True)[:limit]
        )
        completed = sum(process_revocation_task(task_id=task_id) for task_id in task_ids)
        self.stdout.write(f"processed={len(task_ids)} completed={completed}")
