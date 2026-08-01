"""
Tests for the AI reader persona service.

Covers:
- Three personas (gentle_star / wise_moon / frank_sun) have correct metadata
- get_persona() returns the default for None / unknown keys
- get_persona_signature() returns the correct signature for each persona
- Prompt suffix and greeting are present
"""

from app.services.ai_personas import (
    PERSONA_REGISTRY,
    get_persona,
    get_persona_prompt_suffix,
    get_persona_greeting,
    get_persona_signature,
    DEFAULT_PERSONA,
)

PERSONA_KEYS = ["gentle_star", "wise_moon", "frank_sun"]

_REQUIRED_FIELDS = {
    "key", "name", "icon", "short_label", "description",
    "greeting_template", "prompt_suffix", "signature",
}


class TestGetPersona:
    """get_persona() lookups and fallback behaviour."""

    def test_known_keys_return_correct_name(self):
        """Each known persona key should return the matching persona dict."""
        cases = {
            "gentle_star": "温和的星",
            "wise_moon": "星光",
            "frank_sun": "率直的太阳",
        }
        for key, expected_name in cases.items():
            p = get_persona(key)
            assert p["name"] == expected_name, (
                f"Persona '{key}' returned name '{p['name']}', "
                f"expected '{expected_name}'"
            )

    def test_none_returns_default(self):
        """Calling get_persona(None) should return the DEFAULT_PERSONA."""
        p = get_persona(None)
        assert p["key"] == DEFAULT_PERSONA, (
            f"get_persona(None) returned '{p['key']}', "
            f"expected default '{DEFAULT_PERSONA}'"
        )

    def test_unknown_key_returns_default(self):
        """An unknown persona key should fall back to DEFAULT_PERSONA."""
        p = get_persona("completely_fake_persona_xyz")
        assert p["key"] == DEFAULT_PERSONA, (
            f"Unknown key should return DEFAULT_PERSONA, "
            f"got '{p['key']}'"
        )

    def test_all_personas_have_required_fields(self):
        """Every persona in the registry must have all required fields."""
        for key in PERSONA_KEYS:
            p = get_persona(key)
            missing = _REQUIRED_FIELDS - set(p.keys())
            assert not missing, (
                f"Persona '{key}' is missing required fields: {missing}"
            )


class TestPersonaSignatures:
    """get_persona_signature() returns the correct closing line."""

    def test_gentle_star_signature(self):
        sig = get_persona_signature("gentle_star")
        assert "温和的星" in sig, f"Signature missing persona name: {sig}"

    def test_wise_moon_signature(self):
        sig = get_persona_signature("wise_moon")
        assert "智慧的月" in sig, f"Signature missing persona name: {sig}"

    def test_frank_sun_signature(self):
        sig = get_persona_signature("frank_sun")
        assert "率直的太阳" in sig, f"Signature missing persona name: {sig}"

    def test_none_returns_default_signature(self):
        sig = get_persona_signature(None)
        default_sig = PERSONA_REGISTRY[DEFAULT_PERSONA]["signature"]
        assert sig == default_sig, (
            f"get_persona_signature(None) returned unexpected value: {sig}"
        )


class TestPersonaHelpers:
    """Prompt suffix and greeting helpers."""

    def test_prompt_suffix_not_empty(self):
        """All personas have a substantive prompt suffix."""
        for key in PERSONA_KEYS:
            suffix = get_persona_prompt_suffix(key)
            assert isinstance(suffix, str) and len(suffix) > 50, (
                f"Persona '{key}' prompt_suffix is too short or missing"
            )

    def test_greeting_not_empty(self):
        """All personas have a non-empty greeting template."""
        for key in PERSONA_KEYS:
            greeting = get_persona_greeting(key)
            assert isinstance(greeting, str) and len(greeting) > 10, (
                f"Persona '{key}' greeting is too short or missing"
            )

    def test_prompt_suffix_contains_own_signature(self):
        """Each persona's suffix should reference its own signature line."""
        for key in PERSONA_KEYS:
            suffix = get_persona_prompt_suffix(key)
            p = get_persona(key)
            assert p["signature"] in suffix, (
                f"Persona '{key}' prompt_suffix does not contain "
                f"its own signature"
            )
