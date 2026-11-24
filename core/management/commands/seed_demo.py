"""python manage.py seed_demo  - fills the site with realistic demo content for the viva.

Safe to run more than once: everything is matched by title or username first.

    python manage.py seed_demo              # uses the AI provider in .env for the outreach kit
    python manage.py seed_demo --skip-kits  # no AI calls at all (fast, offline)

Demo logins (password for all: smartedu-demo-26):
    teacher  - Teacher group: upload lessons, studio, news, quiz reports
    student  - Class 7 student
    parent   - parent account
"""

from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import Group, User
from django.contrib.contenttypes.models import ContentType
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone

from ask.models import ChatQuery
from courses.models import Quiz, QuizAttempt, Topic, Unit
from engagement.models import Comment, Feedback, NewsletterSubscriber, Rating
from media_portal.models import Announcement, Article, Event
from repository.models import Resource, Subject

PASSWORD = "smartedu-demo-26"

LESSONS = [
    {
        "title": "The water cycle", "subject": "science", "grade": 7, "tags": "water cycle, evaporation, condensation, rain",
        "description": "How water moves between the oceans, the air and the land: evaporation, condensation, precipitation and collection.",
        "text": """The water cycle is the continuous movement of water between the oceans, the atmosphere and the land. The total amount of water on Earth stays almost the same; it only changes form and place.

Evaporation is the first stage. The Sun heats water in oceans, rivers, lakes and even puddles, and some of it turns into an invisible gas called water vapour. Plants also release water vapour through tiny pores in their leaves. This is called transpiration.

Condensation happens when water vapour rises, cools down and turns back into tiny droplets of liquid water. Millions of these droplets together form clouds. Condensation is also why drops form on the outside of a glass of cold water.

Precipitation is water falling from clouds to the ground. When the droplets in a cloud join together and become too heavy, they fall as rain, snow or hail. Goa gets most of its rain during the south-west monsoon, from June to September.

Collection is the last stage. Rain water flows into rivers and lakes, soaks into the ground as groundwater, and finally returns to the sea. Then the Sun heats it again and the cycle repeats.""",
    },
    {
        "title": "Why we have seasons", "subject": "geography", "grade": 7, "tags": "seasons, earth, axis, sun",
        "description": "Earth's tilted axis, not its distance from the Sun, gives us summer and winter.",
        "text": """Earth's axis is tilted by about 23.5 degrees compared to the path it follows around the Sun. Because of this tilt, different parts of Earth receive different amounts of sunlight during the year.

When the Northern Hemisphere is tilted towards the Sun, sunlight falls on it more directly and days are longer. This is summer in the north, and it happens around June. At the same time the Southern Hemisphere is tilted away from the Sun and has winter.

Six months later, around December, the situation is reversed. The Northern Hemisphere is tilted away from the Sun, the sunlight is spread over a larger area, days are shorter, and it is winter in the north.

Seasons are not caused by Earth's distance from the Sun. In fact Earth is closest to the Sun in early January, during winter in India.

Places near the equator, like much of India, have small changes in temperature during the year. Their seasons are shaped more by the monsoon winds than by the tilt alone.""",
    },
    {
        "title": "Photosynthesis", "subject": "science", "grade": 9, "tags": "photosynthesis, plants, chlorophyll, sunlight",
        "description": "How green plants make their own food from sunlight, water and carbon dioxide.",
        "text": """Photosynthesis is the process by which green plants make their own food using sunlight. It takes place mainly in the leaves.

Plants take in carbon dioxide from the air through tiny pores called stomata, and absorb water from the soil through their roots. The water travels up the stem to the leaves.

Chlorophyll is the green pigment in the leaves. It captures energy from sunlight. Using this energy, the plant turns carbon dioxide and water into glucose, a kind of sugar that stores energy.

Oxygen is released into the air as a by-product of photosynthesis. Almost all the oxygen we breathe comes from photosynthesis by plants and algae.

The glucose is used by the plant for energy and growth, and extra glucose is stored as starch. A simple iodine test on a leaf shows the presence of starch by turning blue-black.""",
    },
    {
        "title": "Fractions on a number line", "subject": "mathematics", "grade": 6, "tags": "fractions, number line, equivalent fractions",
        "description": "What a fraction means, how to place it on a number line, and equivalent fractions.",
        "text": """A fraction shows a part of a whole. In the fraction 3/4, the bottom number, the denominator, tells us the whole is divided into 4 equal parts. The top number, the numerator, tells us we take 3 of those parts.

To show 3/4 on a number line, divide the space between 0 and 1 into 4 equal parts and count 3 parts from 0.

Equivalent fractions name the same amount. 1/2, 2/4 and 4/8 all sit at the same point on the number line. We get an equivalent fraction by multiplying or dividing the numerator and the denominator by the same number.

To compare fractions with the same denominator, compare the numerators: 5/8 is greater than 3/8. To compare fractions with different denominators, first change them to equivalent fractions with a common denominator.""",
    },
    {
        "title": "Light, shadows and reflection", "subject": "science", "grade": 6, "tags": "light, shadows, reflection, mirror",
        "description": "Why shadows form, which materials let light through, and how mirrors reflect light.",
        "text": """Light travels in straight lines. This is why we cannot see around a corner, and why shadows form.

A shadow forms when an opaque object blocks light. Opaque objects, like wood or a book, do not let light pass through. Transparent objects, like clear glass, let almost all light pass through. Translucent objects, like butter paper, let some light through.

The size of a shadow changes with the distance between the object and the light source. When the object moves closer to the torch, its shadow becomes bigger.

A mirror reflects light. When light falls on a smooth shiny surface it bounces back; this is called reflection. The image in a plane mirror is upright, the same size as the object, and left and right are swapped.""",
    },
]

