"""
Seed data command — populates the database with realistic AIESEC demo data.
Usage: python manage.py seed_data [--count 50]
"""
import random
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import SiteConfig
from members.models import Member, Team
from ops.models import EP, StageHistory, Interaction
from partners.models import IR, Opportunity

TUNISIAN_FIRST_NAMES = [
    "Ahmed", "Amina", "Youssef", "Fatma", "Mohamed", "Mariem", "Omar", "Ines",
    "Karim", "Sarra", "Houssem", "Nour", "Mehdi", "Amal", "Skander", "Rania",
    "Walid", "Leila", "Sofiene", "Yasmine", "Tarek", "Donia", "Anis", "Chaima",
]

TUNISIAN_LAST_NAMES = [
    "Ben Salah", "Trabelsi", "Gharbi", "Jebali", "Mansour", "Charfi", "Bouzid",
    "Ben Ali", "Haddad", "Riahi", "Sassi", "Abidi", "Marzouki", "Mahmoudi",
    "Kacem", "Hammami", "Nasri", "Ben Youssef", "Zouari", "Dridi",
]

UNIVERSITIES = [
    "Université de Carthage", "Université de Tunis", "Université de Sousse",
    "Université de Sfax", "Université de Monastir", "Université de Gabès",
    "INSAT", "ENIT", "SUP'COM", "IHEC Carthage", "Faculté des Sciences de Tunis",
]

MAJORS = [
    "Computer Science", "Business Administration", "Marketing", "Finance",
    "Engineering", "Economics", "Languages", "Law", "Medicine", "Architecture",
]

IR_ENTITIES = [
    ("AIESEC Brazil", "Brazil"),
    ("AIESEC India", "India"),
    ("AIESEC Turkey", "Turkey"),
    ("AIESEC Egypt", "Egypt"),
    ("AIESEC Morocco", "Morocco"),
    ("AIESEC Poland", "Poland"),
    ("AIESEC Colombia", "Colombia"),
    ("AIESEC Indonesia", "Indonesia"),
    ("AIESEC Romania", "Romania"),
    ("AIESEC Italy", "Italy"),
]

INTERACTION_NOTES = [
    "WhatsApp: Sent registration link. EP will complete by Friday.",
    "Call: Discussed opportunity details. EP excited about Brazil.",
    "WhatsApp: EP submitted passport scan. Forwarded to IR.",
    "Meeting: Reviewed contract terms. EP signed acceptance letter.",
    "WhatsApp: Follow-up on application status. Pending IR response.",
    "Call: EP has questions about visa process. Sent guide.",
    "WhatsApp: EP confirmed travel dates. Notified IR partner.",
    "Meeting: EP struggling with papers. Assigned buddy for help.",
    "WhatsApp: Sent interview prep materials. Mock interview scheduled.",
    "Call: EP accepted! Notifying IR and starting papers process.",
]


