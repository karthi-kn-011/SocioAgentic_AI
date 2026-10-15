import hashlib
from typing import Dict, List, Optional
from .base_provider import BaseLLMProvider
from ..schemas.post import ContentGenerationContext, PostVariant, QualityRubricResult

class MockProvider(BaseLLMProvider):
    """High-fidelity, context-aware deterministic mock LLM provider.
    Synthesizes dynamically varied content across themes, platforms, and variation indexes
    without requiring external API credentials.
    """

    @property
    def provider_name(self) -> str:
        return "mock"

    def is_available(self) -> bool:
        return True

    async def generate_variants(self, context: ContentGenerationContext) -> Dict[str, PostVariant]:
        topic = context.topic.strip()
        theme = (context.theme or "Thought Leadership").strip()
        tone = context.tone or "Professional & Engaging"
        audience = context.target_audience or "Professionals"
        var_idx = context.variation_index or 0

        # Extract topical keywords for authentic hashtags
        clean_words = [w for w in topic.replace(",", " ").replace("-", " ").split() if len(w) > 3]
        primary_tag = f"#{clean_words[0].capitalize()}" if clean_words else "#Innovation"
        secondary_tag = f"#{clean_words[1].capitalize()}" if len(clean_words) > 1 else "#Strategy"

        variants: Dict[str, PostVariant] = {}

        for platform in context.platforms:
            platform_key = platform.upper()
            content, hook_type, char_limit = self._generate_platform_copy(
                platform=platform_key,
                topic=topic,
                theme=theme,
                tone=tone,
                audience=audience,
                primary_tag=primary_tag,
                secondary_tag=secondary_tag,
                var_idx=var_idx
            )

            hashtags = [primary_tag, secondary_tag]
            if platform_key == "LINKEDIN":
                hashtags.extend(["#Leadership", "#FutureOfWork"])
            elif platform_key == "META_INSTAGRAM":
                hashtags.extend(["#GrowthMindset", "#DailyInspiration", "#CreatorEconomy"])

            variants[platform_key] = PostVariant(
                platform=platform_key,
                content=content,
                character_count=len(content),
                character_limit=char_limit,
                hook_type=hook_type,
                hashtags=hashtags,
                call_to_action=self._get_theme_cta(theme, platform_key)
            )

        return variants

    def _generate_platform_copy(
        self,
        platform: str,
        topic: str,
        theme: str,
        tone: str,
        audience: str,
        primary_tag: str,
        secondary_tag: str,
        var_idx: int
    ) -> tuple[str, str, int]:
        hook_types = ["Question", "Contrarian Insight", "Data & Case Observation"]
        chosen_hook = hook_types[var_idx % len(hook_types)]

        if platform == "TWITTER":
            limit = 280
            if chosen_hook == "Question":
                body = f"🤔 Why do most {audience} overlook {topic}?\n\nReal impact isn't about doing more—it's about building smarter, adaptive systems.\n\nWhat's your take? 👇\n{primary_tag} {secondary_tag}"
            elif chosen_hook == "Contrarian Insight":
                body = f"🚀 Unpopular opinion on {topic}:\n\nThe conventional approach is outdated. The teams winning right now are pairing rapid iteration with high-leverage automation.\n\nAgree or disagree? {primary_tag}"
            else:
                body = f"💡 3 unexpected lessons from diving into {topic}:\n\n1. Simplicity scales.\n2. Human judgment matters more than ever.\n3. Measure outcomes, not activity.\n\n{primary_tag} #TechTrends"

            # Enforce hard 280 ceiling
            if len(body) > 280:
                body = body[:275] + "..."
            return body, chosen_hook, limit

        elif platform == "LINKEDIN":
            limit = 3000
            cta = self._get_theme_cta(theme, "LINKEDIN")
            if chosen_hook == "Question":
                body = (
                    f"💡 Are modern teams addressing {topic} the right way?\n\n"
                    f"When we look at how {audience} navigate this space, one pattern stands out: "
                    f"those who treat {topic} as a core strategic lever consistently outperform.\n\n"
                    f"Here are 3 foundational shifts to consider this quarter:\n\n"
                    f"1️⃣ Shift from reactive execution to automated guardrails.\n"
                    f"2️⃣ Keep human-in-the-loop review at pivotal decision points.\n"
                    f"3️⃣ Build transparent feedback loops that learn from every iteration.\n\n"
                    f"{cta}\n\n"
                    f"{primary_tag} {secondary_tag} #Leadership #Strategy"
                )
            elif chosen_hook == "Contrarian Insight":
                body = (
                    f"🔍 Most strategies around {topic} miss the biggest leverage point.\n\n"
                    f"In discussions with industry peers, everyone focuses on speed—but velocity without alignment is just waste. "
                    f"Building sustainable momentum in {topic} requires deliberate systems, not sheer brute force.\n\n"
                    f"Key Takeaways for {audience}:\n"
                    f"• Standardize the repetitive tasks.\n"
                    f"• Empower teams to focus on high-judgment decisions.\n"
                    f"• Benchmark progress against verifiable metrics, not vanity signals.\n\n"
                    f"{cta}\n\n"
                    f"{primary_tag} {secondary_tag} #FutureOfWork #ExecutiveBriefing"
                )
            else:
                body = (
                    f"📈 Rethinking {topic}: What the data reveals for {audience}.\n\n"
                    f"Over the past 6 months, we observed teams scaling their workflows around {topic}. "
                    f"The common thread among the top quartile was simple: disciplined execution paired with modern tooling.\n\n"
                    f"Here is what works:\n"
                    f"1. Clear, documented operating principles.\n"
                    f"2. Multi-channel distribution without compromising message quality.\n"
                    f"3. Continuous optimization based on actual audience feedback.\n\n"
                    f"{cta}\n\n"
                    f"{primary_tag} {secondary_tag} #BusinessGrowth #Innovation"
                )
            return body, chosen_hook, limit

        elif platform == "META_FACEBOOK":
            limit = 2000
            if chosen_hook == "Question":
                body = (
                    f"✨ Quick question for everyone thinking about {topic}: What's been your biggest breakthrough recently? 💬\n\n"
                    f"We've been seeing amazing shifts in how our community tackles this. "
                    f"Whether you're just getting started or scaling up, the key is keeping things clear and consistent.\n\n"
                    f"Drop your thoughts below—let's share ideas! 👇\n\n{primary_tag}"
                )
            else:
                body = (
                    f"✨ Let's talk about {topic}! ✨\n\n"
                    f"No matter what stage you're at, staying curious and building solid daily habits around this space makes all the difference.\n\n"
                    f"What's one lesson or tool that changed the game for you? Let's connect in the comments! 👇\n\n{primary_tag}"
                )
            return body, chosen_hook, limit

        else:  # META_INSTAGRAM
            limit = 2200
            body = (
                f"Swipe for the breakdown on {topic} ➡️📲\n\n"
                f"The future belongs to those who build smart, iterate fast, and stay authentic to their mission.\n\n"
                f"📌 3 things to remember:\n"
                f"• Consistency beats perfection.\n"
                f"• Systems create freedom.\n"
                f"• Quality always shines through.\n\n"
                f"Save this post for your next planning session! 📌\n"
                f".\n.\n.\n"
                f"{primary_tag} {secondary_tag} #Creators #DailyInspiration #DigitalStrategy"
            )
            return body, chosen_hook, limit

    def _get_theme_cta(self, theme: str, platform: str) -> str:
        t = theme.lower()
        if "product" in t or "launch" in t or "promotional" in t:
            return "👉 Explore the full release notes and see it in action: Link in comments."
        elif "educational" in t:
            return "👉 Bookmark this guide and share it with your team."
        elif "storytelling" in t:
            return "👉 Have you experienced a similar pivot? Let's discuss in the comments."
        elif "community" in t or "engagement" in t:
            return "👉 What's your perspective on this? Drop your thoughts below."
        else:
            return "👉 How is your organization approaching this quarter? Let's discuss in the comments."

    async def evaluate_quality(
        self,
        variants: Dict[str, str],
        context: ContentGenerationContext
    ) -> QualityRubricResult:
        import re
        issues = []
        all_text = " ".join(variants.values())
        words = re.findall(r'\b[a-zA-Z]{2,}\b', all_text)

        is_gibberish = len(words) < 5 or (len(all_text) > 0 and len(set(words)) < 3)

        topic_words = set(re.findall(r'\b[a-zA-Z]{3,}\b', context.topic.lower()))
        content_words = set(w.lower() for w in words)
        overlap = topic_words.intersection(content_words)
        has_overlap = bool(overlap) or not topic_words

        grammar = 30 if is_gibberish else 95
        relevance = 20 if is_gibberish else (94 if has_overlap else 50)
        theme = 20 if is_gibberish else 92
        naturalness = 20 if is_gibberish else 91
        engagement = 20 if is_gibberish else 88
        safety = 98

        for plt, text in variants.items():
            if not text or len(text.strip()) < 15:
                issues.append(f"CRITICAL: {plt} draft is empty or too short.")
            if plt == "TWITTER" and len(text) > 280:
                issues.append(f"CRITICAL: Twitter draft exceeds 280 characters ({len(text)} chars).")

        if is_gibberish:
            issues.append("CRITICAL: Content appears to be gibberish or extremely repetitive.")
        if not has_overlap and not is_gibberish:
            issues.append("Post content does not meaningfully reflect the seed topic keywords.")

        dim_scores = [grammar, relevance, theme, naturalness, engagement, safety]
        composite = round(sum(dim_scores) / len(dim_scores))
        passed = composite >= 70 and not any("CRITICAL" in i for i in issues) and not is_gibberish

        feedback = (
            "Content successfully passed all 7 quality dimensions: grammar, theme adherence, platform suitability, and CTA relevance."
            if passed
            else "Quality critique flagged adjustments: " + "; ".join(issues)
        )

        return QualityRubricResult(
            grammar_score=grammar,
            topic_relevance_score=relevance,
            theme_adherence_score=theme,
            platform_suitability_score=90 if passed else 45,
            naturalness_score=naturalness,
            engagement_score=engagement,
            safety_score=safety,
            composite_score=composite,
            passed=passed,
            critique_feedback=feedback,
            issues_detected=issues
        )

