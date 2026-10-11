"""Turn model findings + symptoms into a short, plain-language draft report."""
import os

DISCLAIMER = (
    "This is an educational AI demo, not a medical device. It cannot diagnose. "
    "Always consult a qualified doctor or radiologist."
)

SYSTEM = (
    "You are a radiology-report drafting assistant for an educational demo. "
    "You receive model probabilities for chest X-ray findings and the patient's "
    "symptoms. Write a concise draft with sections: Findings, Possible "
    "Considerations, Suggested Next Steps. Use hedged language ('may suggest'), "
    "never state a definitive diagnosis, and end by telling the reader to see a "
    "doctor. Under 200 words."
)


def _template_report(findings, symptoms: str) -> str:
    lines = ["**Findings (model probabilities)**"]
    lines += [f"- {n}: {p:.0%}" for n, p in findings]
    if symptoms:
        lines += ["", f"**Reported symptoms:** {symptoms}"]
    top = findings[0]
    lines += [
        "",
        f"**Possible consideration:** the highest-scoring finding is {top[0]} "
        f"({top[1]:.0%}). This may warrant clinical review.",
        "",
        "**Next steps:** share this with a doctor or radiologist for interpretation.",
    ]
    return "\n".join(lines)


def make_report(findings, symptoms: str = "") -> str:
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        return _template_report(findings, symptoms)
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=key)
        findings_txt = "\n".join(f"- {n}: {p:.2f}" for n, p in findings)
        msg = client.messages.create(
            model=os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5"),
            max_tokens=500,
            system=SYSTEM,
            messages=[
                {
                    "role": "user",
                    "content": f"Model findings:\n{findings_txt}\n\nSymptoms: {symptoms or 'none given'}",
                }
            ],
        )
        return msg.content[0].text
    except Exception as e:  # fall back so the demo never breaks
        return _template_report(findings, symptoms) + f"\n\n_(LLM unavailable: {e})_"