class Command(BaseCommand):
    help = "Seed the database with realistic AIESEC demo data"

    def add_arguments(self, parser):
        parser.add_argument("--count", type=int, default=30, help="Number of EPs to create")

    def handle(self, *args, **options):
        count = options["count"]
        now = timezone.now()

        self.stdout.write("🌱 Seeding database...")

        # ── SiteConfig ────────────────────────────────────────────
        SiteConfig.objects.update_or_create(
            pk=1,
            defaults={
                "lc_name": "AIESEC LC Carthage",
                "current_term": "2026-S1",
                "contact_email": "vp@aiesec-carthage.org",
            },
        )

        # ── Teams ─────────────────────────────────────────────────
        oGT, _ = Team.objects.get_or_create(name="oGT")
        oGTe, _ = Team.objects.get_or_create(name="oGTe")
        iGT, _ = Team.objects.get_or_create(name="iGT")

        # ── Members ───────────────────────────────────────────────
        vp, _ = Member.objects.get_or_create(
            name="Amine Amouna",
            defaults={"role": "VP", "is_active": True},
        )

        tl_gt, _ = Member.objects.get_or_create(
            name="Nadia Mansour",
            defaults={"role": "TL", "team": oGT, "is_active": True},
        )
        tl_gte, _ = Member.objects.get_or_create(
            name="Karim Jebali",
            defaults={"role": "TL", "team": oGTe, "is_active": True},
        )

        ops_members = []
        for name, team in [("Youssef Trabelsi", oGT), ("Sarra Ben Ali", oGT),
                           ("Mehdi Riahi", oGTe), ("Ines Kacem", oGTe)]:
            m, _ = Member.objects.get_or_create(
                name=name,
                defaults={"role": "OPS", "team": team, "is_active": True},
            )
            ops_members.append(m)

        ir_members = []
        for name in ["Omar Zouari", "Fatma Dridi"]:
            m, _ = Member.objects.get_or_create(
                name=name,
                defaults={"role": "IR", "team": iGT, "is_active": True},
            )
            ir_members.append(m)

        self.stdout.write(f"  ✅ {Member.objects.count()} members in {Team.objects.count()} teams")

        # ── IRs + Opportunities ──────────────────────────────────
        irs = []
        for entity_name, country in IR_ENTITIES:
            ir, _ = IR.objects.get_or_create(
                entity_name=entity_name,
                country=country,
                defaults={
                    "assigned_to": random.choice(ir_members),
                    "opportunities_page_link": f"https://aiesec.org/opportunities/{country.lower()}",
                    "vp_contact": f"VP {random.choice(TUNISIAN_FIRST_NAMES)} ({country})",
                },
            )
            irs.append(ir)
            # Create 2-4 opportunities per IR
            for _ in range(random.randint(2, 4)):
                opp = Opportunity.objects.create(
                    ir=ir,
                    title=f"{random.choice(['Web Dev', 'Marketing Intern', 'Teaching English', 'Data Analyst', 'UX Designer'])}",
                    type=random.choice(Opportunity.OppType.choices)[0],
                    description=f"Exciting opportunity in {country}. Gain international experience.",
                    is_open=random.choice([True, True, True, False]),
                    track=random.choice(["GT", "GTe"]),
                    expires_at=(now + timedelta(days=random.randint(30, 180))).date(),
                )

        self.stdout.write(f"  ✅ {IR.objects.count()} IRs, {Opportunity.objects.count()} opportunities")

        # ── EPs ──────────────────────────────────────────────────
        stages = [s[0] for s in EP.Stage.choices]
        # Weight distribution toward early/mid stages
        stage_weights = [0.20, 0.13, 0.13, 0.13, 0.10, 0.07, 0.07, 0.07, 0.10]
        # Corresponding to: open, matched, applied, accepted, approved, papers_done, not_papers, do_papers, realized

        for i in range(count):
            full_name = f"{random.choice(TUNISIAN_FIRST_NAMES)} {random.choice(TUNISIAN_LAST_NAMES)}"
            stage = random.choices(stages, weights=stage_weights, k=1)[0]
            track = random.choice(["GT", "GTe"])
            ops = random.choice(ops_members)

            # Bias: GT goes to oGT, GTe to oGTe
            if track == "GT" and random.random() < 0.8:
                ops = random.choice([m for m in ops_members if m.team == oGT] or ops_members)
            elif track == "GTe" and random.random() < 0.8:
                ops = random.choice([m for m in ops_members if m.team == oGTe] or ops_members)

            # Match to opportunity if past "matched" stage
            opp = None
            if stage != "open" and stage != "matched_with_opp":
                opp = random.choice(Opportunity.objects.filter(track=track)) if Opportunity.objects.filter(track=track).exists() else None

            created_days_ago = random.randint(1, 120)
            activity_days_ago = random.randint(0, created_days_ago)

            ep = EP.objects.create(
                full_name=full_name,
                phone=f"+216{random.randint(20000000, 99999999)}",
                email=f"{full_name.lower().replace(' ', '.').replace('é','e').replace('è','e')}@gmail.com",
                socials=f"WhatsApp: +216{random.randint(20000000, 99999999)}",
                university=random.choice(UNIVERSITIES),
                major=random.choice(MAJORS),
                year_of_study=str(random.randint(2, 5)),
                track=track,
                current_stage=stage,
                assigned_to=ops,
                matched_opportunity=opp,
                term="2026-S1",
                source=random.choice(["manual", "expa_sync"]),
                created_at=now - timedelta(days=created_days_ago),
                last_activity_at=now - timedelta(days=activity_days_ago),
                last_edited_by=ops,
            )

            # Stage history from open → current stage
            stage_seq = stages[:stages.index(stage) + 1]
            for j, s in enumerate(stage_seq):
                days_ago = created_days_ago - j * random.randint(1, 10)
                days_ago = max(days_ago, 0)
                StageHistory.objects.create(
                    ep=ep,
                    stage=s,
                    previous_stage=stage_seq[j - 1] if j > 0 else "",
                    changed_by=ops,
                    changed_at=now - timedelta(days=days_ago),
                    note=f"Stage changed to {EP.Stage(s).label}",
                )

            # 0-5 interactions per EP
            for _ in range(random.randint(0, 5)):
                Interaction.objects.create(
                    ep=ep,
                    author=random.choice([vp] + ops_members),
                    date=now - timedelta(days=random.randint(0, activity_days_ago)),
                    note=random.choice(INTERACTION_NOTES),
                )

        # ── Flag some EPs as problems ─────────────────────────────
        problem_eps = EP.objects.order_by("?")[:max(1, count // 8)]
        for ep in problem_eps:
            ep.set_problem_flag(
                flag=random.choice(["fix_ep_problem", "fix_ir_problem"]),
                changed_by=vp,
                note="Auto-flagged during seed data generation",
            )

        self.stdout.write(f"  ✅ {EP.objects.count()} EPs, {StageHistory.objects.count()} stage changes")
        self.stdout.write(f"  ✅ {Interaction.objects.count()} interactions")
        self.stdout.write(self.style.SUCCESS(f"🎉 Done! Seeded {count} EPs across all stages."))
        self.stdout.write(f"\n  Default members in identity picker:")
        self.stdout.write(f"    VP:      {vp.name}")
        self.stdout.write(f"    TL (GT): {tl_gt.name}")
        self.stdout.write(f"    TL (GTe):{tl_gte.name}")
        for m in ops_members:
            self.stdout.write(f"    OPS:     {m.name}")
        for m in ir_members:
            self.stdout.write(f"    IR:      {m.name}")