VIDEO = {
    "title": "Why do we have different seasons? (video)", "subject": "geography", "grade": 7, "tags": "seasons, video",
    "url": "https://www.youtube.com/watch?v=WgHmqv_-UbQ",
    "description": "A short video from the California Academy of Sciences explaining why Earth has seasons.",
}

SYLLABUS = [
    ("geography", 7, 1, "Maps and globes", [("Reading a map", []), ("Latitudes and longitudes", [])]),
    ("geography", 7, 2, "Earth and the Sun", [
        ("Why we have seasons", ["Why we have seasons", "Why do we have different seasons? (video)"]),
        ("Day and night", []), ("Latitude and climate zones", []),
    ]),
    ("science", 7, 4, "Water", [("The water cycle", ["The water cycle"]), ("Saving water", [])]),
    ("science", 9, 6, "Life processes", [("Photosynthesis", ["Photosynthesis"]), ("Respiration", [])]),
    ("mathematics", 6, 7, "Fractions", [("Fractions on a number line", ["Fractions on a number line"]), ("Adding fractions", [])]),
    ("science", 6, 11, "Light, shadows and reflections", [("Shadows and reflection", ["Light, shadows and reflection"])]),
]

SEASONS_QUIZ = [
    {"q": "What causes the seasons on Earth?", "options": ["The tilt of Earth's axis", "Earth's distance from the Sun", "The Moon's phases", "Clouds"], "answer": 0, "why": "Seasons come from the 23.5° tilt of Earth's axis, not from distance."},
    {"q": "When the Northern Hemisphere tilts towards the Sun, it has…", "options": ["winter", "summer", "spring", "autumn"], "answer": 1, "why": "More direct sunlight and longer days give summer."},
    {"q": "By about how many degrees is Earth's axis tilted?", "options": ["10", "23.5", "45", "90"], "answer": 1, "why": "Earth's axis is tilted by about 23.5 degrees."},
    {"q": "When is Earth closest to the Sun?", "options": ["Early January", "June", "September", "It never changes"], "answer": 0, "why": "Earth is closest to the Sun in early January, during winter in India."},
]

UNANSWERED = [
    "How do volcanoes erupt?", "Why do volcanoes form near plate boundaries?", "What is a black hole?",
    "How do black holes form?", "What causes earthquakes?", "How are earthquakes measured?",
    "Who built the Aguada fort?", "What is a volcano made of?",
]


