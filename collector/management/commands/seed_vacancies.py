import random

from django.core.management.base import BaseCommand

from collector.models import Source, Vacancy

COMPANIES = ["Acme", "Globex", "Initech", "Umbrella", "Hooli", "Stark", "Wayne"]
TITLES = ["Python developer", "Backend developer", "Django developer", "Data engineer", "DevOps engineer"]


class Command(BaseCommand):
    help = "Генерирует вакансии для замеров производительности"

    def add_arguments(self, parser):
        parser.add_argument("--count", type=int, default=50000)
        parser.add_argument("--sources", type=int, default=4)

    def handle(self, *args, **options):
        count, source_count = options["count"], options["sources"]
        sources = [
            Source.objects.get_or_create(
                slug=f"seed{i}",
                defaults={"name": f"Seed source {i}", "base_url": "stub://0", "is_enabled": False},
            )[0]
            for i in range(source_count)
        ]
        rnd = random.Random(42)
        batch = []
        for i in range(count):
            source = sources[i % source_count]
            batch.append(
                Vacancy(
                    source=source,
                    external_id=f"seed-{i}",
                    title=f"{rnd.choice(TITLES)} {i}",
                    company=rnd.choice(COMPANIES),
                    salary_min=rnd.randrange(50, 250) * 1000,
                    salary_max=rnd.randrange(250, 600) * 1000,
                    salary_currency="RUB",
                    is_remote=rnd.random() < 0.6,
                    url=f"https://example.com/seed/{i}",
                    is_active=rnd.random() < 0.9,
                )
            )
            if len(batch) >= 5000:
                Vacancy.objects.bulk_create(batch, ignore_conflicts=True)
                batch = []
        if batch:
            Vacancy.objects.bulk_create(batch, ignore_conflicts=True)
        self.stdout.write(f"вакансий в базе: {Vacancy.objects.count()}")