class Command(BaseCommand):
    help = "Fill the site with demo lessons, syllabus, news, events, users and activity."

    def add_arguments(self, parser):
        parser.add_argument("--skip-kits", action="store_true", help="Do not make an outreach kit (no AI calls).")

    def say(self, text):
        self.stdout.write(f"  {text}")

    def handle(self, *args, **options):
        call_command("setup_roles", stdout=self.stdout)
        users = self.users()
        lessons = self.lessons(users["teacher"])
        topics = self.syllabus(lessons)
        self.media(users["teacher"])
        quiz = self.quizzes(topics, users)
        if not options["skip_kits"]:
            self.kit(lessons["The water cycle"], users["teacher"], topics)
        self.activity(users, lessons, quiz)
        self.stdout.write(self.style.SUCCESS(f"Demo ready. Log in as teacher / student / parent with password {PASSWORD}"))

    # ------------------------------------------------------------------
    def users(self):
        made = {}
        specs = [
            ("teacher", "Sunita", "Naik", "teacher", None, ["Teacher"], True),
            ("student", "Riya", "Kamat", "student", 7, ["Student"], False),
            ("parent", "Prakash", "Gawas", "parent", None, [], False),
        ]
        for username, first, last, role, grade, groups, staff in specs:
            user, created = User.objects.get_or_create(
                username=username, defaults={"first_name": first, "last_name": last, "email": f"{username}@example.com", "is_staff": staff}
            )
            if created:
                user.set_password(PASSWORD)
                user.save()
            profile = user.profile
            profile.role, profile.grade, profile.school = role, grade, "PM SHRI HBGDM GHS, Dhargal"
            profile.save()
            user.groups.add(*Group.objects.filter(name__in=groups))
            made[username] = user
        self.say("users: teacher, student, parent")
        return made

    def lessons(self, teacher):
        out = {}
        for spec in LESSONS:
            res = Resource.objects.filter(title=spec["title"]).first()
            if res is None:
                res = Resource(
                    title=spec["title"], subject=Subject.objects.get(slug=spec["subject"]), grade=spec["grade"],
                    kind=Resource.Kind.DOCUMENT, description=spec["description"], uploaded_by=teacher,
                )
                res.file.save(f"{spec['title']}.md", ContentFile(spec["text"].encode()), save=True)  # indexes for Ask
                self.tag(res, spec["tags"])
            out[res.title] = res
        video = Resource.objects.filter(title=VIDEO["title"]).first()
        if video is None:
            video = Resource.objects.create(
                title=VIDEO["title"], subject=Subject.objects.get(slug=VIDEO["subject"]), grade=VIDEO["grade"],
                kind=Resource.Kind.VIDEO, url=VIDEO["url"], description=VIDEO["description"], uploaded_by=teacher,
            )
            self.tag(video, VIDEO["tags"])
        out[video.title] = video
        self.say(f"lessons: {len(out)} (indexed for Ask)")
        return out

    def tag(self, res, names):
        from repository.models import Tag
        from django.utils.text import slugify

        res.tags.set([Tag.objects.get_or_create(slug=slugify(n.strip()), defaults={"name": n.strip()})[0] for n in names.split(",")])

    def syllabus(self, lessons):
        topics = {}
        for subj, grade, number, title, items in SYLLABUS:
            unit, _ = Unit.objects.get_or_create(subject=Subject.objects.get(slug=subj), grade=grade, number=number, defaults={"title": title})
            for order, (topic_title, lesson_titles) in enumerate(items, start=1):
                topic, _ = Topic.objects.get_or_create(unit=unit, title=topic_title, defaults={"order": order})
                topic.resources.add(*[lessons[t] for t in lesson_titles if t in lessons])
                topics[topic_title] = topic
        seasons = topics["Why we have seasons"]
        seasons.objectives = "Explain how the tilt of Earth's axis causes seasons\nShow summer and winter with a globe and a torch\nSay why distance from the Sun is not the reason"
        seasons.save()
        self.say(f"syllabus: {Unit.objects.count()} units, {Topic.objects.count()} topics")
        return topics

    def media(self, teacher):
        now = timezone.now()
        articles = [
            ("Class 8 wins the taluka science fair", "achievement", True, 0,
             "A rainwater-harvesting model by four Class 8 students took first prize in Pernem.",
             "The model collects rain from the school roof, filters it through sand and charcoal, and stores it for the school garden.\n\nThe team will now represent Pernem taluka at the district science exhibition in December."),
            ("Revision periods for the first term exams", "notice", False, 1,
             "Extra revision periods start on Monday for Classes 9 and 10.",
             "Students can bring their doubts to the library after the last period. Teachers will be available from Monday to Friday."),
            ("Class 7 learnt about seasons in the courtyard", "learning", False, 3,
             "A torch, a globe and the school courtyard turned into a solar system.",
             "Students took turns walking the globe around a torch to see why one half of Earth gets more sunlight.\n\nThe lesson notes and a short quiz are now on Smart Education."),
            ("Library opens on Saturdays", "news", False, 6,
             "From December, the school library will be open on Saturday mornings.",
             "Students can borrow books and use the computers from 9 to 12 every Saturday."),
        ]
        for title, cat, featured, days, standfirst, body in articles:
            Article.objects.get_or_create(
                title=title,
                defaults={"category": cat, "featured": featured, "standfirst": standfirst, "body": body, "status": "published", "author": teacher, "published_at": now - timedelta(days=days)},
            )
        events = [
            ("Parents–teachers meeting", "meeting", 4, "School hall", "Meet class teachers and see your child's progress."),
            ("First term exams begin", "exam", 10, "", "The timetable is on the notice board and in News."),
            ("Annual day", "cultural", 20, "School ground", "Dance, drama and the Marathi sangeet natak by Classes 8 to 10."),
            ("Inter-house football", "sports", -5, "School ground", "Final between Mandovi and Zuari houses."),
        ]
        for title, kind, days, venue, desc in events:
            Event.objects.get_or_create(title=title, defaults={"kind": kind, "starts_at": now + timedelta(days=days, hours=3), "venue": venue, "description": desc})
        Announcement.objects.get_or_create(text="First term exams begin soon. Revision notes are in the Repository.", defaults={"link": "/repository/", "level": "info"})
        self.say("news: 4 stories, 4 events, 1 announcement")

    def quizzes(self, topics, users):
        quiz, _ = Quiz.objects.get_or_create(title="Seasons: check yourself", defaults={"topic": topics["Why we have seasons"], "questions": SEASONS_QUIZ, "created_by": users["teacher"]})
        if not quiz.attempts.exists():
            QuizAttempt.objects.create(quiz=quiz, user=users["student"], answers=[0, 1, 0, 1], score=2, total=4)
            QuizAttempt.objects.create(quiz=quiz, user=users["student"], answers=[0, 1, 1, 0], score=4, total=4)
        self.say("quiz: Seasons, with two attempts by the student")
        return quiz

    def kit(self, lesson, teacher, topics):
        from outreach_studio.models import OutreachKit
        from outreach_studio.tasks import start_kit

        ct = ContentType.objects.get_for_model(Resource)
        kit = OutreachKit.objects.filter(content_type=ct, object_id=lesson.pk, status="published").first()
        if kit:
            self.say("outreach kit: already published")
            return
        self.say("outreach kit: writing it for 'The water cycle' (this calls the AI provider)…")
        old = getattr(settings, "OUTREACH_RUN_INLINE", False)
        settings.OUTREACH_RUN_INLINE = True
        try:
            kit = start_kit(lesson, teacher)
        finally:
            settings.OUTREACH_RUN_INLINE = old
        kit.refresh_from_db()
        if kit.status != "review":
            self.stdout.write(self.style.WARNING(f"  outreach kit not ready: {kit.error}"))
            return
        kit.items.update(approved=True)
        kit.publish(teacher)
        quiz_item = kit.items.filter(kind="quiz").first()
        if quiz_item and quiz_item.content.get("questions"):
            Quiz.objects.get_or_create(kit=kit, defaults={"title": f"Quiz: {kit.title}", "topic": topics["The water cycle"], "questions": quiz_item.content["questions"], "generated_by_ai": True, "created_by": teacher})
        self.say("outreach kit: published on Learn, with a scored quiz")

    def activity(self, users, lessons, quiz):
        student, parent, teacher = users["student"], users["parent"], users["teacher"]
        if not ChatQuery.objects.exists():
            now = timezone.now()
            for i, q in enumerate(UNANSWERED * 2):
                c = ChatQuery.objects.create(question=q, answer="Not in the repository yet.", in_repository=False, user=student if i % 4 == 0 else None)
                ChatQuery.objects.filter(pk=c.pk).update(created_at=now - timedelta(days=i % 12, hours=i))
            for i in range(14):
                c = ChatQuery.objects.create(question="What is evaporation?", answer="(demo)", in_repository=True, trust_score=78 + i % 15, helpful=i % 5 != 0, user=student if i % 3 == 0 else None)
                ChatQuery.objects.filter(pk=c.pk).update(created_at=now - timedelta(days=i % 13))
        ct = ContentType.objects.get_for_model(Resource)
        seasons = lessons["Why we have seasons"]
        if not Comment.objects.exists():
            first = Comment.objects.create(content_type=ct, object_id=seasons.pk, user=student, body="If Earth is closest to the Sun in January, why is it not hot then?")
            Comment.objects.create(content_type=ct, object_id=seasons.pk, user=teacher, parent=first, body="Good question! The tilt matters more than the distance. In January our half of Earth is tilted away, so sunlight is spread out.")
        for user, stars in ((student, 5), (parent, 4)):
            Rating.objects.get_or_create(content_type=ct, object_id=seasons.pk, user=user, defaults={"stars": stars})
        Feedback.objects.get_or_create(name="Prakash Gawas", defaults={"email": "parent@example.com", "category": "content", "message": "Please add a lesson on volcanoes for Class 8. My son keeps asking about them."})
        NewsletterSubscriber.objects.get_or_create(email="parent@example.com", defaults={"name": "Prakash", "language": "mr"})
        self.say("activity: questions for the gap radar, comments, ratings, feedback, a subscriber")
